"""Regions: the selectable markets that decide currency, tax and procurement conventions.

Tenderdesk is not tied to one country. Two choices drive every regional rule:

* the **operating region** — where the bidding company is registered (country and, where
  tax depends on it, state or province). Set once per workspace; defaults to the company
  profile.
* the **client region** — where the buyer is, chosen by the user for each request. It sets
  the quotation currency and decides between domestic tax and export treatment.

Conventions that exist only in one market (for example India's MSE purchase preference
and the MSMED Act payment limit) apply only when both sides are in that market.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.db.seed import load_json
from app.db.session import session_scope
from app.nlp.gazetteer import countries

AREAS: dict[str, str] = {
    "IN": "Asia Pacific", "SG": "Asia Pacific", "MY": "Asia Pacific", "AU": "Asia Pacific", "NZ": "Asia Pacific",
    "JP": "Asia Pacific", "LK": "Asia Pacific",
    "GB": "Europe", "DE": "Europe", "FR": "Europe", "NL": "Europe", "IE": "Europe", "ES": "Europe", "IT": "Europe",
    "BE": "Europe", "SE": "Europe", "DK": "Europe", "AT": "Europe", "PL": "Europe", "CH": "Europe", "NO": "Europe",
    "AE": "Middle East & Africa", "SA": "Middle East & Africa", "BH": "Middle East & Africa", "OM": "Middle East & Africa",
    "QA": "Middle East & Africa", "ZA": "Middle East & Africa", "KE": "Middle East & Africa",
    "US": "Americas", "CA": "Americas",
}

# Regional procurement conventions, applied only when supplier and buyer share the market.
CONVENTIONS: dict[str, list[str]] = {
    "IN": ["GST split into CGST + SGST within a state, IGST between states",
           "MSE purchase preference (L1 + 15%, 25% of quantity)",
           "MSMED Act: payment to MSE suppliers within 45 days",
           "EMD exemption for Udyam-registered enterprises"],
    "US": ["Sales tax set by the delivery state; services and software often exempt"],
    "CA": ["GST, HST or GST + PST/QST by province"],
}

SETTING_KEY = "operating_region"


@dataclass(frozen=True)
class Place:
    country: str
    region: str | None = None


def tax_name(country: str) -> str:
    rules = [r for r in load_json("tax_rules.json") if r["country"] == country]
    names = sorted({r["name"] for r in rules})
    return " / ".join(names[:2]) if names else "No indirect tax rule configured"


def catalogue() -> list[dict[str, Any]]:
    """Every selectable region with its currency, tax and conventions."""
    out = []
    for c in sorted(countries().values(), key=lambda c: (AREAS.get(c.code, "Other"), c.name)):
        out.append({"code": c.code, "name": c.name, "currency": c.currency, "eu": c.eu,
                    "area": AREAS.get(c.code, "Other"), "regions": sorted(c.regions), "tax": tax_name(c.code),
                    "conventions": CONVENTIONS.get(c.code, [])})
    return out


def validate(place: Place) -> Place:
    """Normalise a place, raising ``ValueError`` for an unknown country or state."""
    code = (place.country or "").upper()
    info = countries().get(code)
    if info is None:
        raise ValueError(f"Unknown country code '{place.country}'")
    region = place.region or None
    if region is not None and region not in info.regions:
        raise ValueError(f"'{region}' is not a listed state or province of {info.name}")
    return Place(code, region)


def currency_of(country: str) -> str | None:
    info = countries().get(country.upper())
    return info.currency if info else None


def operating_region() -> Place:
    """The workspace's operating region (setting, else the company profile)."""
    from app.db.models import WorkspaceSetting

    with session_scope() as s:
        row = s.scalar(select(WorkspaceSetting).where(WorkspaceSetting.key == SETTING_KEY))
        value = dict(row.value) if row is not None else None
    if value:
        return Place(value["country"], value.get("region"))
    company = load_json("company.json")
    return Place(company["country"], company.get("region"))


def set_operating_region(place: Place) -> Place:
    from app.db.models import WorkspaceSetting

    place = validate(place)
    with session_scope() as s:
        row = s.get(WorkspaceSetting, SETTING_KEY)
        value = {"country": place.country, "region": place.region}
        if row is None:
            s.add(WorkspaceSetting(key=SETTING_KEY, value=value))
        else:
            row.value = value
    return place


def company_profile() -> dict[str, Any]:
    """The company profile with the workspace's operating region applied."""
    company = copy.deepcopy(load_json("company.json"))
    place = operating_region()
    company["country"], company["region"] = place.country, place.region
    return company


def same_market(supplier_country: str | None, client_country: str | None, market: str) -> bool:
    return supplier_country == market and client_country == market
