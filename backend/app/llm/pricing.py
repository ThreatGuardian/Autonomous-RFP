"""Pricing & Competitor Analysis Agent — the language-model step.

The strategy engine first prices every line (expected-profit optimum under policy).
Claude then reviews the whole bid as an analyst would, working only through tools:

* ``get_line`` — cost basis, stock, eligible services and the engine's recommendation;
* ``get_competitor_offers`` — every competitor price with its source and date;
* ``evaluate_price`` — margin, win probability and policy checks for any price;
* ``get_bid_history`` — outcomes of the company's real past bids;
* ``set_price`` — the decision for a line, with a rationale.

``set_price`` enforces the commercial guard-rails in code: never below the margin
floor, service costs funded from margin and capped, no free services under a
lowest-price award, and reviewer overrides are never changed. The model can argue for
a price; it cannot breach policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.agents.messages import CostedLine, MarketOffer, PricedLine
from app.llm.client import LLM, AgentRun, Tool, ToolRejected
from app.llm.memory import bid_history
from app.pricing.strategy import BuyerContext, StrategyEngine

SYSTEM = """You are the pricing and competitor analysis agent of a supplier's bid desk. The strategy engine has \
already priced every line of this bid. Review each line and decide its final unit price and whether to include a \
free value-added service.

How to decide:
- Aim for the highest expected profit (margin × quantity × chance of winning) that still gives the bid a realistic \
chance. Use evaluate_price to compare options; it uses the company's trained win-probability model.
- If a competitor is priced below our landed cost, do not chase that price: it would sell at a loss. Hold a price \
above the margin floor and, where the award rule rewards it, compete on value with a bundled service.
- Under a lowest-price (L1) award only the price counts: offer no free services and look at the whole bid's rank.
- Competitor prices are estimates of differing reliability and age; weigh the source and date.
- Learn from the company's past bid outcomes for similar categories.
- Keep the engine's price when you have no better reason; say why either way.

Call set_price exactly once for every line, with a rationale of one or two sentences that cites the facts. The tools \
enforce the margin floor and policy limits; if one rejects your price, choose another. Finish with a short summary \
of the bid strategy for the reviewer (three sentences at most)."""


class LineRef(BaseModel):
    line_no: int


class PriceProposal(BaseModel):
    line_no: int
    unit_price: float = Field(description="Unit price in the base currency, before tax")
    bundle_code: str | None = Field(description="Code of an eligible value-added service to include free, or null")


class PriceDecision(PriceProposal):
    rationale: str = Field(description="One or two sentences citing the facts behind the decision")


class CategoryRef(BaseModel):
    category: str | None = Field(description="Product category, or null for all categories")


@dataclass
class PricingDesk:
    """The bid as the pricing agent sees it, and the decisions it makes."""

    engine: StrategyEngine
    buyer: BuyerContext
    lines: dict[int, CostedLine]
    offers: dict[int, list[MarketOffer]]
    priced: dict[int, PricedLine]
    locked: set[int]
    currency: str
    decisions: dict[int, dict[str, Any]] = field(default_factory=dict)

    def _line(self, line_no: int) -> CostedLine:
        if line_no not in self.lines:
            raise ToolRejected(f"There is no line {line_no}. Lines: {sorted(self.lines)}.")
        return self.lines[line_no]

    # ------------------------------------------------------------------ tools

    def get_line(self, ref: LineRef) -> dict[str, Any]:
        l, p = self._line(ref.line_no), self.priced[ref.line_no]
        best = p.market.best
        return {
            "line_no": l.line_no, "product": l.name, "sku": l.sku, "category": l.category, "quantity": l.quantity,
            "requested": l.requested, "unit_cost": l.unit_cost, "margin_floor_price": l.floor_price,
            "list_price": l.list_price, "standard_price": l.standard_price, "stock": l.stock_qty, "in_stock": l.stock_ok,
            "lead_time_days": l.lead_time_days, "warranty_months": l.warranty_months,
            "eligible_services": [{"code": b.code, "name": b.name, "unit_cost": b.unit_cost, "market_value": b.unit_value,
                                   "warranty_extension_months": b.warranty_extension_months} for b in l.value_adds],
            "market": {"offers": p.market.count, "lowest": p.market.min, "median": p.market.median,
                       "lowest_competitor": best.competitor if best else None,
                       "lowest_is_below_our_cost": bool(best and best.unit_price_base < l.unit_cost)},
            "engine_recommendation": {"unit_price": p.unit_price, "bundle": p.bundle.code if p.bundle else None,
                                      "strategy": p.strategy, "margin_pct": p.margin_pct,
                                      "win_probability": p.win_probability, "expected_profit": p.expected_profit},
            "locked_by_reviewer": l.line_no in self.locked,
        }

    def get_competitor_offers(self, ref: LineRef) -> list[dict[str, Any]]:
        self._line(ref.line_no)
        return [{"competitor": o.competitor, "unit_price": o.unit_price_base, "warranty_months": o.warranty_months,
                 "lead_time_days": o.lead_time_days, "in_stock": o.in_stock, "source": o.source,
                 "observed_on": o.observed_on, "reliability": o.reliability, "equivalent_model": o.equivalent,
                 "promotion": o.promotion} for o in self.offers.get(ref.line_no, [])]

    def evaluate_price(self, proposal: PriceProposal) -> dict[str, Any]:
        line = self._line(proposal.line_no)
        return self.engine.assess(line, self.offers.get(line.line_no, []), self.buyer, proposal.unit_price,
                                  proposal.bundle_code)

    def get_bid_history(self, ref: CategoryRef) -> dict[str, Any]:
        rows = bid_history(ref.category)
        return {"bids": rows, "note": "Real outcomes recorded by reviewers; empty until outcomes are recorded."}

    def set_price(self, decision: PriceDecision) -> dict[str, Any]:
        line = self._line(decision.line_no)
        if line.line_no in self.locked:
            raise ToolRejected(f"Line {line.line_no} was priced by a reviewer and cannot be changed.")
        check = self.engine.assess(line, self.offers.get(line.line_no, []), self.buyer, decision.unit_price,
                                   decision.bundle_code)
        if not check["feasible"]:
            raise ToolRejected(f"Price not accepted: {'; '.join(check['issues'])}.")
        self.decisions[line.line_no] = {"unit_price": round(decision.unit_price, 2), "bundle": decision.bundle_code,
                                        "rationale": decision.rationale.strip()[:600]}
        return {"accepted": True, **check}

    def tools(self) -> list[Tool]:
        return [
            Tool("get_line", "Cost basis, stock, eligible services, market summary and the engine's recommendation for a line.",
                 LineRef, self.get_line),
            Tool("get_competitor_offers", "Every competitor offer for a line, in the base currency, with source and date.",
                 LineRef, self.get_competitor_offers),
            Tool("evaluate_price", "Margin, win probability, expected profit and policy checks for a proposed unit price "
                 "and optional free service. Does not change anything.", PriceProposal, self.evaluate_price),
            Tool("get_bid_history", "Outcomes of the company's real past bids, optionally for one product category.",
                 CategoryRef, self.get_bid_history),
            Tool("set_price", "Record the final unit price and optional free service for a line, with the rationale. "
                 "Rejected if it breaches the margin floor or pricing policy.", PriceDecision, self.set_price),
        ]

    # ------------------------------------------------------------------ brief

    def brief(self, award: str, segment: str) -> str:
        rows = []
        for no, p in sorted(self.priced.items()):
            l = self.lines[no]
            best = p.market.best
            rows.append(f"- Line {no}: {l.name} × {l.quantity}; cost {l.unit_cost:,.2f}, floor {l.floor_price:,.2f}; "
                        f"engine price {p.unit_price:,.2f} ({p.strategy}); lowest competitor "
                        + (f"{best.unit_price_base:,.2f} ({best.competitor})" if best else "none")
                        + ("; locked by reviewer" if no in self.locked else ""))
        return (f"Bid in {self.currency}. Award rule: {award}. Buyer segment: {segment}.\n"
                f"Lines:\n" + "\n".join(rows) +
                "\n\nReview each line with the tools and call set_price for every line that is not locked.")


def review(llm: LLM, desk: PricingDesk, award: str, segment: str) -> AgentRun:
    open_lines = len(desk.lines) - len(desk.locked)
    return llm.run_tools(system=SYSTEM, user=desk.brief(award, segment), tools=desk.tools(), effort="high",
                         max_turns=12 + 3 * open_lines)
