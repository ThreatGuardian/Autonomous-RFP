"""Typed messages exchanged between agents."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- parser output


class ClientInfo(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    country_name: str | None = None
    region: str | None = None
    is_eu: bool = False
    segment: str = "smb"
    segment_source: str = "default"
    tax_id: str | None = None
    customer_id: int | None = None
    repeat_customer: bool = False


class CurrencyInfo(BaseModel):
    code: str
    source: Literal["explicit", "country_default", "company_default"]
    evidence: str | None = None


class ProductMatch(BaseModel):
    sku: str
    name: str
    category: str
    score: float
    retrieval_score: float
    spec_fit: float | None = None
    reasons: list[str] = Field(default_factory=list)


class RequestedItem(BaseModel):
    line_no: int
    text: str
    description: str
    quantity: int
    quantity_source: str
    unit: str | None = None
    category: str | None = None
    category_confidence: float = 0.0
    specs: dict[str, Any] = Field(default_factory=dict)
    brand: str | None = None
    candidates: list[ProductMatch] = Field(default_factory=list)
    selected_sku: str | None = None
    match_confidence: float = 0.0
    status: Literal["matched", "ambiguous", "unmatched"] = "unmatched"


class Requirement(BaseModel):
    id: str
    text: str
    type: str
    confidence: float


class CommercialTerms(BaseModel):
    incoterm: str | None = None
    incoterm_source: str = "default"
    delivery_location: str | None = None
    delivery_days: int | None = None
    payment_days: int | None = None
    advance_pct: float | None = None
    warranty_months_required: int | None = None
    price_weight_pct: float | None = None
    lowest_price_award: bool = False


class ParsedRfp(BaseModel):
    title: str
    client_reference: str | None = None
    client: ClientInfo
    currency: CurrencyInfo
    issued_on: str | None = None
    due_date: str | None = None
    delivery_by: str | None = None
    terms: CommercialTerms
    line_items: list[RequestedItem]
    requirements: list[Requirement]
    requirement_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- internal pricing


class ValueAddOption(BaseModel):
    code: str
    name: str
    kind: str
    description: str
    unit_cost: float
    unit_value: float
    warranty_extension_months: int = 0


class CostedLine(BaseModel):
    line_no: int
    sku: str
    mpn: str
    name: str
    brand: str
    category: str
    description: str
    requested: str
    quantity: int
    unit: str
    unit_cost: float
    list_price: float
    min_margin_pct: float
    floor_price: float
    tier_discount_pct: float
    standard_price: float
    stock_qty: int
    stock_ok: bool
    lead_time_days: int
    warranty_months: int
    tax_category: str
    value_adds: list[ValueAddOption] = Field(default_factory=list)


class ExcludedLine(BaseModel):
    line_no: int
    description: str
    reason: str


class InternalPricing(BaseModel):
    base_currency: str
    lines: list[CostedLine]
    excluded: list[ExcludedLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- competitive strategy


class MarketOffer(BaseModel):
    competitor: str
    competitor_id: str
    positioning: str
    unit_price: float
    currency: str
    unit_price_base: float
    warranty_months: int
    lead_time_days: int
    in_stock: bool
    reliability: float
    bundle: str | None = None
    promotion: str | None = None


class MarketView(BaseModel):
    offers: list[MarketOffer] = Field(default_factory=list)
    count: int = 0
    min: float | None = None
    median: float | None = None
    max: float | None = None
    best: MarketOffer | None = None


class Scenario(BaseModel):
    label: str
    unit_price: float
    bundle: str | None = None
    margin_pct: float
    win_probability: float
    expected_profit: float
    feasible: bool
    note: str | None = None


class CurvePoint(BaseModel):
    unit_price: float
    ratio: float
    win_probability: float
    expected_profit: float


class BundleDecision(BaseModel):
    code: str
    name: str
    kind: str
    unit_cost: float
    unit_value: float
    total_cost: float
    total_value: float
    warranty_extension_months: int


class PricedLine(BaseModel):
    line_no: int
    sku: str
    name: str
    category: str
    quantity: int
    unit: str
    unit_cost: float
    list_price: float
    floor_price: float
    standard_price: float
    unit_price: float
    discount_pct: float
    bundle: BundleDecision | None = None
    revenue: float
    cost: float
    bundle_cost: float
    margin: float
    margin_pct: float
    win_probability: float
    expected_profit: float
    strategy: str
    headline: str
    rationale: list[str]
    scenarios: list[Scenario]
    curve: list[CurvePoint]
    market: MarketView
    lead_time_days: int
    warranty_months: int
    overridden: bool = False
    flags: list[str] = Field(default_factory=list)


class CompetitiveAnalysis(BaseModel):
    base_currency: str
    market_endpoint: str | None
    market_latency_ms: int | None
    market_available: bool
    lines: list[PricedLine]
    revenue: float
    cost: float
    bundle_cost: float
    margin: float
    margin_pct: float
    expected_profit: float
    win_probability: float
    strategy_counts: dict[str, int]
    below_cost_competitors: int
    summary: str
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- localisation


class TaxLine(BaseModel):
    name: str
    rate_pct: float
    amount: float


class LocalisedLine(BaseModel):
    line_no: int
    sku: str
    name: str
    description: str
    quantity: int
    unit: str
    unit_price: float
    net: float
    tax_regime: str
    tax_rate_pct: float
    taxes: list[TaxLine]
    tax_total: float
    gross: float
    tax_note: str | None = None
    bundle_name: str | None = None
    bundle_value: float | None = None


class Localisation(BaseModel):
    currency: str
    base_currency: str
    fx_rate: float
    fx_buffer_pct: float
    fx_effective_rate: float
    fx_source: str
    fx_as_of: str
    fx_stale: bool
    decimals: int
    jurisdiction: str
    tax_summary: str
    tax_notes: list[str]
    lines: list[LocalisedLine]
    subtotal: float
    tax_breakdown: list[TaxLine]
    tax_total: float
    grand_total: float
    grand_total_base: float
    bundled_value: float
