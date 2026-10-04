"""Dashboard, catalogue, market, finance, models and knowledge-base endpoints."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DealHistory, PriceTier, PriceVersion, Product, Rfp, StageRun, TaxRule, ValueAdd
from app.db.seed import load_json
from app.db.session import get_db
from app.finance.currency import UnknownCurrency, fx
from app.finance.tax import TaxContext, assess
from app.ml.registry import registry
from app.nlp.gazetteer import countries
from app.rag.stores import catalogue_store, invalidate_catalogue, knowledge_store
from app.services.market_client import MarketClient, MarketUnavailable

router = APIRouter(prefix="/api", tags=["reference"])


# --------------------------------------------------------------------------- dashboard


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    rfps = list(db.scalars(select(Rfp)))
    by_status = Counter(r.status for r in rfps)
    open_ = [r for r in rfps if r.status == "review"]
    approved = [r for r in rfps if r.status == "approved"]
    priced = [r for r in rfps if r.pricing and r.pricing.get("strategy")]
    strategy_mix: Counter[str] = Counter()
    below_cost = 0
    weighted = 0.0
    for r in priced:
        st = r.pricing["strategy"]
        below_cost += st.get("below_cost_competitors", 0)
        weighted += st.get("revenue", 0) * st.get("win_probability", 0)
        for line in st.get("lines", []):
            strategy_mix[line["strategy"]] += 1
    runs = list(db.scalars(select(StageRun).where(StageRun.status == "completed")))
    stage_ms: dict[str, list[int]] = {}
    for run in runs:
        stage_ms.setdefault(run.stage, []).append(run.duration_ms or 0)
    turnaround = []
    for r in priced:
        stages = [s for s in r.stages if s.status == "completed" and s.finished_at]
        if stages:
            turnaround.append((max(s.finished_at for s in stages) - min(s.started_at for s in stages)).total_seconds())
    now = datetime.now(timezone.utc)
    week = []
    for d in range(13, -1, -1):
        day = (now - timedelta(days=d)).date()
        week.append({"date": day.isoformat(), "received": sum(1 for r in rfps if r.created_at.date() == day)})
    margins = [r.margin_pct for r in priced if r.margin_pct is not None]
    return {
        "counts": {"total": len(rfps), **by_status},
        "pipeline_value": round(sum(r.total_base or 0 for r in open_), 2),
        "approved_value": round(sum(r.total_base or 0 for r in approved), 2),
        "weighted_value": round(weighted, 2),
        "average_margin_pct": round(sum(margins) / len(margins), 2) if margins else None,
        "below_cost_encounters": below_cost,
        "strategy_mix": dict(strategy_mix.most_common()),
        "average_stage_ms": {k: int(sum(v) / len(v)) for k, v in stage_ms.items()},
        "average_turnaround_s": round(sum(turnaround) / len(turnaround), 2) if turnaround else None,
        "intake_by_day": week,
        "base_currency": load_json("company.json")["base_currency"],
    }


@router.get("/company")
def company() -> dict[str, Any]:
    return load_json("company.json")


# --------------------------------------------------------------------------- catalogue


def _product(p: Product) -> dict[str, Any]:
    return {
        "sku": p.sku, "mpn": p.mpn, "name": p.name, "brand": p.brand, "category": p.category, "description": p.description,
        "specs": p.specs, "keywords": p.keywords, "unit": p.unit, "unit_cost": p.unit_cost, "list_price": p.list_price,
        "min_margin_pct": p.min_margin_pct, "floor_price": p.floor_price, "stock_qty": p.stock_qty,
        "lead_time_days": p.lead_time_days, "warranty_months": p.warranty_months, "tax_category": p.tax_category,
        "active": p.active, "list_margin_pct": round(100 * (p.list_price - p.unit_cost) / p.list_price, 2),
        "hsn": p.hsn, "gst_rate_pct": p.gst_rate_pct,
        "price_updated_at": p.price_updated_at.isoformat() if p.price_updated_at else None,
    }


@router.get("/catalog/products")
def products(q: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Product).order_by(Product.category, Product.sku)
    if category:
        stmt = stmt.where(Product.category == category)
    items = list(db.scalars(stmt))
    if q:
        ranked = {h.doc.id: h.score for h in catalogue_store().search(q, k=25)}
        items = sorted((p for p in items if p.sku in ranked), key=lambda p: -ranked[p.sku])
    return [_product(p) for p in items]


class ProductPatch(BaseModel):
    unit_cost: float | None = Field(default=None, gt=0)
    list_price: float | None = Field(default=None, gt=0)
    min_margin_pct: float | None = Field(default=None, ge=0, le=80)
    stock_qty: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0, le=365)
    active: bool | None = None


@router.patch("/catalog/products/{sku}")
def patch_product(sku: str, body: ProductPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.scalar(select(Product).where(Product.sku == sku))
    if p is None:
        raise HTTPException(status_code=404, detail="Product not found")
    before = (p.unit_cost, p.list_price, p.stock_qty)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    if p.list_price <= p.unit_cost:
        raise HTTPException(status_code=422, detail="List price must exceed unit cost")
    if (p.unit_cost, p.list_price, p.stock_qty) != before:
        p.price_updated_at = datetime.now(timezone.utc)
        db.add(PriceVersion(sku=p.sku, unit_cost=p.unit_cost, list_price=p.list_price, stock_qty=p.stock_qty,
                            effective_from=p.price_updated_at, source="Edited in catalogue"))
    db.flush()
    invalidate_catalogue()
    return _product(p)


@router.get("/catalog/value-adds")
def value_adds(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [{"code": v.code, "name": v.name, "kind": v.kind, "description": v.description, "categories": v.categories,
             "basis": v.basis, "cost_rate": v.cost_rate, "value_rate": v.value_rate,
             "warranty_extension_months": v.warranty_extension_months} for v in db.scalars(select(ValueAdd))]


@router.get("/catalog/tiers")
def tiers(db: Session = Depends(get_db)) -> dict[str, list[dict[str, float]]]:
    out: dict[str, list[dict[str, float]]] = {}
    for t in db.scalars(select(PriceTier).order_by(PriceTier.category, PriceTier.min_qty)):
        out.setdefault(t.category, []).append({"min_qty": t.min_qty, "discount_pct": t.discount_pct})
    return out


# --------------------------------------------------------------------------- market


@router.get("/market/competitors")
def competitors() -> list[dict[str, Any]]:
    try:
        return MarketClient().competitors()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="The competitor market service is unavailable") from exc


@router.get("/market/offers")
def market_offers(sku: str, country: str = "IN", quantity: int = Query(default=1, ge=1), db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.sku == sku))
    if p is None:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        resp = MarketClient().batch_offers(country.upper(), [(p.mpn, quantity)])
    except MarketUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    from app.intel.sources import market_view

    merged, _ = market_view(db, [(p.mpn, quantity)], resp.offers, load_json("pricing_policy.json"))
    offers = []
    for o in merged.get(p.mpn, []):
        try:
            base = fx.convert(o["unit_price"], o["currency"], "INR")
        except UnknownCurrency:
            continue
        offers.append({**o, "unit_price_base": round(base, 2), "vs_cost_pct": round(100 * (base / p.unit_cost - 1), 2)})
    return {"product": _product(p), "country": country.upper(), "quantity": quantity, "offers": offers,
            "endpoint": resp.endpoint, "latency_ms": resp.latency_ms}


# --------------------------------------------------------------------------- finance


@router.get("/finance/fx")
def fx_snapshot() -> dict[str, Any]:
    return fx.snapshot()


@router.post("/finance/fx/refresh")
def fx_refresh() -> dict[str, Any]:
    return fx.refresh()


@router.get("/finance/tax-rules")
def tax_rules(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [{"country": t.country, "region": t.region, "tax_category": t.tax_category, "name": t.name,
             "rate_pct": t.rate_pct, "components": t.components}
            for t in db.scalars(select(TaxRule).order_by(TaxRule.country, TaxRule.region))]


class TaxPreview(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    region: str | None = None
    tax_id: str | None = None
    incoterm: str | None = None


@router.post("/finance/tax-preview")
def tax_preview(body: TaxPreview) -> dict[str, Any]:
    c = load_json("company.json")
    info = countries().get(body.country.upper())
    ctx = TaxContext(c["country"], c["region"], body.country.upper(), body.region, bool(info and info.eu), body.tax_id,
                     body.incoterm)
    return assess(ctx, {"goods_standard", "software", "services"}).as_dict()


@router.get("/finance/countries")
def country_list() -> list[dict[str, Any]]:
    return [{"code": c.code, "name": c.name, "currency": c.currency, "eu": c.eu, "regions": sorted(c.regions)}
            for c in sorted(countries().values(), key=lambda c: c.name)]


# --------------------------------------------------------------------------- models & knowledge


@router.get("/models")
def models(db: Session = Depends(get_db)) -> dict[str, Any]:
    deals = list(db.scalars(select(DealHistory)))
    ks = knowledge_store()
    return {
        **registry.describe(),
        "deal_history": {"deals": len(deals), "win_rate": round(sum(d.won for d in deals) / len(deals), 4) if deals else None},
        "knowledge_base": {"sections": len(ks.sections.documents), "sentences": len(ks.sentences.documents),
                           "sources": sorted({d.meta["source"] for d in ks.sections.documents})},
        "catalogue_index": {"documents": len(catalogue_store().index.documents)},
    }


@router.post("/models/retrain")
def retrain() -> dict[str, Any]:
    return registry.retrain()


@router.get("/knowledge/search")
def knowledge_search(q: str = Query(min_length=2), k: int = Query(default=5, ge=1, le=10)) -> dict[str, Any]:
    ks = knowledge_store()
    sections = ks.sections.search(q, k=k)
    return {
        "query": q,
        "sections": [{**h.as_dict(), "text": h.doc.meta["body"]} for h in sections],
        "evidence": [p.as_dict() for p in ks.evidence(q, k=3)],
    }
