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

export interface User { id: number; username: string; name: string; email: string | null; title: string; provider: "password" | "google" | "sso" }

export const auth = {
  me: () => request<User | null>("/api/auth/me"),
  login: (username: string, password: string) => post<User>("/api/auth/login", { username, password }),
  register: (body: { name: string; username: string; email?: string; password: string }) => post<User>("/api/auth/register", body),
  federated: (provider: "google" | "sso", email: string, name?: string) => post<User>("/api/auth/federated", { provider, email, name }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
};

export const api = {
  dashboard: () => request<Dashboard>("/api/dashboard"),
  rfps: (params: { status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<RfpSummary[]>(`/api/rfps${qs ? `?${qs}` : ""}`);
  },
  rfp: (id: number) => request<RfpDetail>(`/api/rfps/${id}`),
  createRfp: (text: string, filename?: string) => post<RfpSummary>("/api/rfps", { text, filename }),
  uploadRfps: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<(RfpSummary & { upload_errors: string[] })[]>("/api/rfps/upload", { method: "POST", body: form });
  },
  samples: () => request<{ filename: string; title: string; text: string; kind: "text" | "file"; pages?: number; format?: string }[]>("/api/rfps/samples"),
  processSample: (filename: string) => post<RfpSummary[]>(`/api/rfps/samples/${encodeURIComponent(filename)}`),
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

  products: (params: { q?: string; category?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<Product[]>(`/api/catalog/products${qs ? `?${qs}` : ""}`);
  },
  patchProduct: (sku: string, body: Partial<Pick<Product, "unit_cost" | "list_price" | "min_margin_pct" | "stock_qty" | "lead_time_days" | "active">>) =>
    request<Product>(`/api/catalog/products/${sku}`, { method: "PATCH", body: JSON.stringify(body) }),
  valueAdds: () => request<{ code: string; name: string; kind: string; description: string; categories: string[]; basis: string; cost_rate: number; value_rate: number; warranty_extension_months: number }[]>("/api/catalog/value-adds"),
  tiers: () => request<Record<string, { min_qty: number; discount_pct: number }[]>>("/api/catalog/tiers"),

  competitors: () => request<{ id: string; name: string; hq: string; currency: string; positioning: string; serves: string[]; reliability: number; default_warranty_months: number; bundle: string | null }[]>("/api/market/competitors"),
  marketOffers: (sku: string, country: string, quantity: number) =>
    request<{ product: Product; country: string; quantity: number; offers: (Record<string, unknown> & { competitor: string; unit_price: number; currency: string; unit_price_base: number; vs_cost_pct: number; warranty_months: number; lead_time_days: number; in_stock: boolean; promotion: string | null; positioning: string; reliability: number })[]; endpoint: string; latency_ms: number }>(
      `/api/market/offers?sku=${encodeURIComponent(sku)}&country=${country}&quantity=${quantity}`,
    ),

  fx: () => request<{ base: string; source: string; as_of: string; stale: boolean; rates: Record<string, number> }>("/api/finance/fx"),
  fxRefresh: () => post<{ base: string; source: string; as_of: string; stale: boolean; rates: Record<string, number> }>("/api/finance/fx/refresh"),
  countries: () => request<{ code: string; name: string; currency: string; eu: boolean; regions: string[] }[]>("/api/finance/countries"),
  taxRules: () => request<{ country: string; region: string | null; tax_category: string; name: string; rate_pct: number; components: { name: string; rate_pct: number }[] }[]>("/api/finance/tax-rules"),
  taxPreview: (body: { country: string; region?: string; tax_id?: string; incoterm?: string }) =>
    post<{ jurisdiction: string; summary: string; notes: string[]; treatments: Record<string, { regime: string; rate_pct: number; components: { name: string; rate_pct: number }[]; note: string | null }> }>("/api/finance/tax-preview", body),

  models: () => request<Record<string, any>>("/api/models"),
  retrain: () => post<Record<string, any>>("/api/models/retrain"),
  knowledge: (q: string) =>
    request<{ query: string; sections: { id: string; score: number; signals: Record<string, number>; meta: Record<string, string>; text: string }[]; evidence: { source: string; section: string; text: string; score: number }[] }>(
      `/api/knowledge/search?q=${encodeURIComponent(q)}`,
    ),
};
