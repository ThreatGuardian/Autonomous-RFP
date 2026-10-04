"""Indirect-tax determination by jurisdiction, supply type and product tax category.

The supplier's operating region and the client region (both chosen in the app) decide
which rules apply. Rates come from ``tax_rules.json``.

Rules implemented
-----------------
* **Domestic supply** – the country's VAT / GST / sales tax for the client's state or
  province where it differs. India additionally splits GST into CGST + SGST within the
  supplier's state and charges IGST between states.
* **Export, non-DDP incoterms** – zero-rated export of goods and services; destination
  taxes are borne by the importer and shown for information (under a Letter of
  Undertaking when exporting from India).
* **Export, DDP** – the supplier is importer of record, so destination indirect
  tax (VAT/GST/sales tax, with regional and category brackets) is charged.
* **Cross-border B2B services and licences** – where the client provides a tax
  registration, destination VAT/GST on services is reverse-charged to the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.db.models import TaxRule
from app.db.session import session_scope

NON_DDP_EXPORT_TERMS = {"EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU"}
SERVICE_CATEGORIES = {"services", "software"}


@dataclass
class TaxTreatment:
    tax_category: str
    regime: str
    components: list[dict[str, Any]]
    charged: bool
    note: str | None = None

    @property
    def rate_pct(self) -> float:
        return round(sum(c["rate_pct"] for c in self.components), 4) if self.charged else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"tax_category": self.tax_category, "regime": self.regime, "components": self.components,
                "charged": self.charged, "rate_pct": self.rate_pct, "note": self.note}


@dataclass
class TaxContext:
    supplier_country: str
    supplier_region: str | None
    client_country: str
    client_region: str | None
    client_is_eu: bool
    client_tax_id: str | None
    incoterm: str | None


@dataclass
class TaxAssessment:
    jurisdiction: str
    summary: str
    treatments: dict[str, TaxTreatment] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"jurisdiction": self.jurisdiction, "summary": self.summary, "notes": self.notes,
                "treatments": {k: v.as_dict() for k, v in self.treatments.items()}}


def _lookup(country: str, region: str | None, category: str) -> TaxRule | None:
    with session_scope() as s:
        rules = list(s.scalars(select(TaxRule).where(TaxRule.country == country)))
    for want_region, want_cat in ((region, category), (region, "*"), (None, category), (None, "*")):
        for r in rules:
            if r.region == want_region and r.tax_category == want_cat:
                return r
    return None


def assess(ctx: TaxContext, categories: set[str]) -> TaxAssessment:
    if ctx.client_country == ctx.supplier_country:
        if ctx.supplier_country == "IN":
            return _domestic_india(ctx, categories)
        return _domestic(ctx, categories)
    return _international(ctx, categories)


def _domestic(ctx: TaxContext, categories: set[str]) -> TaxAssessment:
    """Domestic supply outside India: the destination rule for the client's country and region."""
    where = ctx.client_country + (f" — {ctx.client_region}" if ctx.client_region else "")
    out = TaxAssessment(jurisdiction=where, summary="Domestic supply")
    if ctx.client_country in ("US", "CA") and not ctx.client_region:
        out.notes.append("State or province not selected; regional tax cannot be determined and is excluded.")
    names = set()
    for cat in categories:
        rule = _lookup(ctx.client_country, ctx.client_region, cat)
        if rule is None:
            out.treatments[cat] = TaxTreatment(cat, "No rule", [{"name": "Not determined", "rate_pct": 0.0}], True,
                                               "No tax rule configured for this jurisdiction.")
            continue
        names.add(rule.name)
        note = (f"{cat.replace('_', ' ').capitalize()} is exempt in this jurisdiction."
                if sum(c["rate_pct"] for c in rule.components) == 0 else None)
        out.treatments[cat] = TaxTreatment(cat, rule.name, list(rule.components), True, note)
    if names:
        out.summary = f"Domestic supply — {' / '.join(sorted(names))}"
    return out


def _domestic_india(ctx: TaxContext, categories: set[str]) -> TaxAssessment:
    intra = bool(ctx.client_region) and ctx.client_region == ctx.supplier_region
    notes = []
    if not ctx.client_region:
        notes.append("Client state not identified; inter-state supply (IGST) assumed.")
    out = TaxAssessment(
        jurisdiction=f"India — {ctx.client_region or 'state not identified'}",
        summary="GST intra-state (CGST + SGST)" if intra else "GST inter-state (IGST)",
        notes=notes,
    )
    for cat in categories:
        rule = _lookup("IN", None, cat)
        rate = rule.rate_pct if rule else 18.0
        comps = (
            [{"name": "CGST", "rate_pct": rate / 2}, {"name": "SGST", "rate_pct": rate / 2}] if intra
            else [{"name": "IGST", "rate_pct": rate}]
        )
        out.treatments[cat] = TaxTreatment(cat, out.summary, comps, charged=True)
    return out


def _international(ctx: TaxContext, categories: set[str]) -> TaxAssessment:
    incoterm = (ctx.incoterm or "DDP").upper()
    where = ctx.client_country + (f" — {ctx.client_region}" if ctx.client_region else "")
    ddp = incoterm not in NON_DDP_EXPORT_TERMS
    from_india = ctx.supplier_country == "IN"
    out = TaxAssessment(
        jurisdiction=where,
        summary=(f"Destination taxes charged under {incoterm}" if ddp else
                 f"Zero-rated export under LUT, {incoterm} terms" if from_india else f"Zero-rated export, {incoterm} terms"),
    )
    if ctx.client_country in ("US", "CA") and not ctx.client_region:
        out.notes.append("State or province not selected; regional tax cannot be determined and is excluded.")
    export_component = "IGST (export, LUT)" if from_india else "Zero-rated export"
    for cat in categories:
        rule = _lookup(ctx.client_country, ctx.client_region, cat)
        dest_components = list(rule.components) if rule else []
        dest_name = rule.name if rule else "destination tax"
        if not ddp:
            note = (f"Destination {dest_name} of {sum(c['rate_pct'] for c in dest_components):g}% is payable by the importer."
                    if dest_components else "Destination import taxes are payable by the importer.")
            out.treatments[cat] = TaxTreatment(cat, "Zero-rated export", [{"name": export_component, "rate_pct": 0.0}], True, note)
            continue
        if cat in SERVICE_CATEGORIES and ctx.client_tax_id and ctx.client_country != "US":
            out.treatments[cat] = TaxTreatment(
                cat, "Reverse charge", [{"name": f"{dest_name} (reverse charge)", "rate_pct": 0.0}], True,
                f"Cross-border B2B {cat}: {dest_name} is self-accounted by the client (reverse charge).",
            )
            continue
        if rule is None:
            out.treatments[cat] = TaxTreatment(cat, "No rule", [{"name": "Not determined", "rate_pct": 0.0}], True,
                                               "No tax rule configured for this jurisdiction.")
            continue
        regime = f"{dest_name} {'— ' + ctx.client_region if rule.region else ''}".strip()
        note = None
        if sum(c["rate_pct"] for c in dest_components) == 0:
            note = f"{cat.replace('_', ' ').capitalize()} is exempt in this jurisdiction."
        out.treatments[cat] = TaxTreatment(cat, regime, dest_components, True, note)
    if any(t.regime == "Reverse charge" for t in out.treatments.values()):
        out.notes.append("Services and licences are invoiced without VAT/GST under the reverse-charge mechanism.")
    if not ddp:
        out.notes.append("Exports of goods and services are zero-rated" +
                         (" under a Letter of Undertaking (LUT)." if from_india else "; the importer accounts for import taxes."))
    return out
