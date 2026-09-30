"""Mock competitor market API.

Simulates a price-intelligence feed (the kind of data an SME would obtain from
a pricing-intelligence subscription or distributor portal). It is a separate
FastAPI application with its own data file and API-key authentication, and is
queried over HTTP by the Competitive Strategy Agent.

Prices move daily: each competitor's price for a product is a deterministic
function of (competitor, product, date), combining its category positioning,
a daily random walk, volume discounts and active promotions.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import data_file, get_settings

REFERENCE_FX_TO_USD = {"USD": 1.0, "INR": 88.2, "EUR": 0.8555, "AED": 3.6725, "GBP": 0.745}


@lru_cache
def market() -> dict[str, Any]:
    with open(data_file("market.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _rng(*parts: Any) -> random.Random:
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def _daily_drift(comp_id: str, mpn: str, day: date, volatility: float) -> float:
    """Mean-reverting weekly random walk, reproducible for any date."""
    level = 0.0
    week0 = day - timedelta(days=day.weekday())
    for k in range(8, -1, -1):  # last eight weeks
        wk = week0 - timedelta(weeks=k)
        level = 0.6 * level + _rng(comp_id, mpn, wk.isoformat()).gauss(0, volatility)
    return math.exp(level)


def _volume_discount(qty: int) -> float:
    if qty >= 200:
        return 0.06
    if qty >= 100:
        return 0.045
    if qty >= 50:
        return 0.03
    if qty >= 20:
        return 0.015
    return 0.0


class Offer(BaseModel):
    competitor_id: str
    competitor: str
    positioning: str
    mpn: str
    unit_price: float
    currency: str
    warranty_months: int
    lead_time_days: int
    in_stock: bool
    reliability: float
    bundle: str | None = None
    promotion: str | None = None
    equivalent: str | None = None  # a brand store offers its own like-for-like model
    source: str = "Market feed"
    observed_at: str


class OfferQuery(BaseModel):
    mpn: str
    quantity: int = Field(ge=1, default=1)


class BatchRequest(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    items: list[OfferQuery]


def _equivalent(product: dict[str, Any], brands: list[str]) -> tuple[str, dict[str, Any]] | None:
    """The closest-priced product of the same category from one of ``brands`` (within 40%)."""
    best = None
    for other_mpn, other in market()["products"].items():
        if other["category"] != product["category"] or other.get("brand") not in brands:
            continue
        gap = abs(math.log(other["street_price_usd"] / product["street_price_usd"]))
        if gap <= math.log(1.4) and (best is None or gap < best[0]):
            best = (gap, other_mpn, other)
    return (best[1], best[2]) if best else None


def offers_for(mpn: str, qty: int, country: str, day: date | None = None) -> list[Offer]:
    data = market()
    requested = data["products"].get(mpn)
    if not requested:
        return []
    day = day or date.today()
    promos = {(p["competitor"], p["mpn"]): p for p in data["promotions"]}
    out: list[Offer] = []
    for comp in data["competitors"]:
        if country.upper() not in comp["serves"]:
            continue
        product, priced_mpn, equivalent = requested, mpn, None
        brands = comp.get("brands", "*")
        if brands != "*" and requested.get("brand") not in brands:
            # A brand store cannot sell another brand; it offers its own nearest model instead.
            eq = _equivalent(requested, brands)
            if eq is None:
                continue
            priced_mpn, product = eq
            equivalent = product["description"]
        rng = _rng(comp["id"], mpn, "coverage")
        if rng.random() > comp["coverage"] and (comp["id"], priced_mpn) not in promos:
            continue  # competitor does not carry this product
        factor = comp["category_factor"].get(product["category"], comp["category_factor"]["*"])
        promo = promos.get((comp["id"], priced_mpn))
        if promo:
            factor = promo["street_factor"]
        usd = product["street_price_usd"] * factor * _daily_drift(comp["id"], priced_mpn, day, comp["volatility"])
        usd *= 1 - _volume_discount(qty)
        price = usd * REFERENCE_FX_TO_USD[comp["currency"]]
        lo, hi = comp["lead_time_days"]
        day_rng = _rng(comp["id"], mpn, day.isoformat())
        out.append(
            Offer(
                competitor_id=comp["id"], competitor=comp["name"], positioning=comp["positioning"], mpn=mpn,
                unit_price=round(price, 2), currency=comp["currency"],
                warranty_months=comp["default_warranty_months"], lead_time_days=day_rng.randint(lo, hi),
                in_stock=day_rng.random() < 0.85, reliability=comp["reliability"], bundle=comp.get("bundle"),
                promotion=promo["label"] if promo else None, equivalent=equivalent,
                observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        )
    return sorted(out, key=lambda o: o.unit_price * (1 / REFERENCE_FX_TO_USD[o.currency]))


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != get_settings().market_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def create_market_app() -> FastAPI:
    app = FastAPI(title="Market Intelligence API (mock)", version="1.0", docs_url="/docs")

    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/competitors", dependencies=[Depends(require_key)])
    def competitors() -> list[dict[str, Any]]:
        return [
            {k: c[k] for k in ("id", "name", "hq", "currency", "positioning", "serves", "reliability", "default_warranty_months")}
            | {"bundle": c.get("bundle"), "brands": c.get("brands", "*"), "channel": c.get("channel"), "notes": c.get("notes")}
            for c in market()["competitors"]
        ]

    @app.get("/v1/offers", dependencies=[Depends(require_key)], response_model=list[Offer])
    def offers(mpn: str, country: str = Query(min_length=2, max_length=2), quantity: int = Query(default=1, ge=1)):
        return offers_for(mpn, quantity, country)

    @app.post("/v1/offers/batch", dependencies=[Depends(require_key)])
    def batch(req: BatchRequest) -> dict[str, list[Offer]]:
        return {q.mpn: offers_for(q.mpn, q.quantity, req.country) for q in req.items}

    return app


market_app = create_market_app()
