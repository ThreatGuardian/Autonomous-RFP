"""Localisation Agent — converts the priced quote into the client's currency and applies tax."""

from __future__ import annotations

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import CompetitiveAnalysis, InternalPricing, Localisation, LocalisedLine, ParsedRfp, TaxLine
from app.db.seed import load_json
from app.finance.currency import fx
from app.finance.money import fmt
from app.finance.tax import TaxContext, assess


class LocalisationAgent(Agent):
    stage = "localisation"
    name = "Currency & Tax Agent"
    produces = "localisation"
    consumes = ("parsed", "costing", "strategy")

    def run(self, ctx: PipelineContext, log: StageLog) -> Localisation:
        parsed: ParsedRfp = ctx.require("parsed")
        costing: InternalPricing = ctx.require("costing")
        strategy: CompetitiveAnalysis = ctx.require("strategy")
        policy = load_json("pricing_policy.json")
        base = strategy.base_currency
        ccy = (ctx.overrides or {}).get("currency") or parsed.currency.code
        decimals = policy["currency_decimals"].get(ccy, 2)

        q = fx.quote(base, ccy)
        buffer = 0.0 if ccy == base else float((ctx.overrides or {}).get("fx_buffer_pct", policy["fx_buffer_pct"]))
        eff = q.rate * (1 + buffer / 100)
        log.info("Exchange rate applied", pair=f"{base}/{ccy}", rate=round(q.rate, 6), buffer_pct=buffer,
                 effective=round(eff, 6), source=q.source, as_of=q.as_of, stale=q.stale)
        if q.stale:
            log.warn("Exchange rate is from a fallback source; confirm before sending", source=q.source)

        tax_cat = {l.line_no: l.tax_category for l in costing.lines}
        desc = {l.line_no: l.description for l in costing.lines}
        company = ctx.company
        assessment = assess(
            TaxContext(company["country"], company["region"], parsed.client.country or company["country"],
                       parsed.client.region, parsed.client.is_eu, parsed.client.tax_id, parsed.terms.incoterm),
            set(tax_cat.values()) or {"goods_standard"},
        )
        log.decision("Tax regime determined", jurisdiction=assessment.jurisdiction, regime=assessment.summary,
                     rates={k: v.rate_pct for k, v in assessment.treatments.items()}, notes=assessment.notes)

        lines: list[LocalisedLine] = []
        breakdown: dict[tuple[str, float], float] = {}
        bundled_value = 0.0
        for p in strategy.lines:
            unit = round(p.unit_price * eff, decimals)
            net = round(unit * p.quantity, decimals)
            t = assessment.treatments[tax_cat[p.line_no]]
            taxes = []
            for comp in t.components if t.charged else []:
                amt = round(net * comp["rate_pct"] / 100, decimals)
                taxes.append(TaxLine(name=comp["name"], rate_pct=comp["rate_pct"], amount=amt))
                key = (comp["name"], comp["rate_pct"])
                breakdown[key] = breakdown.get(key, 0.0) + amt
            tax_total = round(sum(x.amount for x in taxes), decimals)
            bvalue = round(p.bundle.total_value * eff, decimals) if p.bundle else None
            bundled_value += bvalue or 0.0
            lines.append(LocalisedLine(
                line_no=p.line_no, sku=p.sku, name=p.name, description=desc[p.line_no], quantity=p.quantity,
                unit=p.unit, unit_price=unit, net=net, tax_regime=t.regime, tax_rate_pct=t.rate_pct, taxes=taxes,
                tax_total=tax_total, gross=round(net + tax_total, decimals), tax_note=t.note,
                bundle_name=p.bundle.name if p.bundle else None, bundle_value=bvalue,
            ))
        subtotal = round(sum(l.net for l in lines), decimals)
        tax_total = round(sum(l.tax_total for l in lines), decimals)
        grand = round(subtotal + tax_total, decimals)
        tax_lines = [TaxLine(name=n, rate_pct=r, amount=round(a, decimals)) for (n, r), a in sorted(breakdown.items()) if a or r == 0]
        log.info("Quote localised", currency=ccy, subtotal=subtotal, tax=tax_total, total=grand)
        return Localisation(
            currency=ccy, base_currency=base, fx_rate=q.rate, fx_buffer_pct=buffer, fx_effective_rate=eff,
            fx_source=q.source, fx_as_of=q.as_of, fx_stale=q.stale, decimals=decimals,
            jurisdiction=assessment.jurisdiction, tax_summary=assessment.summary, tax_notes=assessment.notes,
            lines=lines, subtotal=subtotal, tax_breakdown=tax_lines, tax_total=tax_total, grand_total=grand,
            grand_total_base=round(grand / eff, 2), bundled_value=round(bundled_value, decimals),
        )

    def summarize(self, output: Localisation) -> str:  # type: ignore[override]
        fx_note = "" if output.currency == output.base_currency else (
            f"; 1 {output.currency} = {1 / output.fx_effective_rate:,.4f} {output.base_currency} ({output.fx_source})")
        return f"Total {fmt(output.grand_total, output.currency, output.decimals)} — {output.tax_summary}{fx_note}."
