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
    city: str | None = None
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
    # Location and nature of the clause in long documents (defaults keep short requests unchanged).
    section: str | None = None
    clause: str | None = None
    page: int | None = None
    modality: Literal["mandatory", "desirable", "information"] = "information"
    actor: Literal["bidder", "buyer"] = "bidder"
    category: str = "scope"
    line_no: int | None = None
    source: Literal["text", "table"] = "text"


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


class TenderSection(BaseModel):
    id: str
    number: str | None = None
    title: str
    level: int
    kind: str
    kind_confidence: float
    parent: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    requirement_count: int = 0
    mandatory_count: int = 0
    line_nos: list[int] = Field(default_factory=list)


class TenderFact(BaseModel):
    key: str
    label: str
    value: str
    amount: float | None = None
    section: str | None = None
    page: int | None = None
    evidence: str | None = None


class KeyDate(BaseModel):
    key: str
    label: str
    date: str
    time: str | None = None
    section: str | None = None
    page: int | None = None
    evidence: str | None = None


class EligibilityCriterion(BaseModel):
    id: str
    kind: str
    label: str
    text: str
    clause: str | None = None
    section: str | None = None
    page: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    documents: str | None = None


class EvaluationMethod(BaseModel):
    method: Literal["L1", "QCBS", "Weighted", "Not stated"] = "Not stated"
    technical_weight: float | None = None
    financial_weight: float | None = None
    min_technical_score: float | None = None
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence: str | None = None


class TenderDocument(BaseModel):
    format: str
    pages: int
    pages_estimated: bool = False
    words: int = 0
    tables: int = 0
    scanned_pages: list[int] = Field(default_factory=list)
    removed_lines: int = 0
    long_form: bool = False
    sections: list[TenderSection] = Field(default_factory=list)
    facts: list[TenderFact] = Field(default_factory=list)
    key_dates: list[KeyDate] = Field(default_factory=list)
    eligibility: list[EligibilityCriterion] = Field(default_factory=list)
    evaluation: EvaluationMethod = Field(default_factory=EvaluationMethod)
    forms: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


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
    document: TenderDocument | None = None


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
    #: Value-adds the tender makes mandatory (e.g. a 5-year warranty), folded into cost and price.
    included_addons: list[ValueAddOption] = Field(default_factory=list)
    warranty_required_months: int | None = None


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
    equivalent: str | None = None
    source: str = "Market feed"
    observed_on: str | None = None


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
    description: str = ""


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


class AwardOption(BaseModel):
    label: str
    total: float
    margin: float
    margin_pct: float
    feasible: bool
    outcome: str


class AwardAnalysis(BaseModel):
    rule: Literal["L1", "QCBS", "Weighted"]
    our_total: float
    cost_total: float
    floor_total: float
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    lowest_competitor: str | None = None
    lowest_total: float | None = None
    rank: int | None = None
    gap_pct: float | None = None
    target_total: float | None = None
    target_feasible: bool = False
    target_prices: dict[str, float] = Field(default_factory=dict)
    msme_band_pct: float | None = None
    msme_match: bool = False
    technical_score: float | None = None
    competitor_technical_score: float | None = None
    combined_score: float | None = None
    best_competitor_combined: float | None = None
    reverse_auction: bool = False
    walk_away_total: float | None = None
    options: list[AwardOption] = Field(default_factory=list)
    recommendation: str
    reasons: list[str] = Field(default_factory=list)


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
    award: AwardAnalysis | None = None
    #: The pricing agent's summary of the bid strategy (when the language model is enabled).
    agent_summary: str | None = None


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


# --------------------------------------------------------------------------- proposal


class Evidence(BaseModel):
    source: str
    section: str
    text: str
    score: float


class ComplianceRow(BaseModel):
    ref: str
    requirement: str
    type: str
    status: Literal["Complies", "Complies with note", "Clarification required", "Deviation", "Noted"]
    response: str
    evidence: list[Evidence] = Field(default_factory=list)
    req_id: str | None = None


class Milestone(BaseModel):
    label: str
    day: int
    detail: str


class Proposal(BaseModel):
    quote_number: str
    version: int
    issue_date: str
    valid_until: str
    salutation: str
    cover_letter: list[str]
    executive_summary: list[str]
    highlights: list[str]
    compliance: list[ComplianceRow]
    compliance_counts: dict[str, int]
    delivery_plan: list[str]
    milestones: list[Milestone]
    inclusions: list[dict[str, Any]]
    terms: list[str]
    signatory: dict[str, str]
    retrieval_log: list[dict[str, Any]]
    documents: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- tender compliance

ComplianceStatus = Literal["Complies", "Complies with note", "Clarification required", "Deviation", "Noted"]
EligibilityStatus = Literal["Meets", "Documents required", "Needs review", "Does not meet"]


class ComplianceItem(BaseModel):
    id: str
    clause: str | None = None
    section: str | None = None
    section_title: str | None = None
    page: int | None = None
    text: str
    category: str
    modality: str
    line_no: int | None = None
    status: ComplianceStatus
    response: str
    basis: str
    verify: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    risk: str | None = None
    overridden: bool = False


class EligibilityCheck(BaseModel):
    id: str
    kind: str
    label: str
    text: str
    clause: str | None = None
    page: int | None = None
    status: EligibilityStatus
    position: str
    evidence: list[str] = Field(default_factory=list)
    documents: str | None = None
    overridden: bool = False


class RiskFlag(BaseModel):
    title: str
    detail: str
    severity: Literal["high", "medium", "low"]
    clause: str | None = None
    page: int | None = None


class ChecklistItem(BaseModel):
    name: str
    status: Literal["Ready", "To prepare", "To obtain"]
    source: str | None = None
    note: str | None = None


class ComplianceReport(BaseModel):
    items: list[ComplianceItem]
    eligibility: list[EligibilityCheck]
    eligibility_verdict: Literal["Eligible", "Eligible subject to documents", "Review required", "Not eligible", "Not assessed"]
    recommendation: Literal["Bid", "Bid with clarifications", "Do not bid"]
    reasons: list[str]
    counts: dict[str, int]
    mandatory_total: int
    mandatory_met: int
    risks: list[RiskFlag] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    contract_value_estimate: float = 0.0
    summary: str
