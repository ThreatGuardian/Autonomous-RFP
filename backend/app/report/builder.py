"""Editable bid report: a structured document built from the pipeline's results.

The report is a list of sections, each a list of typed blocks. The editor,
the editing assistant and both exporters (PDF, Word) work on this one model,
so an edit made by typing, by instruction or by a panel control appears
identically everywhere.

Block types::

    lead       {"text"}                          display sentence
    paragraph  {"text"}
    bullets    {"items": [str]}
    kpis       {"items": [{"value", "label"}]}
    bars       {"items": [{"label", "note", "value": 0..1, "display"}]}
    table      {"header": [str], "rows": [[str]]}
    callout    {"text", "tone": "good"|"warn"|"bad"|"neutral"}
    note       {"text"}                          small print
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.agents.messages import (
    CompetitiveAnalysis, ComplianceReport, Localisation, ParsedRfp, Proposal,
)
from app.finance.money import fmt
from app.services.report_renderer import STRATEGY_NOTES, _key_lines, _pick_reason, _risks, _verdict

SECTION_KEYS = ("summary", "award", "lines", "decisions", "economics", "compliance", "delivery", "risks", "next", "method")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def block(type_: str, **data: Any) -> dict[str, Any]:
    return {"id": new_id(), "type": type_, **data}


def section(key: str, title: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": new_id(), "key": key, "title": title, "hidden": False, "blocks": blocks}


def build_sections(company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation, proposal: Proposal,
                   compliance: ComplianceReport | None, only: str | None = None) -> list[dict[str, Any]]:
    """Every generated section, or just the one named by ``only`` (used to refresh a section)."""
    base = strat.base_currency
    mb = lambda v: fmt(v, base, 0)  # noqa: E731
    mc = lambda v: fmt(v, loc.currency, loc.decimals)  # noqa: E731
    client = parsed.client.name or "the client"
    out: list[dict[str, Any]] = []

    def want(key: str) -> bool:
        return only is None or only == key

    if want("summary"):
        verdict, advice = _verdict(strat, compliance)
        vd = strat.strategy_counts.get("Value differentiation", 0)
        text = (f"We have priced {len(strat.lines)} lines for {client}"
                f"{', ' + (parsed.client.city or parsed.client.country_name) if (parsed.client.city or parsed.client.country_name) else ''}. "
                f"{strat.below_cost_competitors} line(s) meet competitors priced below our own landed cost"
                + (f"; on {vd} line(s) we hold price and compete on value, including services worth {mc(loc.bundled_value)} at no charge. "
                   if vd else ". ")
                + f"Tax treatment: {loc.tax_summary}; the quotation is issued in {loc.currency}.")
        out.append(section("summary", "Summary", [
            block("callout", text=f"{verdict}. {advice}", tone="bad" if verdict == "Do not bid" else "good" if verdict == "Strong bid" else "warn"),
            block("lead", text=f"A {mc(loc.grand_total)} offer at {strat.margin_pct:.1f}% gross margin, with a "
                               f"{100 * strat.win_probability:.0f}% modelled chance of winning."),
            block("paragraph", text=text),
            block("kpis", items=[
                {"value": mc(loc.grand_total), "label": "quotation value"},
                {"value": f"{strat.margin_pct:.1f}%", "label": "gross margin"},
                {"value": f"{100 * strat.win_probability:.0f}%", "label": "win probability"},
                {"value": mb(strat.expected_profit), "label": "expected profit"},
            ]),
        ]))

    award = strat.award
    if want("award") and award is not None:
        blocks = [block("callout", text=award.recommendation, tone="good" if award.recommendation.startswith("Submit") else "warn"),
                  block("bullets", items=list(award.reasons))]
        rows = [[o.label, mb(o.total), f"{o.margin_pct:.1f}%", o.outcome] for o in award.options]
        blocks.append(block("table", header=["Option", "Bid total", "Margin", "Outcome"], rows=rows))
        if award.competitors:
            bars = [{"label": c["name"], "note": f"{c['coverage_pct']:.0f}% of items quoted", "value": 0.0, "display": mb(c["total"])}
                    for c in award.competitors] + [{"label": "Our bid", "note": "as priced", "value": 0.0, "display": mb(award.our_total)}]
            top = max([c["total"] for c in award.competitors] + [award.our_total])
            for b, total in zip(bars, [c["total"] for c in award.competitors] + [award.our_total]):
                b["value"] = round(total / top, 4)
            blocks.append(block("bars", items=sorted(bars, key=lambda b: b["value"])))
        label = {"L1": "lowest price (L1)", "QCBS": "quality and cost (QCBS)", "Weighted": "weighted evaluation"}[award.rule]
        out.append(section("award", f"Award position — {label}", blocks))

    if want("lines"):
        out.append(section("lines", "Win probability by line", [
            block("bars", items=[{"label": l.name, "note": l.strategy.lower(), "value": l.win_probability,
                                  "display": f"{100 * l.win_probability:.0f}"} for l in sorted(strat.lines, key=lambda l: -l.revenue)]),
            block("note", text="Bars show the modelled chance of winning each line at the recommended price and terms, ordered by line value."),
        ]))

    if want("decisions"):
        items = []
        for line in _key_lines(strat):
            best = line.market.best
            fact = f"our price {mb(line.unit_price)}" + (f", lowest rival {best.competitor} at {mb(best.unit_price_base)}" if best else "")
            items.append(f"{line.name} × {line.quantity:,}: {line.headline.lower()} ({fact}). {_pick_reason(line)}")
        out.append(section("decisions", "Key pricing decisions", [block("bullets", items=items)]))

    if want("economics"):
        offers = sum(l.market.count for l in strat.lines)
        out.append(section("economics", "Margin structure", [
            block("kpis", items=[
                {"value": mb(strat.cost), "label": "landed cost"},
                {"value": mb(strat.bundle_cost), "label": "services included"},
                {"value": mb(strat.margin), "label": "gross margin"},
                {"value": str(offers), "label": "competitor offers analysed"},
            ]),
            block("bullets", items=[f"{name}: {count} line(s) — {STRATEGY_NOTES.get(name, '')}."
                                    for name, count in sorted(strat.strategy_counts.items(), key=lambda kv: -kv[1])]),
        ]))

    tender = parsed.document
    if want("compliance") and compliance is not None and tender is not None and tender.long_form:
        blocks = [
            block("callout", text=f"{compliance.recommendation}: {compliance.summary}",
                  tone="bad" if compliance.recommendation == "Do not bid" else "warn" if compliance.recommendation != "Bid" else "good"),
            block("kpis", items=[
                {"value": compliance.eligibility_verdict.split()[0], "label": "eligibility"},
                {"value": f"{compliance.mandatory_met}/{compliance.mandatory_total}", "label": "mandatory clauses met"},
                {"value": str(compliance.counts.get("Deviation", 0)), "label": "deviations"},
                {"value": f"{tender.pages} pp", "label": f"{len(tender.sections)} sections read"},
            ]),
        ]
        if compliance.eligibility:
            blocks.append(block("table", header=["Criterion", "Status", "Our position"],
                                rows=[[e.label, e.status, e.position] for e in compliance.eligibility]))
        exceptions = [i for i in compliance.items if i.status in ("Deviation", "Clarification required")]
        if exceptions:
            blocks.append(block("bullets", items=[f"Clause {i.clause or i.id}: {i.response}" for i in exceptions[:10]]))
        if compliance.benefits:
            blocks.append(block("bullets", items=list(compliance.benefits)))
        out.append(section("compliance", "Tender compliance", blocks))

    if want("delivery"):
        rows = [[f"Day {m.day}", m.label, m.detail] for m in proposal.milestones]
        blocks = [block("table", header=["When", "Milestone", "Detail"], rows=rows)]
        if parsed.terms.delivery_days and proposal.milestones:
            done = proposal.milestones[-1].day
            blocks.append(block("note", text=f"Requested completion within {parsed.terms.delivery_days} days; planned completion day {done}."))
        out.append(section("delivery", "Delivery roadmap", blocks))

    if want("risks"):
        items = [f"{r.title} — {r.detail}" for r in (compliance.risks if compliance else [])] + _risks(parsed, strat, loc)
        out.append(section("risks", "Risks to weigh", [block("bullets", items=items or ["No material risks identified."])]))

    if want("next"):
        steps: list[str] = []
        if compliance is not None:
            prebid = next((d for d in (tender.key_dates if tender else []) if d.key == "prebid"), None)
            if prebid and compliance.recommendation != "Bid":
                steps.append(f"Raise the deviations and eligibility questions at the pre-bid meeting on "
                             f"{date.fromisoformat(prebid.date):%d %B %Y}.")
            obtain = [c.name for c in compliance.checklist if c.status == "To obtain"]
            if obtain:
                steps.append(f"Obtain {len(obtain)} document(s) from third parties, starting with: {obtain[0]}.")
        steps += ["Review the flagged lines and confirm or adjust the recommended prices.",
                  "Approve the quotation to issue the final documents without the draft marking."]
        if parsed.due_date:
            steps.append(f"Submit before {date.fromisoformat(parsed.due_date):%d %B %Y}.")
        out.append(section("next", "Next steps", [block("bullets", items=steps)]))

    if want("method"):
        out.append(section("method", "How these figures were produced", [block("note", text=(
            "Win probabilities come from a logistic model trained on historical bid outcomes and competitor prices from the "
            f"market intelligence feed; they indicate relative likelihood, not certainty. Prices respect the minimum-margin "
            f"policy for every product. Exchange rate: {loc.fx_source}, as of {loc.fx_as_of}."))]))
    return out


def build_document(company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation, proposal: Proposal,
                   compliance: ComplianceReport | None) -> dict[str, Any]:
    meta = [x for x in [
        f"Ref {parsed.client_reference}" if parsed.client_reference else None,
        f"Due {date.fromisoformat(parsed.due_date):%d %B %Y}" if parsed.due_date else None,
        f"Prepared {date.fromisoformat(proposal.issue_date):%d %B %Y}",
        f"Version {proposal.version}",
    ] if x]
    return {
        "title": parsed.client.name or parsed.title,
        "subtitle": "  ·  ".join(meta),
        "quote_number": proposal.quote_number,
        "proposal_version": proposal.version,
        "sections": build_sections(company, parsed, strat, loc, proposal, compliance),
        "edited": False,
        "stale": False,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "history": [],
        "redo": [],
        "chat": [],
    }


def figures(parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation, compliance: ComplianceReport | None) -> dict[str, str]:
    """Named figures the assistant can insert ("add the total price to the summary")."""
    base = strat.base_currency
    out = {
        "total price": f"Total offer value is {fmt(loc.grand_total, loc.currency, loc.decimals)} including {loc.tax_summary}.",
        "net price": f"Net value before tax is {fmt(loc.subtotal, loc.currency, loc.decimals)}.",
        "tax": f"Taxes amount to {fmt(loc.tax_total, loc.currency, loc.decimals)} ({loc.tax_summary}).",
        "margin": f"Gross margin is {strat.margin_pct:.1f}% ({fmt(strat.margin, base, 0)}).",
        "win probability": f"The modelled chance of winning is {100 * strat.win_probability:.0f}%.",
        "expected profit": f"Expected gross profit is {fmt(strat.expected_profit, base, 0)}.",
        "services": f"Services worth {fmt(loc.bundled_value, loc.currency, loc.decimals)} are included at no charge.",
        "deadline": f"The submission deadline is {date.fromisoformat(parsed.due_date):%d %B %Y}." if parsed.due_date else "",
        "competitors": f"{sum(l.market.count for l in strat.lines)} competitor offers were analysed; "
                       f"{strat.below_cost_competitors} line(s) face rivals below our landed cost.",
    }
    if strat.award and strat.award.lowest_total:
        out["l1"] = (f"The lowest estimated rival bid is {strat.award.lowest_competitor} at {fmt(strat.award.lowest_total, base, 0)}; "
                     f"we are {strat.award.gap_pct:+.1f}% against it.")
    if compliance is not None:
        out["compliance"] = f"{compliance.mandatory_met} of {compliance.mandatory_total} mandatory clauses are met."
        out["eligibility"] = f"Eligibility: {compliance.eligibility_verdict}."
    return {k: v for k, v in out.items() if v}
