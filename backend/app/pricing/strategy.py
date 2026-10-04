"""Competitive pricing strategy engine.

For one line item the engine searches a price grid between the margin floor
and the list price, optionally combined with each eligible value-add, and
chooses the configuration that maximises **expected gross profit**::

    E[profit] = (price − unit cost − bundle cost) × quantity × P(win | offer)

``P(win)`` comes from the win-probability model trained on the bid ledger.
Commercial guard-rails are hard constraints, never soft penalties: the price
never drops below the margin floor, and a bundle's cost must be covered by
margin above that floor.

The critical rule: **if the best competitor is below our landed cost**, the
engine does not chase price. Matching would sell at a loss, so it holds price
above the floor and competes on value — it restricts the search to bundled
configurations and picks the value-add that buys the most win probability per
rupee of cost.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.agents.messages import (
    BundleDecision, CostedLine, CurvePoint, MarketOffer, MarketView, PricedLine, Scenario, ValueAddOption,
)
from app.finance.money import fmt
from app.ml.models import BidFeatures, WinProbabilityModel

VALUE_DIFFERENTIATION = "Value differentiation"
FLOOR_DEFENCE = "Floor defence"
UNDERCUT = "Competitive undercut"
MATCH = "Competitive match"
MARGIN_CAPTURE = "Margin capture"
VALUE_PREMIUM = "Value premium"
LIST_PRICE = "Standard pricing"
MANUAL = "Reviewer override"


@dataclass
class BuyerContext:
    segment: str
    repeat_customer: bool
    price_weight_pct: float  # weight of price in the buyer's evaluation
    award: str = "weighted"  # "L1" when the lowest compliant price wins outright


@dataclass
class Candidate:
    price: float
    bundle: ValueAddOption | None
    margin_unit: float
    p_win: float
    expected: float


def market_view(offers: list[MarketOffer]) -> MarketView:
    if not offers:
        return MarketView()
    prices = sorted(o.unit_price_base for o in offers)
    best = min(offers, key=lambda o: o.unit_price_base)
    return MarketView(
        offers=sorted(offers, key=lambda o: o.unit_price_base), count=len(offers), min=prices[0],
        median=statistics.median(prices), max=prices[-1], best=best,
    )


class StrategyEngine:
    def __init__(self, model: WinProbabilityModel, policy: dict, currency: str) -> None:
        self.model = model
        self.policy = policy
        self.ccy = currency
        self._best_effort = False

    def _m(self, v: float) -> str:
        return fmt(v, self.ccy, 0)

    # ------------------------------------------------------------------ model plumbing

    def _amplification(self, buyer: BuyerContext) -> float:
        """Award rules modulate price sensitivity: L1 tenders ~2x, balanced scoring ~1x."""
        return max(0.6, min(2.0, buyer.price_weight_pct / self.policy["default_price_weight_pct"]))

    def _features(self, line: CostedLine, best: MarketOffer, price: float, bundle: ValueAddOption | None,
                  buyer: BuyerContext) -> BidFeatures:
        ratio = 1 + (price / best.unit_price_base - 1) * self._amplification(buyer)
        ext = bundle.warranty_extension_months if bundle else 0
        if buyer.award == "L1":
            # Lowest-price awards score only the price of a compliant offer: extras earn nothing.
            return BidFeatures(price_ratio=ratio, warranty_delta_months=0, lead_time_delta_days=0,
                               bundled_value_add=False, repeat_customer=False, segment=buyer.segment)
        return BidFeatures(
            price_ratio=ratio,
            warranty_delta_months=line.warranty_months + ext - best.warranty_months,
            lead_time_delta_days=line.lead_time_days - best.lead_time_days,
            bundled_value_add=bundle is not None,
            repeat_customer=buyer.repeat_customer,
            segment=buyer.segment,
        )

    def _evaluate(self, line: CostedLine, best: MarketOffer, price: float, bundle: ValueAddOption | None,
                  buyer: BuyerContext) -> Candidate:
        va_cost = bundle.unit_cost if bundle else 0.0
        margin_unit = price - line.unit_cost - va_cost
        p = self.model.predict(self._features(line, best, price, bundle, buyer))
        return Candidate(price, bundle, margin_unit, p, margin_unit * line.quantity * p)

    def _feasible(self, line: CostedLine, price: float, bundle: ValueAddOption | None) -> bool:
        if price < line.floor_price - 1e-6:
            return False
        if bundle is None:
            return True
        # The bundle is funded from margin above the floor and capped as a share of price.
        return (price - bundle.unit_cost >= line.floor_price - 1e-6
                and bundle.unit_cost <= price * self.policy["max_bundle_cost_share_pct"] / 100)

    def _grid(self, line: CostedLine) -> list[float]:
        lo, hi = line.floor_price, max(line.floor_price, line.list_price)
        n = self.policy["price_grid_points"]
        return [round(lo + (hi - lo) * i / (n - 1), 2) for i in range(n)]

    # ------------------------------------------------------------------ public

    def assess(self, line: CostedLine, offers: list[MarketOffer], buyer: BuyerContext, price: float,
               bundle_code: str | None) -> dict:
        """Metrics and policy checks for one proposed price (used by the pricing agent's tools)."""
        view = market_view(offers)
        bundle = next((b for b in line.value_adds if b.code == bundle_code), None) if bundle_code else None
        issues = []
        if bundle_code and bundle is None:
            issues.append(f"'{bundle_code}' is not an eligible service for this line")
        if price < line.floor_price - 1e-6:
            issues.append(f"below the margin floor {self._m(line.floor_price)}")
        if bundle is not None:
            if buyer.award == "L1":
                issues.append("a free service earns no credit under a lowest-price (L1) award")
            elif price - bundle.unit_cost < line.floor_price - 1e-6:
                issues.append("the service cost would take the price below the margin floor")
            elif bundle.unit_cost > price * self.policy["max_bundle_cost_share_pct"] / 100:
                issues.append(f"the service costs more than {self.policy['max_bundle_cost_share_pct']:g}% of the price")
        out = {"unit_price": round(price, 2), "bundle": bundle.code if bundle else None,
               "margin_pct": round(100 * (price - line.unit_cost - (bundle.unit_cost if bundle else 0)) / price, 2) if price else 0.0,
               "feasible": not issues, "issues": issues}
        if view.best is not None:
            c = self._evaluate(line, view.best, price, bundle, buyer)
            out.update(win_probability=round(c.p_win, 4), expected_profit=round(c.expected, 2),
                       vs_best_competitor_pct=round(100 * (price / view.best.unit_price_base - 1), 2),
                       classification=self._classify(line, view.best, c, view.best.unit_price_base < line.unit_cost, False))
        return out

    def price_line(self, line: CostedLine, offers: list[MarketOffer], buyer: BuyerContext,
                   override: dict | None = None, agent_choice: dict | None = None) -> PricedLine:
        """Price one line. A reviewer ``override`` wins; otherwise a feasible ``agent_choice``
        (unit_price, bundle, rationale) from the pricing agent replaces the grid optimum."""
        view = market_view(offers)
        if view.best is None:
            return self._no_market(line, view, override)
        best = view.best
        grid = self._grid(line)
        bundles: list[ValueAddOption | None] = [None, *line.value_adds]
        below_cost = best.unit_price_base < line.unit_cost

        candidates: list[Candidate] = []
        if buyer.award == "L1":
            allowed: list[ValueAddOption | None] = [None]  # a free bundle adds cost and wins no marks under L1
        else:
            allowed = [b for b in bundles if b is not None] if below_cost and line.value_adds else bundles
        for bundle in allowed:
            for price in grid:
                if self._feasible(line, price, bundle):
                    candidates.append(self._evaluate(line, best, price, bundle, buyer))
        if not candidates:  # bundles too expensive for the floor: fall back to unbundled pricing
            candidates = [self._evaluate(line, best, p, None, buyer) for p in grid]
        # Maximise expected profit among offers with a realistic chance of winning;
        # if none reach the target, submit the most competitive compliant offer.
        target = self.policy["min_target_win_probability"]
        viable = [c for c in candidates if c.p_win >= target]
        if viable:
            chosen = max(viable, key=lambda c: (round(c.expected, 2), c.p_win))
            self._best_effort = False
        else:
            chosen = max(candidates, key=lambda c: (round(c.p_win, 4), c.expected))
            self._best_effort = True

        agent_note = None
        if agent_choice and not override:
            bundle = next((b for b in line.value_adds if b.code == agent_choice.get("bundle")), None)
            price = float(agent_choice["unit_price"])
            if self._feasible(line, price, bundle) and not (bundle is not None and buyer.award == "L1"):
                chosen = self._evaluate(line, best, price, bundle, buyer)
                agent_note = agent_choice.get("rationale")

        overridden = False
        if override and (override.get("unit_price") is not None or "bundle" in override):
            bundle_code = override.get("bundle", chosen.bundle.code if chosen.bundle else None)
            bundle = next((b for b in line.value_adds if b.code == bundle_code), None)
            price = float(override.get("unit_price") or chosen.price)
            chosen = self._evaluate(line, best, price, bundle, buyer)
            overridden = True

        strategy = self._classify(line, best, chosen, below_cost, overridden)
        scenarios = self._scenarios(line, best, buyer, chosen, grid)
        curve = self._curve(line, best, chosen.bundle, buyer, grid)
        rationale, headline = self._explain(line, view, chosen, strategy, buyer, scenarios, below_cost)
        if agent_note:
            rationale.insert(0, f"Pricing agent: {agent_note}")
        return self._assemble(line, view, chosen, strategy, headline, rationale, scenarios, curve, overridden)

    # ------------------------------------------------------------------ classification & narrative

    def _classify(self, line: CostedLine, best: MarketOffer, c: Candidate, below_cost: bool, overridden: bool) -> str:
        if overridden:
            return MANUAL
        b = best.unit_price_base
        if below_cost:
            return VALUE_DIFFERENTIATION if c.bundle else FLOOR_DEFENCE
        if b < line.floor_price:
            return VALUE_DIFFERENTIATION if c.bundle else FLOOR_DEFENCE
        if b >= line.standard_price and c.price >= line.standard_price:
            return MARGIN_CAPTURE
        band = self.policy["match_band_pct"] / 100
        if c.price < b * (1 - 0.0005):
            return UNDERCUT
        if c.price <= b * (1 + band):
            return MATCH
        return VALUE_PREMIUM

    def _scenarios(self, line: CostedLine, best: MarketOffer, buyer: BuyerContext, chosen: Candidate,
                   grid: list[float]) -> list[Scenario]:
        def scen(label: str, price: float, bundle: ValueAddOption | None, note: str | None = None) -> Scenario:
            c = self._evaluate(line, best, price, bundle, buyer)
            return Scenario(
                label=label, unit_price=round(price, 2), bundle=bundle.code if bundle else None,
                margin_pct=round(100 * c.margin_unit / price, 2) if price else 0.0,
                win_probability=round(c.p_win, 4), expected_profit=round(c.expected, 2),
                feasible=self._feasible(line, price, bundle), note=note,
            )

        out = [
            scen("Recommended", chosen.price, chosen.bundle),
            scen("Match best competitor", best.unit_price_base, None,
                 "Below landed cost" if best.unit_price_base < line.unit_cost
                 else "Below margin floor" if best.unit_price_base < line.floor_price else None),
            scen("Standard price (list less volume tier)", line.standard_price, None),
            scen("Margin floor, no bundle", line.floor_price, None),
        ]
        if chosen.bundle is not None:
            no_bundle = [self._evaluate(line, best, p, None, buyer) for p in grid]
            viable = [c for c in no_bundle if c.p_win >= self.policy["min_target_win_probability"]]
            pick = max(viable, key=lambda c: c.expected) if viable else max(no_bundle, key=lambda c: c.p_win)
            out.append(scen("Best price without a bundle", pick.price, None))
        unique: dict[tuple[float, str | None], Scenario] = {}
        for sc in out:
            key = (round(sc.unit_price, 2), sc.bundle)
            if key in unique:
                # Identical offers: keep one row, preferring the more specific label.
                if sc.label == "Best price without a bundle":
                    unique[key].label = sc.label
                continue
            unique[key] = sc
        return list(unique.values())

    def _curve(self, line: CostedLine, best: MarketOffer, bundle: ValueAddOption | None, buyer: BuyerContext,
               grid: list[float]) -> list[CurvePoint]:
        pts = []
        step = max(1, len(grid) // 30)
        for price in grid[::step] + [grid[-1]]:
            c = self._evaluate(line, best, price, bundle, buyer)
            pts.append(CurvePoint(unit_price=price, ratio=round(price / best.unit_price_base, 4),
                                  win_probability=round(c.p_win, 4), expected_profit=round(c.expected, 2)))
        return pts

    def _explain(self, line: CostedLine, view: MarketView, c: Candidate, strategy: str, buyer: BuyerContext,
                 scenarios: list[Scenario], below_cost: bool) -> tuple[list[str], str]:
        best = view.best
        assert best is not None
        m = self._m
        gap_to_cost = 100 * (best.unit_price_base - line.unit_cost) / line.unit_cost
        r = [
            f"Market: {view.count} competitor offer(s) for {line.mpn}; lowest is {best.competitor} at "
            f"{m(best.unit_price_base)} per {line.unit}"
            + (f" (quoted {fmt(best.unit_price, best.currency)})" if best.currency != self.ccy else "")
            + (f", flagged as '{best.promotion}'" if best.promotion else "") + ".",
            f"Our landed cost is {m(line.unit_cost)}; minimum-margin floor {m(line.floor_price)} "
            f"({line.min_margin_pct:g}%); standard price after {line.tier_discount_pct:g}% volume tier is {m(line.standard_price)}.",
        ]
        match = next(s for s in scenarios if s.label == "Match best competitor")
        if below_cost:
            r.append(
                f"The best competitor is {abs(gap_to_cost):.1f}% below our landed cost. Matching would lose "
                f"{m(line.unit_cost - best.unit_price_base)} per unit ({m((line.unit_cost - best.unit_price_base) * line.quantity)} "
                f"on this line), so price matching was rejected."
            )
        elif best.unit_price_base < line.floor_price:
            r.append(f"The best competitor is above our cost but below our margin floor; matching would breach the "
                     f"{line.min_margin_pct:g}% minimum-margin policy and was rejected.")
        if buyer.award == "L1" and (below_cost or best.unit_price_base < line.floor_price):
            r.append("The tender is awarded to the lowest compliant bid (L1), where bundled services earn no evaluation "
                     "credit, so value differentiation cannot win this line; the price is held at the policy floor and "
                     "the whole-bid position is assessed in the award analysis.")
        if c.bundle is not None:
            b = c.bundle
            extra = f", extending warranty to {line.warranty_months + b.warranty_extension_months} months" if b.warranty_extension_months else ""
            r.append(f"Included '{b.name}' at no charge: worth {m(b.unit_value)} per unit to the buyer, costing us {m(b.unit_cost)}{extra}.")
            unbundled = next((s for s in scenarios if s.label == "Best price without a bundle"), None)
            if unbundled is not None:
                if c.expected >= unbundled.expected_profit:
                    r.append(
                        f"The bundle outperforms the best unbundled price ({m(unbundled.unit_price)}): win probability "
                        f"{100 * c.p_win:.0f}% vs {100 * unbundled.win_probability:.0f}%, expected profit {m(c.expected)} vs "
                        f"{m(unbundled.expected_profit)}."
                    )
                else:
                    r.append(
                        f"Policy: against below-cost competition we compete on value, not price. The unbundled floor price "
                        f"({m(unbundled.unit_price)}) would model {100 * unbundled.win_probability:.0f}% win probability vs "
                        f"{100 * c.p_win:.0f}% — a difference too small to justify abandoning differentiation."
                    )
        pct_vs_best = 100 * (c.price / best.unit_price_base - 1)
        rel = f"{abs(pct_vs_best):.1f}% {'above' if pct_vs_best >= 0 else 'below'} the lowest competitor"
        r.append(
            f"Recommended {m(c.price)} per unit ({rel}), margin {100 * c.margin_unit / c.price:.1f}% after bundle cost, "
            f"modelled win probability {100 * c.p_win:.0f}%, expected gross profit {m(c.expected)}."
        )
        if self._best_effort:
            r.append(
                f"No policy-compliant price reaches the {100 * self.policy['min_target_win_probability']:.0f}% target win "
                f"probability, so the most competitive compliant offer was chosen rather than the highest expected profit."
            )
        if match.feasible:
            r.append(f"Alternative — match at {m(match.unit_price)}: win probability {100 * match.win_probability:.0f}%, "
                     f"expected profit {m(match.expected_profit)}.")
        elasticity = self.model.price_elasticity(buyer.segment)
        r.append(
            f"Buyer segment '{buyer.segment}' (price elasticity {elasticity:.1f} log-odds per unit price ratio); "
            f"price weighted at {buyer.price_weight_pct:g}% in evaluation"
            + ("; repeat customer." if buyer.repeat_customer else ".")
        )
        headline = {
            VALUE_DIFFERENTIATION: (f"Competitor {'below our cost' if below_cost else 'below our margin floor'} — "
                                    f"holding price and bundling {c.bundle.name.lower() if c.bundle else 'value'}"),
            FLOOR_DEFENCE: "Competitor below floor — holding at policy minimum",
            UNDERCUT: f"Priced {abs(pct_vs_best):.1f}% under the lowest competitor",
            MATCH: "Priced level with the market",
            MARGIN_CAPTURE: "Market is above our standard price — capturing margin",
            VALUE_PREMIUM: f"Priced {pct_vs_best:.1f}% above market, justified by service terms",
            MANUAL: "Price set by reviewer",
        }[strategy]
        return r, headline

    # ------------------------------------------------------------------ assembly

    def _assemble(self, line: CostedLine, view: MarketView, c: Candidate, strategy: str, headline: str,
                  rationale: list[str], scenarios: list[Scenario], curve: list[CurvePoint], overridden: bool) -> PricedLine:
        q = line.quantity
        bundle = None
        if c.bundle:
            b = c.bundle
            bundle = BundleDecision(code=b.code, name=b.name, kind=b.kind, unit_cost=b.unit_cost, unit_value=b.unit_value,
                                    total_cost=round(b.unit_cost * q, 2), total_value=round(b.unit_value * q, 2),
                                    warranty_extension_months=b.warranty_extension_months, description=b.description)
        revenue = round(c.price * q, 2)
        cost = round(line.unit_cost * q, 2)
        bcost = bundle.total_cost if bundle else 0.0
        margin = round(revenue - cost - bcost, 2)
        flags = []
        if c.price < line.floor_price - 1e-6:
            flags.append("Below margin floor")
        if c.margin_unit < 0:
            flags.append("Loss-making price")
        if not line.stock_ok:
            flags.append(f"Backorder: {line.stock_qty} in stock")
        if c.p_win < 0.25:
            flags.append("Low win probability")
        return PricedLine(
            line_no=line.line_no, sku=line.sku, name=line.name, category=line.category, quantity=q, unit=line.unit,
            unit_cost=line.unit_cost, list_price=line.list_price, floor_price=line.floor_price,
            standard_price=line.standard_price, unit_price=round(c.price, 2),
            discount_pct=round(100 * (1 - c.price / line.list_price), 2), bundle=bundle, revenue=revenue, cost=cost,
            bundle_cost=bcost, margin=margin, margin_pct=round(100 * margin / revenue, 2) if revenue else 0.0,
            win_probability=round(c.p_win, 4), expected_profit=round(c.expected, 2), strategy=strategy,
            headline=headline, rationale=rationale, scenarios=scenarios, curve=curve, market=view,
            lead_time_days=line.lead_time_days,
            warranty_months=line.warranty_months + (bundle.warranty_extension_months if bundle else 0),
            overridden=overridden, flags=flags,
        )

    def _no_market(self, line: CostedLine, view: MarketView, override: dict | None) -> PricedLine:
        self._best_effort = False
        price = float((override or {}).get("unit_price") or line.standard_price)
        overridden = bool(override and override.get("unit_price") is not None)
        c = Candidate(price, None, price - line.unit_cost, 0.5, (price - line.unit_cost) * line.quantity * 0.5)
        rationale = [
            f"No competitor offers were found for {line.mpn} in the client's market.",
            f"Priced at the standard price {self._m(line.standard_price)} (list {self._m(line.list_price)} less "
            f"{line.tier_discount_pct:g}% volume tier), margin {100 * (price - line.unit_cost) / price:.1f}%.",
            "Win probability is shown at the neutral prior of 50% because no market reference exists.",
        ]
        strategy = MANUAL if overridden else LIST_PRICE
        headline = "Price set by reviewer" if overridden else "No market data — standard pricing"
        return self._assemble(line, view, c, strategy, headline, rationale, [], [], overridden)
