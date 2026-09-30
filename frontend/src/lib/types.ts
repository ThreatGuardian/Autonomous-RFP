export type RfpStatus = "queued" | "processing" | "review" | "approved" | "rejected" | "failed";

export interface RfpSummary {
  id: number;
  reference: string;
  title: string;
  status: RfpStatus;
  running: boolean;
  client_name: string | null;
  client_country: string | null;
  currency: string | null;
  due_date: string | null;
  total_base: number | null;
  total_client: number | null;
  margin_pct: number | null;
  win_probability: number | null;
  strategy_summary: string | null;
  line_count: number;
  below_cost_competitors: number | null;
  recommendation: "Bid" | "Bid with clarifications" | "Do not bid" | null;
  eligibility_verdict: string | null;
  pages: number | null;
  source_filename: string | null;
  created_at: string;
  updated_at: string;
  error: string | null;
}

export interface LogEntry { t_ms: number; level: "info" | "decision" | "warning"; message: string; data: Record<string, unknown> }
export interface StageRun {
  id: number; stage: string; agent: string; status: "running" | "completed" | "failed";
  started_at: string; finished_at: string | null; duration_ms: number | null; summary: string | null; log: LogEntry[];
}
export interface ApprovalEvent { id: number; action: string; actor: string; note: string | null; payload: Record<string, unknown>; created_at: string }

export interface ProductMatch { sku: string; name: string; category: string; score: number; retrieval_score: number; spec_fit: number | null; reasons: string[] }
export interface RequestedItem {
  line_no: number; text: string; description: string; quantity: number; quantity_source: string; unit: string | null;
  category: string | null; category_confidence: number; specs: Record<string, unknown>; brand: string | null;
  candidates: ProductMatch[]; selected_sku: string | null; match_confidence: number; status: "matched" | "ambiguous" | "unmatched";
}
export interface Requirement {
  id: string; text: string; type: string; confidence: number;
  section?: string | null; clause?: string | null; page?: number | null;
  modality?: "mandatory" | "desirable" | "information"; actor?: "bidder" | "buyer"; category?: string;
  line_no?: number | null; source?: "text" | "table";
}
export interface TenderSection {
  id: string; number: string | null; title: string; level: number; kind: string; kind_confidence: number; parent: string | null;
  page_start: number | null; page_end: number | null; requirement_count: number; mandatory_count: number; line_nos: number[];
}
export interface TenderFact { key: string; label: string; value: string; amount: number | null; section: string | null; page: number | null; evidence: string | null }
export interface KeyDate { key: string; label: string; date: string; time: string | null; section: string | null; page: number | null; evidence: string | null }
export interface TenderDocument {
  format: string; pages: number; pages_estimated: boolean; words: number; tables: number; scanned_pages: number[]; removed_lines: number;
  long_form: boolean; sections: TenderSection[]; facts: TenderFact[]; key_dates: KeyDate[];
  eligibility: { id: string; kind: string; label: string; text: string; clause: string | null; page: number | null }[];
  evaluation: { method: "L1" | "QCBS" | "Weighted" | "Not stated"; technical_weight: number | null; financial_weight: number | null;
    min_technical_score: number | null; criteria: { criterion: string; marks: number }[]; notes: string[]; evidence: string | null };
  forms: string[]; notes: string[];
}
export type ComplianceStatus = "Complies" | "Complies with note" | "Clarification required" | "Deviation" | "Noted";
export type EligibilityStatus = "Meets" | "Documents required" | "Needs review" | "Does not meet";
export interface Evidence { source: string; section: string; text: string; score: number }
export interface ComplianceItem {
  id: string; clause: string | null; section: string | null; section_title: string | null; page: number | null; text: string;
  category: string; modality: string; line_no: number | null; status: ComplianceStatus; response: string; basis: string;
  verify: boolean; evidence: Evidence[]; risk: string | null; overridden: boolean;
}
export interface EligibilityCheck {
  id: string; kind: string; label: string; text: string; clause: string | null; page: number | null; status: EligibilityStatus;
  position: string; evidence: string[]; documents: string | null; overridden: boolean;
}
export interface RiskFlag { title: string; detail: string; severity: "high" | "medium" | "low"; clause: string | null; page: number | null }
export interface ComplianceReport {
  items: ComplianceItem[]; eligibility: EligibilityCheck[];
  eligibility_verdict: "Eligible" | "Eligible subject to documents" | "Review required" | "Not eligible" | "Not assessed";
  recommendation: "Bid" | "Bid with clarifications" | "Do not bid"; reasons: string[]; counts: Record<string, number>;
  mandatory_total: number; mandatory_met: number; risks: RiskFlag[];
  checklist: { name: string; status: "Ready" | "To prepare" | "To obtain"; source: string | null; note: string | null }[];
  benefits: string[]; contract_value_estimate: number; summary: string;
}
export interface ParsedRfp {
  title: string; client_reference: string | null;
  client: {
    name: string | null; contact_name: string | null; email: string | null; phone: string | null; country: string | null;
    country_name: string | null; region: string | null; city: string | null; is_eu: boolean; segment: string; segment_source: string;
    tax_id: string | null; customer_id: number | null; repeat_customer: boolean;
  };
  currency: { code: string; source: string; evidence: string | null };
  issued_on: string | null; due_date: string | null; delivery_by: string | null;
  terms: {
    incoterm: string | null; incoterm_source: string; delivery_location: string | null; delivery_days: number | null;
    payment_days: number | null; advance_pct: number | null; warranty_months_required: number | null;
    price_weight_pct: number | null; lowest_price_award: boolean;
  };
  line_items: RequestedItem[]; requirements: Requirement[]; requirement_counts: Record<string, number>;
  warnings: string[]; stats: Record<string, number>; document?: TenderDocument | null;
}

export interface ValueAddOption { code: string; name: string; kind: string; description: string; unit_cost: number; unit_value: number; warranty_extension_months: number }
export interface CostedLine {
  line_no: number; sku: string; mpn: string; name: string; category: string; quantity: number; unit: string;
  unit_cost: number; list_price: number; floor_price: number; standard_price: number; tier_discount_pct: number;
  stock_qty: number; stock_ok: boolean; lead_time_days: number; warranty_months: number; value_adds: ValueAddOption[];
  included_addons?: ValueAddOption[]; warranty_required_months?: number | null;
}
export interface MarketOffer {
  competitor: string; competitor_id: string; positioning: string; unit_price: number; currency: string; unit_price_base: number;
  warranty_months: number; lead_time_days: number; in_stock: boolean; reliability: number; bundle: string | null; promotion: string | null;
}
export interface Scenario { label: string; unit_price: number; bundle: string | null; margin_pct: number; win_probability: number; expected_profit: number; feasible: boolean; note: string | null }
export interface CurvePoint { unit_price: number; ratio: number; win_probability: number; expected_profit: number }
export interface PricedLine {
  line_no: number; sku: string; name: string; category: string; quantity: number; unit: string;
  unit_cost: number; list_price: number; floor_price: number; standard_price: number; unit_price: number; discount_pct: number;
  bundle: { code: string; name: string; kind: string; unit_cost: number; unit_value: number; total_cost: number; total_value: number; warranty_extension_months: number; description: string } | null;
  revenue: number; cost: number; bundle_cost: number; margin: number; margin_pct: number; win_probability: number; expected_profit: number;
  strategy: string; headline: string; rationale: string[]; scenarios: Scenario[]; curve: CurvePoint[];
  market: { offers: MarketOffer[]; count: number; min: number | null; median: number | null; max: number | null; best: MarketOffer | null };
  lead_time_days: number; warranty_months: number; overridden: boolean; flags: string[];
}
export interface CompetitiveAnalysis {
  base_currency: string; market_endpoint: string | null; market_latency_ms: number | null; market_available: boolean;
  lines: PricedLine[]; revenue: number; cost: number; bundle_cost: number; margin: number; margin_pct: number;
  expected_profit: number; win_probability: number; strategy_counts: Record<string, number>; below_cost_competitors: number;
  summary: string; warnings: string[];
}
export interface TaxLine { name: string; rate_pct: number; amount: number }
export interface Localisation {
  currency: string; base_currency: string; fx_rate: number; fx_buffer_pct: number; fx_effective_rate: number; fx_source: string;
  fx_as_of: string; fx_stale: boolean; decimals: number; jurisdiction: string; tax_summary: string; tax_notes: string[];
  lines: { line_no: number; sku: string; name: string; description: string; quantity: number; unit: string; unit_price: number; net: number; tax_regime: string; tax_rate_pct: number; taxes: TaxLine[]; tax_total: number; gross: number; tax_note: string | null; bundle_name: string | null; bundle_value: number | null }[];
  subtotal: number; tax_breakdown: TaxLine[]; tax_total: number; grand_total: number; grand_total_base: number; bundled_value: number;
}
export interface Proposal {
  quote_number: string; version: number; issue_date: string; valid_until: string; salutation: string;
  cover_letter: string[]; executive_summary: string[]; highlights: string[];
  compliance: { ref: string; requirement: string; type: string; status: string; response: string; evidence: Evidence[]; req_id?: string | null }[];
  compliance_counts: Record<string, number>; delivery_plan: string[]; milestones: { label: string; day: number; detail: string }[];
  inclusions: { line_no: number; item: string; service: string; quantity: number; value: number; description: string }[];
  terms: string[]; signatory: Record<string, string>; retrieval_log: { purpose: string; query: string; passages: { source: string; section: string; score: number }[] }[];
  documents: { quotation?: string; memo?: string; report?: string; compliance?: string };
}

export interface RfpDetail extends RfpSummary {
  raw_text: string; parsed: ParsedRfp | null;
  pricing: { costing?: { lines: CostedLine[]; excluded: { line_no: number; description: string; reason: string }[]; warnings: string[] }; strategy?: CompetitiveAnalysis; localisation?: Localisation } | null;
  compliance: ComplianceReport | null; has_original: boolean;
  proposal: Proposal | null; overrides: Record<string, unknown>; stages: StageRun[]; stage_order: string[]; events: ApprovalEvent[];
}

export interface Dashboard {
  counts: Record<string, number>; pipeline_value: number; approved_value: number; weighted_value: number;
  average_margin_pct: number | null; below_cost_encounters: number; strategy_mix: Record<string, number>;
  average_stage_ms: Record<string, number>; average_turnaround_s: number | null; intake_by_day: { date: string; received: number }[];
  base_currency: string;
}

export interface Product {
  sku: string; mpn: string; name: string; brand: string; category: string; description: string; specs: Record<string, unknown>;
  keywords: string[]; unit: string; unit_cost: number; list_price: number; min_margin_pct: number; floor_price: number;
  stock_qty: number; lead_time_days: number; warranty_months: number; tax_category: string; active: boolean; list_margin_pct: number;
}
