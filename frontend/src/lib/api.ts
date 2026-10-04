import type { Dashboard, Product, RfpDetail, RfpSummary } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && !path.startsWith("/api/auth/") && window.location.pathname.startsWith("/app")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export interface RepriceBody {
  lines?: Record<string, LineOverride>; currency?: string; fx_buffer_pct?: number; reset?: boolean; actor?: string; note?: string;
  client?: { name?: string | null; country?: string | null; region?: string | null; tax_id?: string | null; segment?: string | null };
  incoterm?: string; add_lines?: { sku: string; quantity: number }[]; remove_added?: number[];
}

export interface ComplianceBody {
  items?: Record<string, { status: string; response?: string }>;
  eligibility?: Record<string, { status: string; position?: string }>;
  clear?: string[]; actor?: string; note?: string;
}

export interface LineOverride { unit_price?: number; bundle?: string; clear_bundle?: boolean; sku?: string; quantity?: number; exclude?: boolean }

export interface Outcome { result: "won" | "lost" | "cancelled"; our_total: number | null; winning_total: number | null; winner: string | null; note: string | null; recorded_at: string }

export interface ImportRow {
  row: number; action: "create" | "update" | "unchanged" | "skip"; sku: string | null; name: string;
  values: Record<string, unknown>; changes: Record<string, [unknown, unknown]>; issues: { field: string; severity: "error" | "warning" | "info"; message: string }[];
}
export interface ImportPreview {
  token: string; filename: string; format: "csv" | "xlsx" | "tally"; sheet: string | null; mapping: Record<string, string>; unmapped: string[];
  counts: { create: number; update: number; unchanged: number; skip: number }; rows: ImportRow[]; issues: number;
}
export interface ImportBatch { id: number; filename: string; format: string; rows: number; created: number; updated: number; unchanged: number; skipped: number; issues: number; actor: string; created_at: string }
export interface Observation {
  id: number; competitor_id: string; competitor: string; mpn: string; product: string | null; unit_price: number; currency: string; quantity: number;
  warranty_months: number | null; observed_on: string; adapter: "quotes" | "awards" | "web" | "feed"; source: string; reference: string | null; collected_by: string | null;
}

export interface ClientRegion { country: string; region?: string | null }
export interface Region {
  code: string; name: string; currency: string; eu: boolean; area: string; regions: string[]; tax: string; conventions: string[];
}
export interface Workspace { operating_region: { country: string; region: string | null }; base_currency: string; company: string }

export interface User { id: number; username: string; name: string; email: string | null; title: string; provider: "password" | "firebase" }
export interface AuthConfig { signup: boolean; firebase: boolean; demo: boolean }

export const auth = {
  me: () => request<User | null>("/api/auth/me"),
  login: (username: string, password: string) => post<User>("/api/auth/login", { username, password }),
  register: (body: { name: string; username: string; email?: string; password: string }) => post<User>("/api/auth/register", body),
  config: () => request<AuthConfig>("/api/auth/config"),
  firebaseLogin: (token: string) => post<User>("/api/auth/firebase", { token }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
};

export interface ReportBlock {
  id: string; type: "lead" | "paragraph" | "bullets" | "kpis" | "bars" | "table" | "callout" | "note";
  text?: string; tone?: "good" | "warn" | "bad" | "neutral"; items?: any[]; header?: string[]; rows?: string[][];
}
export interface ReportSection { id: string; key: string; title: string; hidden: boolean; blocks: ReportBlock[] }
export interface ChatMessage { role: "user" | "assistant"; text: string; at: string; intent?: string; confidence?: number; changes?: { section: string | null; block: string | null; action: string }[] }
export interface ReportDocument {
  title: string; subtitle: string; quote_number: string; proposal_version: number; sections: ReportSection[];
  edited: boolean; stale: boolean; updated_at: string; chat: ChatMessage[]; can_undo: boolean; can_redo: boolean;
}
export interface AssistantReply {
  reply: string; changed: boolean; changes: { section: string | null; block: string | null; action: string }[];
  intent: string; confidence: number; suggestions: string[]; document: ReportDocument;
}

export const report = {
  get: (id: number) => request<ReportDocument>(`/api/rfps/${id}/report`),
  save: (id: number, body: { title: string; sections: ReportSection[] }) =>
    request<ReportDocument>(`/api/rfps/${id}/report`, { method: "PUT", body: JSON.stringify(body) }),
  ask: (id: number, message: string) => post<AssistantReply>(`/api/rfps/${id}/report/assistant`, { message }),
  undo: (id: number) => post<ReportDocument>(`/api/rfps/${id}/report/undo`),
  redo: (id: number) => post<ReportDocument>(`/api/rfps/${id}/report/redo`),
  reset: (id: number) => post<ReportDocument>(`/api/rfps/${id}/report/reset`),
  exportUrl: (id: number, format: "pdf" | "docx") => `/api/rfps/${id}/report/export?format=${format}`,
};

export const api = {
  dashboard: () => request<Dashboard>("/api/dashboard"),
  rfps: (params: { status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<RfpSummary[]>(`/api/rfps${qs ? `?${qs}` : ""}`);
  },
  rfp: (id: number) => request<RfpDetail>(`/api/rfps/${id}`),
  createRfp: (text: string, region: ClientRegion, filename?: string) =>
    post<RfpSummary>("/api/rfps", { text, filename, client_region: region }),
  uploadRfps: (files: File[], region: ClientRegion) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("country", region.country);
    if (region.region) form.append("region", region.region);
    return request<(RfpSummary & { upload_errors: string[] })[]>("/api/rfps/upload", { method: "POST", body: form });
  },
  samples: () => request<{ filename: string; title: string; text: string; kind: "text" | "file"; pages?: number; format?: string }[]>("/api/rfps/samples"),
  processSample: (filename: string, region: ClientRegion) =>
    post<RfpSummary[]>(`/api/rfps/samples/${encodeURIComponent(filename)}`, { client_region: region }),
  regions: () => request<Region[]>("/api/regions"),
  workspace: () => request<Workspace>("/api/workspace"),
  setOperatingRegion: (place: ClientRegion) => request<Workspace>("/api/workspace", { method: "PUT", body: JSON.stringify(place) }),
  updateCompliance: (id: number, body: ComplianceBody) => post<{ status: string }>(`/api/rfps/${id}/compliance`, body),
  originalUrl: (id: number) => `/api/rfps/${id}/original`,
  reprice: (id: number, body: RepriceBody) =>
    post<{ status: string }>(`/api/rfps/${id}/reprice`, body),
  approve: (id: number, actor: string, note?: string) => post(`/api/rfps/${id}/approve`, { actor, note }),
  reject: (id: number, actor: string, note?: string) => post(`/api/rfps/${id}/reject`, { actor, note }),
  reopen: (id: number, actor: string, note?: string) => post(`/api/rfps/${id}/reopen`, { actor, note }),
  retry: (id: number) => post(`/api/rfps/${id}/retry`),
  remove: (id: number) => request<void>(`/api/rfps/${id}`, { method: "DELETE" }),
  documentUrl: (id: number, kind: "quotation" | "memo" | "report" | "compliance") => `/api/rfps/${id}/documents/${kind}`,
  packUrl: (id: number) => `/api/rfps/${id}/pack`,
  outcome: (id: number) => request<{ outcome: Outcome | null }>(`/api/rfps/${id}/outcome`),
  setOutcome: (id: number, body: { result: "won" | "lost" | "cancelled"; winning_total?: number; winner?: string; note?: string; actor?: string }) =>
    post<{ outcome: Outcome }>(`/api/rfps/${id}/outcome`, body),
  labelRequirement: (id: number, requirement_id: string, type: string) => post<{ requirement_id: string; type: string }>(`/api/rfps/${id}/labels`, { requirement_id, type }),

  products: (params: { q?: string; category?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<Product[]>(`/api/catalog/products${qs ? `?${qs}` : ""}`);
  },
  patchProduct: (sku: string, body: Partial<Pick<Product, "unit_cost" | "list_price" | "min_margin_pct" | "stock_qty" | "lead_time_days" | "active">>) =>
    request<Product>(`/api/catalog/products/${sku}`, { method: "PATCH", body: JSON.stringify(body) }),
  importPreview: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportPreview>("/api/catalog/import/preview", { method: "POST", body: form });
  },
  importCommit: (token: string, actor?: string) => post<ImportBatch>("/api/catalog/import/commit", { token, actor }),
  imports: () => request<ImportBatch[]>("/api/catalog/imports"),
  priceHistory: (sku: string) => request<{ unit_cost: number; list_price: number; stock_qty: number; effective_from: string; source: string }[]>(`/api/catalog/products/${encodeURIComponent(sku)}/history`),
  valueAdds: () => request<{ code: string; name: string; kind: string; description: string; categories: string[]; basis: string; cost_rate: number; value_rate: number; warranty_extension_months: number }[]>("/api/catalog/value-adds"),
  tiers: () => request<Record<string, { min_qty: number; discount_pct: number }[]>>("/api/catalog/tiers"),

  competitors: () => request<{ id: string; name: string; hq: string; currency: string; positioning: string; serves: string[]; reliability: number; default_warranty_months: number; bundle: string | null; brands: string[] | "*"; channel: string | null; notes: string | null }[]>("/api/market/competitors"),
  marketOffers: (sku: string, country: string, quantity: number) =>
    request<{ product: Product; country: string; quantity: number; offers: (Record<string, unknown> & { competitor: string; unit_price: number; currency: string; unit_price_base: number; vs_cost_pct: number; warranty_months: number; lead_time_days: number; in_stock: boolean; promotion: string | null; positioning: string; reliability: number; source?: string; observed_on?: string; equivalent?: string | null })[]; endpoint: string; latency_ms: number }>(
      `/api/market/offers?sku=${encodeURIComponent(sku)}&country=${country}&quantity=${quantity}`,
    ),

  marketSources: () => request<{ adapters: Record<string, { label: string; observations: number | null; latest: string | null; competitors: number }> }>("/api/market/sources"),
  observations: (params: { sku?: string; competitor?: string; adapter?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString();
    return request<Observation[]>(`/api/market/observations${qs ? `?${qs}` : ""}`);
  },
  uploadObservations: (adapter: "quotes" | "awards", file: File) => {
    const form = new FormData();
    form.append("adapter", adapter);
    form.append("file", file);
    return request<{ added: number; skipped: number; issues: { row: number; message: string }[] }>("/api/market/observations/upload", { method: "POST", body: form });
  },
  webObservation: (body: { competitor: string; html: string; url?: string; mpn?: string }) =>
    post<{ added: number; name: string | null; price: number | null; method: string | null; mpn?: string; message?: string }>("/api/market/observations/web", body),
  deleteObservation: (id: number) => request<void>(`/api/market/observations/${id}`, { method: "DELETE" }),
  fx: () => request<{ base: string; source: string; as_of: string; stale: boolean; rates: Record<string, number> }>("/api/finance/fx"),
  fxRefresh: () => post<{ base: string; source: string; as_of: string; stale: boolean; rates: Record<string, number> }>("/api/finance/fx/refresh"),
  countries: () => request<{ code: string; name: string; currency: string; eu: boolean; regions: string[] }[]>("/api/finance/countries"),
  taxRules: () => request<{ country: string; region: string | null; tax_category: string; name: string; rate_pct: number; components: { name: string; rate_pct: number }[] }[]>("/api/finance/tax-rules"),
  taxPreview: (body: { country: string; region?: string; tax_id?: string; incoterm?: string }) =>
    post<{ jurisdiction: string; summary: string; notes: string[]; treatments: Record<string, { regime: string; rate_pct: number; components: { name: string; rate_pct: number }[]; note: string | null }> }>("/api/finance/tax-preview", body),

  company: () => request<{ name: string; short_name: string; base_currency: string }>("/api/company"),
  knowledge: (q: string) =>
    request<{ query: string; sections: { id: string; score: number; signals: Record<string, number>; meta: Record<string, string>; text: string }[]; evidence: { source: string; section: string; text: string; score: number }[] }>(
      `/api/knowledge/search?q=${encodeURIComponent(q)}`,
    ),
};
