"""Competitor intelligence adapters.

Every source of competitor prices is an *adapter* that turns its input into
``PriceObservation`` rows: dated, attributed to a competitor and to a source, so
every number the strategy agent uses can be traced back to where it came from.

Adapters
--------
* ``feed``   – the market price feed (the mock market API, or a real
               subscription behind the same contract); queried live per bid.
* ``quotes`` – a CSV or Excel sheet of quotes collected by the sales team from
               marketplaces, brand stores and distributors.
* ``awards`` – public award results (GeM, state e-tender portals): who won, at
               what unit price. The winner may be a competitor the company has
               never listed.
* ``web``    – a saved product page (HTML). Prices are read from schema.org
               markup, price meta tags or visible "₹ 12,345" text; no request is
               made to the site by the system.

``market_view`` merges live feed offers with stored observations for the lines
of a bid: per competitor and product the freshest observation wins, old ones
age out, and each offer carries its source and date.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import PriceObservation, Product
from app.imports.tabular import map_headers, parse_int, parse_months, parse_number, read_table

ADAPTERS = {
    "feed": "Market price feed",
    "quotes": "Collected quotes",
    "awards": "Public award results",
    "web": "Saved web page",
}

QUOTE_FIELDS = {
    "observed_on": ["observed on", "date", "quote date", "observed", "collected on"],
    "competitor": ["competitor", "seller", "vendor", "supplier", "store", "dealer"],
    "competitor_id": ["competitor id"],
    "mpn": ["mpn", "part number", "part no", "model", "model number"],
    "product": ["product", "item", "item name", "description"],
    "quantity": ["quantity", "qty", "moq"],
    "unit_price": ["unit price", "price", "rate", "quoted price", "offer price"],
    "currency": ["currency"],
    "warranty_months": ["warranty", "warranty months"],
    "source": ["source", "channel"],
    "reference": ["reference", "url", "link", "quote ref", "store address"],
    "collected_by": ["collected by", "sales person", "owner"],
}
AWARD_FIELDS = {
    "observed_on": ["awarded on", "award date", "date", "contract date"],
    "competitor": ["winner", "awarded to", "l1 bidder", "successful bidder", "seller"],
    "mpn": ["mpn", "part number", "model"],
    "product": ["product", "item", "item description", "description"],
    "quantity": ["quantity", "qty"],
    "unit_price": ["unit price", "l1 unit price", "rate", "price"],
    "currency": ["currency"],
    "reference": ["reference", "contract no", "bid number", "gem contract", "tender no"],
    "portal": ["portal", "source"],
    "buyer": ["buyer", "organisation", "department"],
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48]


def _date(value: str) -> datetime | None:
    value = (value or "").strip()
    for candidate in (value, value[:10]):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _resolve_mpn(db: Session, mpn: str, product: str) -> str | None:
    """Tie an observation to a catalogue MPN: exact MPN, then SKU, then catalogue search on the name."""
    if mpn:
        p = db.scalar(select(Product).where(Product.mpn == mpn)) or db.scalar(select(Product).where(Product.sku == mpn))
        if p is not None:
            return p.mpn
    if product:
        from app.rag.stores import catalogue_store

        store = catalogue_store()
        hits = store.search(product, k=1)
        if hits and hits[0].score >= 0.45:
            return store.products[hits[0].doc.id].mpn
    return mpn or None


def _our_names() -> set[str]:
    from app.db.seed import load_json

    c = load_json("company.json")
    return {slug(c["name"]), slug(c["short_name"])}


def _known_competitors() -> dict[str, str]:
    from app.market.service import market

    return {slug(c["name"]): c["id"] for c in market()["competitors"]} | {c["id"]: c["id"] for c in market()["competitors"]}


def ingest_table(db: Session, adapter: str, filename: str, data: bytes, replace: bool = False) -> dict[str, Any]:
    """Load a quotes or awards sheet into observations."""
    table = read_table(filename, data)
    fields = QUOTE_FIELDS if adapter == "quotes" else AWARD_FIELDS
    mapping = map_headers(table.headers, fields)
    if replace:
        db.execute(delete(PriceObservation).where(PriceObservation.adapter == adapter))
    known, ours = _known_competitors(), _our_names()
    added, skipped, issues = 0, 0, []
    for i, row in enumerate(table.rows, start=table.header_row + 1):
        g = lambda f: mapping.get(row, f)  # noqa: E731
        price, when, who = parse_number(g("unit_price")), _date(g("observed_on")), g("competitor")
        if price is None or when is None or not who:
            skipped += 1
            issues.append({"row": i, "message": "Needs a date, a competitor and a unit price."})
            continue
        comp_id = g("competitor_id") or known.get(slug(who)) or slug(who)
        if slug(who) in ours:
            skipped += 1  # our own past awards are not competitor prices
            continue
        mpn = _resolve_mpn(db, g("mpn"), g("product"))
        if not mpn:
            skipped += 1
            issues.append({"row": i, "message": f"Could not match '{g('product')}' to a catalogue item."})
            continue
        if adapter == "awards":
            source = f"{g('portal') or 'Public'} award" + (f" – {g('buyer')}" if g("buyer") else "")
        else:
            source = g("source") or "Collected quote"
        db.add(PriceObservation(
            competitor_id=comp_id, competitor=who, mpn=mpn, product=g("product") or None, unit_price=price,
            currency=(g("currency") or "INR").upper()[:3], quantity=parse_int(g("quantity")) or 1,
            warranty_months=parse_months(g("warranty_months")) if g("warranty_months") else None, observed_on=when,
            adapter=adapter, source=source[:80], reference=(g("reference") or None), collected_by=g("collected_by") or None,
        ))
        added += 1
    return {"adapter": adapter, "filename": filename, "added": added, "skipped": skipped, "issues": issues[:50],
            "mapping": mapping.fields}


# --------------------------------------------------------------------------- web page adapter


class _PriceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self.text: list[str] = []
        self.title = ""
        self._in: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in = "jsonld"
        elif tag == "title":
            self._in = "title"
        elif tag in ("script", "style"):
            self._in = "skip"
        if tag == "meta":
            key = a.get("property") or a.get("itemprop") or a.get("name") or ""
            if a.get("content"):
                self.meta[key.lower()] = a["content"]
        if a.get("itemprop") in ("price", "name") and a.get("content"):
            self.meta[f"itemprop:{a['itemprop']}"] = a["content"]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title"):
            self._in = None

    def handle_data(self, data):
        if self._in == "jsonld":
            self.jsonld.append(data)
        elif self._in == "title":
            self.title += data
        elif self._in is None and data.strip():
            self.text.append(data.strip())


def _walk_offers(obj: Any):
    if isinstance(obj, dict):
        if obj.get("@type") in ("Offer", "AggregateOffer") and (obj.get("price") or obj.get("lowPrice")):
            yield obj
        for v in obj.values():
            yield from _walk_offers(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_offers(v)


def extract_web_price(html: str) -> dict[str, Any]:
    """Find a product name and price in a saved product page."""
    p = _PriceParser()
    p.feed(html)
    name, price, currency, how = None, None, "INR", None
    for block in p.jsonld:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                name = name or item.get("name")
        for offer in _walk_offers(data):
            price = parse_number(str(offer.get("price") or offer.get("lowPrice")))
            currency = offer.get("priceCurrency", currency)
            how = "schema.org offer"
            break
        if price:
            break
    if price is None:
        for key in ("product:price:amount", "og:price:amount", "itemprop:price", "price"):
            if key in p.meta:
                price, how = parse_number(p.meta[key]), f"meta {key}"
                currency = p.meta.get("product:price:currency", p.meta.get("og:price:currency", currency))
                break
    if price is None:
        text = " ".join(p.text)
        m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
        if m:
            price, how = parse_number(m.group(1)), "visible price text"
    name = name or p.meta.get("og:title") or p.meta.get("itemprop:name") or p.title.strip() or None
    return {"name": name, "price": price, "currency": (currency or "INR").upper()[:3], "method": how}


def ingest_web_page(db: Session, competitor: str, html: str, url: str | None, observed_on: date | None = None,
                    mpn: str | None = None) -> dict[str, Any]:
    found = extract_web_price(html)
    if not found["price"]:
        return {"added": 0, "message": "No price found on the page.", **found}
    resolved = _resolve_mpn(db, mpn or "", found["name"] or "")
    if not resolved:
        return {"added": 0, "message": f"Could not match '{found['name']}' to a catalogue item.", **found}
    comp_id = _known_competitors().get(slug(competitor), slug(competitor))
    when = datetime.combine(observed_on or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    db.add(PriceObservation(competitor_id=comp_id, competitor=competitor, mpn=resolved, product=found["name"],
                            unit_price=found["price"], currency=found["currency"], observed_on=when, adapter="web",
                            source="Saved web page", reference=url))
    return {"added": 1, "mpn": resolved, **found}


# --------------------------------------------------------------------------- merge for a bid


def market_view(db: Session, lines: list[tuple[str, int]], feed: dict[str, list[dict]], policy: dict[str, Any],
                today: date | None = None) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Combine live feed offers with stored observations, freshest per competitor and product."""
    from app.market.service import market

    today = today or date.today()
    max_age = int(policy.get("observation_max_age_days", 180))
    base_rel = policy.get("observation_source_reliability", {})
    comps = {c["id"]: c for c in market()["competitors"]}
    cutoff = datetime.combine(today - timedelta(days=max_age), datetime.min.time(), tzinfo=timezone.utc)
    mpns = [m for m, _ in lines]
    stored = list(db.scalars(select(PriceObservation).where(PriceObservation.mpn.in_(mpns),
                                                            PriceObservation.observed_on >= cutoff)
                             .order_by(PriceObservation.observed_on.desc())))
    used = {"feed": 0, "quotes": 0, "awards": 0, "web": 0}
    out: dict[str, list[dict]] = {}
    for mpn, qty in lines:
        merged: dict[str, dict] = {}
        for o in feed.get(mpn, []):
            merged[o["competitor_id"]] = {**o, "source": o.get("source") or ADAPTERS["feed"],
                                          "observed_on": (o.get("observed_at") or today.isoformat())[:10]}
        for ob in stored:
            if ob.mpn != mpn:
                continue
            when = ob.observed_on.date() if isinstance(ob.observed_on, datetime) else ob.observed_on
            prior = merged.get(ob.competitor_id)
            if prior is not None and prior["observed_on"] >= when.isoformat():
                continue  # the feed or a newer observation already covers this competitor
            comp = comps.get(ob.competitor_id, {})
            age = (today - when).days
            # Older observations are trusted less; a quote from six months ago is a weak signal.
            rel = min(comp.get("reliability", 1.0), 1.0) * base_rel.get(ob.adapter, 0.8) * (1 - 0.35 * age / max_age)
            lo, hi = comp.get("lead_time_days", [10, 21])
            merged[ob.competitor_id] = {
                "competitor_id": ob.competitor_id, "competitor": ob.competitor,
                "positioning": comp.get("positioning") or ("Past award winner" if ob.adapter == "awards" else "Reseller"),
                "mpn": mpn, "unit_price": ob.unit_price, "currency": ob.currency,
                "warranty_months": ob.warranty_months or comp.get("default_warranty_months", 12),
                "lead_time_days": (lo + hi) // 2, "in_stock": True, "reliability": round(max(0.0, rel), 3),
                "bundle": comp.get("bundle"), "promotion": None, "source": ob.source, "observed_on": when.isoformat(),
                "adapter": ob.adapter,
            }
        for o in merged.values():
            used[o.get("adapter", "feed")] = used.get(o.get("adapter", "feed"), 0) + 1
        out[mpn] = sorted(merged.values(), key=lambda o: o["unit_price"])
    return out, used


# --------------------------------------------------------------------------- seeding


def seed_observations(db: Session) -> None:
    """Load the company's bundled quote and award sheets on first start."""
    if db.scalar(select(PriceObservation.id).limit(1)) is not None:
        return
    for adapter, name in (("quotes", "competitor_quotes.csv"), ("awards", "award_history.csv")):
        path = get_settings().company_dir / name
        if path.exists():
            ingest_table(db, adapter, name, path.read_bytes())


def observation_dict(o: PriceObservation) -> dict[str, Any]:
    return {"id": o.id, "competitor_id": o.competitor_id, "competitor": o.competitor, "mpn": o.mpn, "product": o.product,
            "unit_price": o.unit_price, "currency": o.currency, "quantity": o.quantity,
            "warranty_months": o.warranty_months, "observed_on": o.observed_on.date().isoformat(), "adapter": o.adapter,
            "source": o.source, "reference": o.reference, "collected_by": o.collected_by}


def csv_template(adapter: str) -> str:
    fields = QUOTE_FIELDS if adapter == "quotes" else AWARD_FIELDS
    buf = io.StringIO()
    csv.writer(buf).writerow([v[0] for v in fields.values()])
    return buf.getvalue()
