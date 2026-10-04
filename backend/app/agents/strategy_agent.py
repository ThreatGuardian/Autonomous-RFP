"""Competitive Strategy Agent — queries the market API and sets every price."""

from __future__ import annotations

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import CompetitiveAnalysis, InternalPricing, MarketOffer, ParsedRfp
from app.db.seed import load_json
from app.db.session import session_scope
from app.finance.currency import UnknownCurrency, fx
from app.finance.money import fmt
from app.intel.sources import ADAPTERS, market_view
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
            warnings=warnings, award=award,
        )

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
