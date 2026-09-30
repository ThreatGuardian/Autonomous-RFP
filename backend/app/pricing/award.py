"""Bid-level award analysis: where the whole offer stands under the tender's award rule.

Line pricing answers "what should each item cost?". Public tenders are decided
on the **whole bid**, so this module answers the question a bid manager asks
next:

* **L1 (lowest price).** Competitor totals are estimated from the market offers
  per line (a competitor that does not carry an item is assumed to buy it at
  the market median). The analysis reports our rank, the gap to L1, the total
  needed to become L1, and whether that total respects every line's margin
  floor. For registered Micro and Small Enterprises the Public Procurement
  Policy for MSEs lets a bidder within 15% of L1 match the L1 price for up to
  25% of the order; that option is priced too.
* **QCBS.** Combined score = technical weight × technical score + financial
  weight × (lowest price ÷ our price × 100). Our technical score is estimated
  transparently from the compliance review; competitors are assumed at a
  policy value. The analysis finds the highest total that still wins.
* **Reverse auction.** Opening price and a walk-away total at the margin floor.
"""

from __future__ import annotations

from app.agents.messages import AwardAnalysis, AwardOption, ComplianceReport, InternalPricing, PricedLine
from app.finance.money import fmt


def _competitor_totals(lines: list[PricedLine]) -> list[dict]:
    medians = {l.line_no: l.market.median for l in lines if l.market.median}
    names: dict[str, str] = {}
    for l in lines:
        for o in l.market.offers:
            names[o.competitor_id] = o.competitor
    out = []
    value = sum(l.revenue for l in lines) or 1.0
    for cid, name in names.items():
        total, covered = 0.0, 0.0
        for l in lines:
            offer = next((o for o in l.market.offers if o.competitor_id == cid), None)
            if offer is not None:
                total += offer.unit_price_base * l.quantity
                covered += l.revenue
            elif l.line_no in medians:
                total += medians[l.line_no] * l.quantity
            else:
                total += l.revenue  # no market reference: assume parity with us
        out.append({"id": cid, "name": name, "total": round(total, 2), "coverage_pct": round(100 * covered / value, 1)})
    # Bidders that carry most of the schedule are the realistic rivals.
    serious = [c for c in out if c["coverage_pct"] >= 50] or out
    return sorted(serious, key=lambda c: c["total"])


def _scaled_prices(lines: list[PricedLine], costing: InternalPricing, target: float) -> tuple[dict[str, float], float]:
    """Uniform discount on every line, bounded by each line's floor, that reaches ``target`` if possible."""
    floors = {l.line_no: l.floor_price for l in lines}
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        total = sum(max(floors[l.line_no], l.unit_price * (1 - mid)) * l.quantity for l in lines)
        if total > target:
            lo = mid
        else:
            hi = mid
    prices = {str(l.line_no): round(max(floors[l.line_no], l.unit_price * (1 - hi)), 2) for l in lines}
    total = sum(prices[str(l.line_no)] * l.quantity for l in lines)
    return prices, round(total, 2)


def analyse(rule: str, lines: list[PricedLine], costing: InternalPricing, policy: dict, currency: str, *,
            msme: bool = False, reverse_auction: bool = False, technical_weight: float | None = None,
            financial_weight: float | None = None, min_technical: float | None = None,
            compliance: ComplianceReport | None = None) -> AwardAnalysis | None:
    if not lines:
        return None
    m = lambda v: fmt(v, currency, 0)  # noqa: E731
    ours = round(sum(l.revenue for l in lines), 2)
    cost = round(sum(l.cost + l.bundle_cost for l in lines), 2)
    floor_total = round(sum(l.floor_price * l.quantity for l in lines), 2)
    rivals = _competitor_totals(lines)
    a = AwardAnalysis(rule=rule if rule in ("L1", "QCBS") else "Weighted", our_total=ours, cost_total=cost,
                      floor_total=floor_total, competitors=rivals[:5], reverse_auction=reverse_auction,
                      recommendation="Submit as priced")

    def option(label: str, total: float, outcome: str) -> AwardOption:
        margin = total - cost
        return AwardOption(label=label, total=round(total, 2), margin=round(margin, 2),
                           margin_pct=round(100 * margin / total, 2) if total else 0.0,
                           feasible=total >= floor_total - 1, outcome=outcome)

    if reverse_auction:
        a.walk_away_total = floor_total
    if not rivals:
        a.reasons.append("No competitor prices were available to estimate rival bids.")
        a.options = [option("Submit as priced", ours, "No market reference")]
        return a

    lowest = rivals[0]
    a.lowest_competitor, a.lowest_total = lowest["name"], lowest["total"]
    a.rank = 1 + sum(1 for c in rivals if c["total"] < ours)
    a.gap_pct = round(100 * (ours - lowest["total"]) / lowest["total"], 2)

    if a.rule == "L1":
        target = lowest["total"] * (1 - policy["l1_undercut_pct"] / 100)
        prices, reached = _scaled_prices(lines, costing, target)
        a.target_total, a.target_prices = reached, prices
        a.target_feasible = reached <= target + 1
        band = policy["msme_purchase_preference_band_pct"]
        share = policy["msme_purchase_preference_share_pct"] / 100
        a.msme_band_pct = band
        within = ours <= lowest["total"] * (1 + band / 100)
        a.msme_match = bool(msme and a.rank > 1 and within and lowest["total"] > cost)
        a.options = [option("Submit as priced", ours, "Wins as L1" if a.rank == 1 else
                            f"Ranked L{a.rank}, {a.gap_pct:+.1f}% vs L1")]
        if a.rank == 1:
            # Already lowest: the useful question is how much headroom sits below the next rival.
            a.options.append(option("Highest price that stays L1", target,
                                    f"{m(target - ours)} more margin; {m(lowest['total'] - target)} gap to {lowest['name']}"))
        else:
            a.options.append(option("Price to become L1", reached,
                                    "Wins as L1" if a.target_feasible else "Cannot reach L1 above the margin floor"))
        if msme and a.rank > 1:
            mse = option(f"MSE match for {int(share * 100)}% of the order", lowest["total"],
                         f"Match L1 on {int(share * 100)}% of quantities" if a.msme_match
                         else "Matching L1 would be below cost" if within else f"Outside the {band:g}% band")
            mse.feasible = a.msme_match
            a.options.append(mse)
        if a.rank == 1:
            a.recommendation = "Submit as priced — already L1"
            a.reasons.append(f"Our total {m(ours)} is below the lowest estimated rival ({lowest['name']}, {m(lowest['total'])}).")
            a.reasons.append(f"There is {m(target - ours)} of headroom below that rival; keep it as a safety margin against "
                             f"price estimates that may be a few days old.")
        elif a.target_feasible:
            a.recommendation = "Reprice to become L1"
            a.reasons.append(f"{lowest['name']} is estimated at {m(lowest['total'])}, {abs(a.gap_pct):.1f}% below us. "
                             f"A uniform reduction to {m(reached)} makes us L1 and keeps every line above its margin floor "
                             f"({m(reached - cost)} gross margin).")
        elif a.msme_match:
            a.recommendation = "Stay above floor and use the MSE purchase preference"
            a.reasons.append(f"L1 at {m(lowest['total'])} is below our floor total {m(floor_total)}; we cannot win outright "
                             f"without breaching margin policy.")
            a.reasons.append(f"We are within {band:g}% of L1, so as a registered MSE we may match L1 for "
                             f"{int(share * 100)}% of the order: about {m(lowest['total'] * share)} of revenue at "
                             f"{100 * (lowest['total'] - cost) / lowest['total']:.1f}% margin.")
        else:
            a.recommendation = "Unlikely to win on price"
            a.reasons.append(f"L1 is estimated at {m(lowest['total'])}; our floor total is {m(floor_total)}. "
                             "Winning would mean pricing below the minimum-margin policy.")
        a.reasons.append("Under an L1 award, bundled services earn no evaluation credit; the whole-bid price decides.")
    else:
        tw = technical_weight or (70.0 if a.rule == "QCBS" else 100 - (financial_weight or 50))
        fw = financial_weight or (100 - tw)
        tech = 80.0
        if compliance is not None and compliance.mandatory_total >= 5:
            ratio = compliance.mandatory_met / compliance.mandatory_total
            deviations = compliance.counts.get("Deviation", 0)
            tech = max(40.0, min(95.0, 55 + 40 * ratio - 3 * deviations))
        rival_tech = float(policy["assumed_competitor_technical_score"])
        a.technical_score, a.competitor_technical_score = round(tech, 1), rival_tech

        def combined(price: float, rival_price: float, t: float, other_t: float) -> tuple[float, float]:
            low = min(price, rival_price)
            return (tw * t + fw * 100 * low / price) / 100, (tw * other_t + fw * 100 * low / rival_price) / 100

        us, them = combined(ours, lowest["total"], tech, rival_tech)
        a.combined_score, a.best_competitor_combined = round(us, 2), round(them, 2)
        # Highest total that still beats the best rival's combined score.
        lo, hi = floor_total, max(ours, lowest["total"]) * 1.3
        for _ in range(50):
            mid = (lo + hi) / 2
            u, t_ = combined(mid, lowest["total"], tech, rival_tech)
            if u > t_:
                lo = mid
            else:
                hi = mid
        winning = combined(lo, lowest["total"], tech, rival_tech)
        a.target_total = round(lo, 2) if winning[0] > winning[1] else None
        a.target_feasible = a.target_total is not None and a.target_total >= floor_total
        a.options = [option("Submit as priced", ours, f"Combined {us:.1f} vs {them:.1f}")]
        if a.target_total:
            a.options.append(option("Highest winning price", a.target_total, "Wins on combined score"))
        if min_technical and tech < min_technical:
            a.recommendation = "Technical score at risk"
            a.reasons.append(f"Estimated technical score {tech:.0f} is below the {min_technical:g}-mark qualifying threshold.")
        elif us > them:
            a.recommendation = "Submit as priced — leads on combined score"
            headroom = (a.target_total or ours) - ours
            a.reasons.append(f"Combined score {us:.1f} against {them:.1f} for {lowest['name']} "
                             f"({tw:g}:{fw:g} technical to financial)."
                             + (f" Up to {m(headroom)} of headroom remains." if headroom > 0 else ""))
        elif a.target_feasible:
            a.recommendation = "Reprice to lead on combined score"
            a.reasons.append(f"At {m(a.target_total)} our combined score overtakes {lowest['name']}, still above the floor.")
        else:
            a.recommendation = "Compete on technical strength"
            a.reasons.append("Price alone cannot close the combined-score gap above the margin floor; strengthen the "
                             "technical proposal.")
        a.reasons.append(f"Technical score estimated at {tech:.0f} from the compliance review; rivals assumed at {rival_tech:.0f}.")
    if reverse_auction:
        a.reasons.append(f"Reverse auction: open at {m(ours)} and do not go below {m(floor_total)}.")
    return a

