"""Internal Pricing Agent — sole reader of the internal pricing database.

For every matched line it retrieves landed cost, list price, margin floor,
volume-tier discount, stock position, lead time, warranty and the value-adds
that can legitimately be bundled with that product category.
"""

from __future__ import annotations

from sqlalchemy import select

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import CostedLine, ExcludedLine, InternalPricing, ParsedRfp, ValueAddOption
from app.db.models import PriceTier, Product, ValueAdd
from app.db.seed import load_json
from app.db.session import session_scope


def tier_discount(tiers: list[PriceTier], category: str, qty: int) -> float:
    applicable = [t for t in tiers if t.category == category] or [t for t in tiers if t.category == "*"]
    best = 0.0
    for t in sorted(applicable, key=lambda t: t.min_qty):
        if qty >= t.min_qty:
            best = t.discount_pct
    return best


class InternalPricingAgent(Agent):
    stage = "costing"
    name = "Internal Pricing Agent"
    produces = "costing"
    consumes = ("parsed",)

    def run(self, ctx: PipelineContext, log: StageLog) -> InternalPricing:
        parsed: ParsedRfp = ctx.require("parsed")
        policy = load_json("pricing_policy.json")
        overrides = (ctx.overrides or {}).get("lines", {})
        lines: list[CostedLine] = []
        excluded: list[ExcludedLine] = []
        warnings: list[str] = []

        with session_scope() as s:
            tiers = list(s.scalars(select(PriceTier)))
            value_adds = list(s.scalars(select(ValueAdd)))
            for item in parsed.line_items:
                ov = overrides.get(str(item.line_no), {})
                if ov.get("exclude"):
                    excluded.append(ExcludedLine(line_no=item.line_no, description=item.description, reason="Excluded by reviewer"))
                    log.decision(f"Line {item.line_no} excluded by reviewer")
                    continue
                sku = ov.get("sku") or item.selected_sku
                if not sku:
                    excluded.append(ExcludedLine(line_no=item.line_no, description=item.description, reason="No catalogue match"))
                    log.warn(f"Line {item.line_no} has no catalogue match", request=item.description)
                    continue
                product = s.scalar(select(Product).where(Product.sku == sku))
                if product is None or not product.active:
                    excluded.append(ExcludedLine(line_no=item.line_no, description=item.description, reason=f"SKU {sku} inactive"))
                    continue
                qty = int(ov.get("quantity") or item.quantity)
                tier = tier_discount(tiers, product.category, qty)
                standard = round(product.list_price * (1 - tier / 100), 2)
                stock_ok = product.stock_qty >= qty
                lead = policy["in_stock_lead_days"] if stock_ok else product.lead_time_days
                options = [
                    ValueAddOption(
                        code=v.code, name=v.name, kind=v.kind, description=v.description,
                        unit_cost=v.unit_cost_for(product), unit_value=v.unit_value_for(product),
                        warranty_extension_months=v.warranty_extension_months,
                    )
                    for v in value_adds
                    if product.category in (v.categories or []) and v.kind in policy["bundle_kinds"]
                ]
                line = CostedLine(
                    line_no=item.line_no, sku=product.sku, mpn=product.mpn, name=product.name, brand=product.brand,
                    category=product.category, description=product.description, requested=item.description,
                    quantity=qty, unit=product.unit, unit_cost=product.unit_cost, list_price=product.list_price,
                    min_margin_pct=product.min_margin_pct, floor_price=product.floor_price, tier_discount_pct=tier,
                    standard_price=standard, stock_qty=product.stock_qty, stock_ok=stock_ok, lead_time_days=lead,
                    warranty_months=product.warranty_months, tax_category=product.tax_category, value_adds=options,
                )
                lines.append(line)
                log.info(
                    f"Line {item.line_no}: {product.sku} costed",
                    unit_cost=product.unit_cost, list_price=product.list_price, floor=product.floor_price,
                    tier_discount_pct=tier, standard_price=standard, stock=product.stock_qty, quantity=qty,
                    bundle_options=[o.code for o in options],
                )
                if not stock_ok:
                    msg = f"Line {item.line_no}: only {product.stock_qty} of {qty} in stock; lead time {product.lead_time_days} days."
                    warnings.append(msg)
                    log.warn(msg)

        return InternalPricing(base_currency=ctx.company["base_currency"], lines=lines, excluded=excluded, warnings=warnings)

    def summarize(self, output: InternalPricing) -> str:  # type: ignore[override]
        cost = sum(l.unit_cost * l.quantity for l in output.lines)
        return f"{len(output.lines)} lines costed, landed cost {cost:,.0f} {output.base_currency}; {len(output.excluded)} excluded."
