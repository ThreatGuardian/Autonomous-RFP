"""Competitive Strategy Agent (the Pricing & Competitor Analysis Agent) — queries the market and sets every price.

The strategy engine prices each line; when the language model is enabled, Claude then
reviews the bid through tools (``app.llm.pricing``) and may move prices within policy.
"""

from __future__ import annotations

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import CompetitiveAnalysis, InternalPricing, MarketOffer, ParsedRfp
from app.db.seed import load_json
from app.db.session import session_scope
from app.finance.currency import UnknownCurrency, fx
from app.finance.money import fmt
from app.intel.sources import ADAPTERS, market_view
from app.llm import pricing as llm_pricing
from app.llm.client import LLMError, get_llm
from app.llm.pricing import PricingDesk
from app.ml.registry import registry
from app.pricing.award import analyse
from app.pricing.strategy import VALUE_DIFFERENTIATION, BuyerContext, StrategyEngine
from app.regions import same_market
from app.services.market_client import MarketClient, MarketUnavailable


def market_ok(available: bool, priced: list) -> bool:
    return available and any(p.market.count for p in priced)


class CompetitiveStrategyAgent(Agent):
    stage = "strategy"
    name = "Competitive Strategy Agent"
    produces = "strategy"
    consumes = ("parsed", "costing")

    def __init__(self, market: MarketClient | None = None) -> None:
        self._market = market

    def run(self, ctx: PipelineContext, log: StageLog) -> CompetitiveAnalysis:
        parsed: ParsedRfp = ctx.require("parsed")
        costing: InternalPricing = ctx.require("costing")
        policy = load_json("pricing_policy.json")
        base = costing.base_currency
        warnings: list[str] = []
        country = parsed.client.country or ctx.company["country"]

        # ---- market intelligence
        offers_by_mpn: dict[str, list[dict]] = {}
        endpoint, latency, available = None, None, True
        try:
            client = self._market or MarketClient()
            resp = client.batch_offers(country, [(l.mpn, l.quantity) for l in costing.lines])
            offers_by_mpn, endpoint, latency = resp.offers, resp.endpoint, resp.latency_ms
            log.info("Market API queried", endpoint=endpoint, country=country, products=len(costing.lines),
                     offers=sum(len(v) for v in offers_by_mpn.values()), latency_ms=latency, attempts=resp.attempts)
        except MarketUnavailable as exc:
            available = False
            log.warn("Market API unavailable", error=str(exc))

        # ---- stored competitor intelligence (collected quotes, public awards, saved pages)
        try:
            with session_scope() as db:
                offers_by_mpn, used = market_view(db, [(l.mpn, l.quantity) for l in costing.lines], offers_by_mpn, policy)
            if any(v for k, v in used.items() if k != "feed"):
                available = True
                log.info("Competitor observations merged", **{ADAPTERS[k]: v for k, v in used.items() if v})
        except Exception as exc:  # observations are an enrichment; never block pricing on them
            log.warn("Stored competitor observations unavailable", error=str(exc))
        if not available:
            warnings.append("Competitor market data unavailable; lines priced at standard price.")

        # ---- buyer context
        weight = parsed.terms.price_weight_pct or (
            policy["lowest_price_award_weight_pct"] if parsed.terms.lowest_price_award else policy["default_price_weight_pct"]
        )
        doc = parsed.document
        method = doc.evaluation.method if doc is not None else "Not stated"
        rule = "L1" if (method == "L1" or (method == "Not stated" and parsed.terms.lowest_price_award)) else \
            "QCBS" if method == "QCBS" else "Weighted"
        buyer = BuyerContext(parsed.client.segment, parsed.client.repeat_customer, float(weight), award=rule)
        log.info("Buyer context", segment=buyer.segment, repeat_customer=buyer.repeat_customer, price_weight_pct=weight,
                 award_rule="lowest compliant bid" if parsed.terms.lowest_price_award else "weighted evaluation")

        engine = StrategyEngine(registry.win_model(), policy, base)
        overrides = (ctx.overrides or {}).get("lines", {})
        priced = []
        offers_by_line: dict[int, list[MarketOffer]] = {}
        below_cost = 0
        for line in costing.lines:
            offers = []
            for o in offers_by_mpn.get(line.mpn, []):
                if o["reliability"] < policy["min_offer_reliability"]:
                    log.info("Offer ignored for low reliability", competitor=o["competitor"], reliability=o["reliability"])
                    continue
                try:
                    in_base = fx.convert(o["unit_price"], o["currency"], base)
                except UnknownCurrency:
                    continue
                offers.append(MarketOffer(**{k: o[k] for k in MarketOffer.model_fields if k in o}, unit_price_base=round(in_base, 2)))
            offers_by_line[line.line_no] = offers
            result = engine.price_line(line, offers, buyer, overrides.get(str(line.line_no)))
            if result.market.best and result.market.best.unit_price_base < line.unit_cost:
                below_cost += 1
            priced.append(result)
            log.decision(
                f"Line {line.line_no}: {result.strategy}",
                sku=line.sku, unit_price=result.unit_price, best_competitor=result.market.best.competitor if result.market.best else None,
                best_price=result.market.min, unit_cost=line.unit_cost, bundle=result.bundle.code if result.bundle else None,
                margin_pct=result.margin_pct, win_probability=result.win_probability,
            )

        agent_summary = None
        llm = get_llm()
        if llm is not None and priced:
            priced, agent_summary = self._agent_review(llm, engine, buyer, costing, offers_by_line, priced, overrides,
                                                       rule, base, log)

        revenue = round(sum(p.revenue for p in priced), 2)
        cost = round(sum(p.cost for p in priced), 2)
        bcost = round(sum(p.bundle_cost for p in priced), 2)
        margin = round(revenue - cost - bcost, 2)
        exp_profit = round(sum(p.expected_profit for p in priced), 2)
        win = round(sum(p.win_probability * p.revenue for p in priced) / revenue, 4) if revenue else 0.0
        counts: dict[str, int] = {}
        for p in priced:
            counts[p.strategy] = counts.get(p.strategy, 0) + 1
        summary = self._summary(priced, revenue, margin, win, below_cost, base)
        profile = ctx.company.get("profile", {})
        facts = {f.key for f in doc.facts} if doc is not None else set()
        award = analyse(
            rule, priced, costing, policy, base,
            # The MSE purchase preference is an Indian public-procurement rule.
            msme=bool(profile.get("msme", {}).get("valid")) and same_market(ctx.company.get("country"), country, "IN"),
            reverse_auction="reverse_auction" in facts,
            technical_weight=doc.evaluation.technical_weight if doc is not None else None,
            financial_weight=(doc.evaluation.financial_weight if doc is not None else None) or parsed.terms.price_weight_pct,
            min_technical=doc.evaluation.min_technical_score if doc is not None else None,
            compliance=ctx.messages.get("compliance"),
        ) if market_ok(available, priced) else None
        if award is not None:
            log.decision(f"Award analysis ({award.rule}): {award.recommendation}", our_total=award.our_total,
                         lowest_rival=award.lowest_competitor, lowest_total=award.lowest_total, rank=award.rank,
                         gap_pct=award.gap_pct, target_total=award.target_total, msme_match=award.msme_match)
        return CompetitiveAnalysis(
            base_currency=base, market_endpoint=endpoint, market_latency_ms=latency, market_available=available,
            lines=priced, revenue=revenue, cost=cost, bundle_cost=bcost, margin=margin,
            margin_pct=round(100 * margin / revenue, 2) if revenue else 0.0, expected_profit=exp_profit,
            win_probability=win, strategy_counts=counts, below_cost_competitors=below_cost, summary=summary,
            warnings=warnings, award=award, agent_summary=agent_summary,
        )

    @staticmethod
    def _agent_review(llm, engine: StrategyEngine, buyer: BuyerContext, costing: InternalPricing,
                      offers_by_line: dict[int, list[MarketOffer]], priced: list, overrides: dict, rule: str, base: str,
                      log: StageLog) -> tuple[list, str | None]:
        """Let the pricing agent review the engine's prices through its tools; apply what it decides."""
        locked = {int(k) for k, v in overrides.items() if v.get("unit_price") is not None or "bundle" in v}
        desk = PricingDesk(engine=engine, buyer=buyer, lines={l.line_no: l for l in costing.lines}, offers=offers_by_line,
                           priced={p.line_no: p for p in priced}, locked=locked, currency=base)
        award = {"L1": "lowest compliant price wins (L1)", "QCBS": "quality and cost based selection"}.get(rule, "weighted evaluation")
        try:
            run = llm_pricing.review(llm, desk, award, buyer.segment)
        except LLMError as exc:
            log.warn("Pricing agent unavailable; engine prices kept", error=str(exc))
            return priced, None
        rejected = [c for c in run.calls if c.name == "set_price" and not c.ok]
        log.info("Pricing agent review", model=llm.model, turns=run.turns, tool_calls=len(run.calls),
                 decisions=len(desk.decisions), rejected_by_guardrails=len(rejected), **llm.usage.as_dict())
        lines = {l.line_no: l for l in costing.lines}
        out = []
        for p in priced:
            decision = desk.decisions.get(p.line_no)
            if decision is None:
                out.append(p)
                continue
            updated = engine.price_line(lines[p.line_no], offers_by_line[p.line_no], buyer, None, agent_choice=decision)
            log.decision(f"Line {p.line_no}: pricing agent {'kept' if updated.unit_price == p.unit_price else 'set'} "
                         f"{updated.unit_price:,.2f}", engine_price=p.unit_price, bundle=decision.get("bundle"),
                         strategy=updated.strategy, rationale=decision["rationale"])
            out.append(updated)
        missing = [p.line_no for p in priced if p.line_no not in desk.decisions and p.line_no not in locked]
        if missing:
            log.warn("Pricing agent left lines at the engine price", lines=missing)
        return out, run.text or None

    @staticmethod
    def _summary(priced, revenue, margin, win, below_cost, base) -> str:
        if not priced:
            return "No lines could be priced."
        parts = [f"{len(priced)} lines priced at {fmt(revenue, base, 0)} with {100 * margin / revenue:.1f}% gross margin"]
        vd = [p for p in priced if p.strategy == VALUE_DIFFERENTIATION]
        if below_cost:
            parts.append(f"{below_cost} line(s) face competitors below our landed cost")
        if vd:
            parts.append(f"{len(vd)} answered with value bundles instead of price cuts")
        parts.append(f"revenue-weighted win probability {100 * win:.0f}%")
        return "; ".join(parts) + "."

    def summarize(self, output: CompetitiveAnalysis) -> str:  # type: ignore[override]
        return output.summary
