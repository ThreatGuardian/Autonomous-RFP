import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, FileSpreadsheet, History, Info, Search, Upload } from "lucide-react";
import { useDeferredValue, useRef, useState } from "react";
import { Page, PageHeader } from "../components/layout/Shell";
import { Badge, Button, Card, Field, Segmented, Sheet, Skeleton } from "../components/ui";
import { api, type ImportPreview } from "../lib/api";
import type { Product } from "../lib/types";
import { CATEGORY_LABEL, date, getBaseCurrency, money, pct, titleCase } from "../lib/format";

export default function Catalogue() {
  const [view, setView] = useState<"products" | "services" | "tiers">("products");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [edit, setEdit] = useState<Product | null>(null);
  const [importing, setImporting] = useState(false);
  const deferred = useDeferredValue(q.trim());
  const products = useQuery({ queryKey: ["products", deferred, category], queryFn: () => api.products({ q: deferred || undefined, category: category || undefined }) });
  const all = useQuery({ queryKey: ["products", "", ""], queryFn: () => api.products() });
  const categories = Array.from(new Set((all.data ?? []).map((p) => p.category)));

  return (
    <>
      <PageHeader title="Catalogue" description="Internal pricing database: landed cost, list price, margin floor, stock and lead time for every product."
        actions={<>
          <Segmented value={view} onChange={setView} items={[{ value: "products", label: "Products" }, { value: "services", label: "Bundle services" }, { value: "tiers", label: "Volume tiers" }]} />
          <Button icon={<Upload className="size-4" />} onClick={() => setImporting(true)}>Import</Button>
        </>} />
      <Page>
        {view === "products" && (
          <div className="card overflow-hidden">
            <div className="flex items-center gap-3 border-b border-line px-4 py-3">
              <div className="relative w-80">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-subtle" />
                <input className="input h-8 pl-8" placeholder="Search by description, e.g. “27 inch 4K monitor”" value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
              <select className="input h-8 w-48" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {categories.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? c}</option>)}
              </select>
              <span className="ml-auto text-[12px] text-muted">{products.data?.length ?? 0} products{deferred && " · ranked by relevance"}</span>
            </div>
            {products.isLoading ? <div className="space-y-2 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div> : (
              <div className="max-h-[calc(100vh-240px)] overflow-auto">
                <table className="table-base">
                  <thead><tr><th>Product</th><th>Category</th><th className="!text-right">Landed cost</th><th className="!text-right">List price</th><th className="!text-right">List margin</th><th className="!text-right">Floor</th><th className="!text-right">Stock</th><th className="!text-right">Lead time</th><th /></tr></thead>
                  <tbody>
                    {products.data?.map((p) => (
                      <tr key={p.sku} className={clsx("hover:bg-[#fafbfc]", !p.active && "opacity-50")}>
                        <td className="max-w-[360px]"><div className="truncate font-medium">{p.name}</div><div className="text-[11.5px] text-muted"><span className="font-mono">{p.sku}</span> · {p.mpn}{p.hsn && <> · Tax code {p.hsn}</>}</div></td>
                        <td><Badge>{CATEGORY_LABEL[p.category] ?? p.category}</Badge></td>
                        <td className="text-right tnum">{money(p.unit_cost)}</td>
                        <td className="text-right tnum">{money(p.list_price)}</td>
                        <td className="text-right tnum">{pct(p.list_margin_pct)}</td>
                        <td className="text-right tnum text-muted">{money(p.floor_price)}<div className="text-[11px]">min {p.min_margin_pct}%</div></td>
                        <td className={clsx("text-right tnum", p.stock_qty < 20 && p.stock_qty < 99999 && "text-amber-700")}>{p.stock_qty >= 99999 ? "Licensed" : p.stock_qty.toLocaleString()}</td>
                        <td className="text-right tnum">{p.lead_time_days} d</td>
                        <td className="text-right"><Button size="sm" variant="ghost" onClick={() => setEdit(p)}>Edit</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
        {view === "services" && <Services />}
        {view === "tiers" && <Tiers />}
      </Page>
      {edit && <EditProduct product={edit} onClose={() => setEdit(null)} />}
      {importing && <ImportSheet onClose={() => setImporting(false)} />}
    </>
  );
}

function EditProduct({ product, onClose }: { product: Product; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ unit_cost: product.unit_cost, list_price: product.list_price, min_margin_pct: product.min_margin_pct, stock_qty: product.stock_qty, lead_time_days: product.lead_time_days, active: product.active });
  const save = useMutation({ mutationFn: () => api.patchProduct(product.sku, form), onSuccess: () => { qc.invalidateQueries({ queryKey: ["products"] }); onClose(); } });
  const num = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });
  return (
    <Sheet open onClose={onClose} width={520} title={product.name} subtitle={`${product.sku} · ${product.mpn}`}
      footer={<div className="flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save changes</Button></div>}>
      <p className="mb-5 text-[12.5px] leading-[1.6] text-muted">{product.description}</p>
      <div className="grid grid-cols-2 gap-4">
        <Field label={`Landed cost (${getBaseCurrency()})`}><input className="input tnum" type="number" value={form.unit_cost} onChange={num("unit_cost")} /></Field>
        <Field label={`List price (${getBaseCurrency()})`}><input className="input tnum" type="number" value={form.list_price} onChange={num("list_price")} /></Field>
        <Field label="Minimum margin %" hint={`Floor ${money(form.unit_cost * (1 + form.min_margin_pct / 100))}`}><input className="input tnum" type="number" value={form.min_margin_pct} onChange={num("min_margin_pct")} /></Field>
        <Field label="Stock on hand"><input className="input tnum" type="number" value={form.stock_qty} onChange={num("stock_qty")} /></Field>
        <Field label="Lead time (days)"><input className="input tnum" type="number" value={form.lead_time_days} onChange={num("lead_time_days")} /></Field>
        <Field label="Status"><select className="input" value={form.active ? "1" : "0"} onChange={(e) => setForm({ ...form, active: e.target.value === "1" })}><option value="1">Active</option><option value="0">Inactive</option></select></Field>
      </div>
      <div className="mt-6">
        <div className="label mb-2">Specification</div>
        <div className="flex flex-wrap gap-1.5">{Object.entries(product.specs).map(([k, v]) => <Badge key={k}>{titleCase(k)}: {String(v)}</Badge>)}</div>
      </div>
      <PriceHistory sku={product.sku} />
      {save.isError && <div className="mt-4 text-[12.5px] text-rose-700">{(save.error as Error).message}</div>}
    </Sheet>
  );
}

function PriceHistory({ sku }: { sku: string }) {
  const { data } = useQuery({ queryKey: ["price-history", sku], queryFn: () => api.priceHistory(sku) });
  if (!data?.length) return null;
  return (
    <div className="mt-6">
      <div className="label mb-2 flex items-center gap-1.5"><History className="size-3.5" /> Price history</div>
      <div className="overflow-hidden rounded-lg border border-line">
        <table className="w-full text-[12px]">
          <thead className="bg-[#f8f9fb] text-left text-muted"><tr><th className="px-3 py-1.5 font-medium">From</th><th className="px-3 py-1.5 text-right font-medium">Cost</th><th className="px-3 py-1.5 text-right font-medium">List</th><th className="px-3 py-1.5 text-right font-medium">Stock</th><th className="px-3 py-1.5 font-medium">Source</th></tr></thead>
          <tbody>
            {[...data].reverse().map((v, i) => (
              <tr key={i} className="border-t border-line">
                <td className="px-3 py-1.5 tnum">{date(v.effective_from)}</td>
                <td className="px-3 py-1.5 text-right tnum">{money(v.unit_cost)}</td>
                <td className="px-3 py-1.5 text-right tnum">{money(v.list_price)}</td>
                <td className="px-3 py-1.5 text-right tnum">{v.stock_qty.toLocaleString()}</td>
                <td className="max-w-[140px] truncate px-3 py-1.5 text-muted">{v.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const FIELD_LABEL: Record<string, string> = {
  sku: "SKU", mpn: "Part number", name: "Item name", brand: "Brand", category: "Category", hsn: "Tax code (HSN/SAC)", gst: "Tax rate",
  unit_cost: "Landed cost", list_price: "List price", stock_qty: "Stock", lead_time_days: "Lead time", warranty_months: "Warranty",
  min_margin_pct: "Min. margin", unit: "Unit", description: "Description", gst_rate_pct: "Tax rate",
};
const ACTION_TONE = { create: "blue", update: "gold", unchanged: "neutral", skip: "red" } as const;
const ACTION_LABEL = { create: "New", update: "Update", unchanged: "No change", skip: "Skipped" } as const;

function fmtVal(field: string, v: unknown) {
  if (typeof v === "number" && ["unit_cost", "list_price"].includes(field)) return money(v);
  if (typeof v === "number" && field === "gst_rate_pct") return `${v}%`;
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

function ImportSheet({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [plan, setPlan] = useState<ImportPreview | null>(null);
  const [filter, setFilter] = useState<"all" | "changes" | "issues">("changes");
  const preview = useMutation({ mutationFn: (f: File) => api.importPreview(f), onSuccess: setPlan });
  const commit = useMutation({
    mutationFn: () => api.importCommit(plan!.token),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["products"] }); qc.invalidateQueries({ queryKey: ["imports"] }); onClose(); },
  });
  const history = useQuery({ queryKey: ["imports"], queryFn: api.imports });
  const rows = (plan?.rows ?? []).filter((r) =>
    filter === "all" ? true : filter === "issues" ? r.issues.length > 0 : r.action !== "unchanged");
  const applicable = plan ? plan.counts.create + plan.counts.update : 0;

  return (
    <Sheet open onClose={onClose} width={880} title="Import company data"
      subtitle="Catalogue, prices, stock, tax codes and rates from a CSV or Excel sheet, or a Tally stock-item export (XML)"
      footer={<div className="flex items-center justify-between">
        <span className="text-[12px] text-muted">{plan ? `${applicable} product(s) will change. Every price change is kept in the price history.` : "Nothing is changed until you apply the import."}</span>
        <div className="flex gap-2"><Button onClick={onClose}>Close</Button>
          <Button variant="primary" disabled={!plan || !applicable} loading={commit.isPending} onClick={() => commit.mutate()}>Apply import</Button></div>
      </div>}>
      <input ref={input} type="file" className="hidden" accept=".csv,.xlsx,.xlsm,.xml,.txt"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) preview.mutate(f); e.target.value = ""; }} />
      {!plan && (
        <button onClick={() => input.current?.click()} disabled={preview.isPending}
          className="group flex w-full flex-col items-center rounded-xl border border-dashed border-line-strong bg-[#fafbfc] px-6 py-10 text-center transition-colors hover:border-ink/30 hover:bg-white">
          <FileSpreadsheet className="size-8 text-subtle transition-transform duration-300 group-hover:-translate-y-0.5" />
          <div className="mt-3 text-[14px] font-semibold">{preview.isPending ? "Reading the file…" : "Choose a file to preview"}</div>
          <div className="mt-1 max-w-md text-[12.5px] text-muted">Columns are recognised by name — "Item Name", "Stock Group", "Purchase Rate", "Closing Qty", "HSN/SAC" and similar headers from Tally, Busy or a distributor price list all work.</div>
          <a href="/api/catalog/import/template" onClick={(e) => e.stopPropagation()} className="mt-3 text-[12px] font-medium text-ink underline decoration-line-strong underline-offset-4">Download a template</a>
        </button>
      )}
      {preview.isError && <div className="mt-3 text-[12.5px] text-rose-700">{(preview.error as Error).message}</div>}
      {plan && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            <Badge tone="neutral">{plan.filename}</Badge>
            <Badge tone="neutral">{plan.format === "tally" ? "Tally XML" : plan.format.toUpperCase()}{plan.sheet ? ` · ${plan.sheet}` : ""}</Badge>
            <span className="ml-auto flex gap-2">
              <Badge tone="blue">{plan.counts.create} new</Badge><Badge tone="gold">{plan.counts.update} updated</Badge>
              <Badge>{plan.counts.unchanged} unchanged</Badge>{plan.counts.skip > 0 && <Badge tone="red">{plan.counts.skip} skipped</Badge>}
            </span>
          </div>
          <div>
            <div className="label mb-2">Column mapping</div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(plan.mapping).map(([f, h]) => <Badge key={f}>{h} → {FIELD_LABEL[f] ?? f}</Badge>)}
              {plan.unmapped.map((h) => <Badge key={h} tone="neutral" className="opacity-60">{h} (ignored)</Badge>)}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="label">Rows</div>
            <Segmented value={filter} onChange={setFilter} items={[{ value: "changes", label: "Changes" }, { value: "issues", label: `Issues (${plan.issues})` }, { value: "all", label: "All" }]} />
          </div>
          <div className="max-h-[48vh] overflow-auto rounded-xl border border-line">
            <table className="table-base">
              <thead><tr><th className="w-12">Row</th><th>Item</th><th className="w-24">Action</th><th>What changes</th></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={4} className="py-8 text-center text-muted">Nothing to show.</td></tr>}
                {rows.map((r) => (
                  <tr key={r.row}>
                    <td className="text-muted tnum">{r.row}</td>
                    <td className="max-w-[260px]"><div className="truncate font-medium">{r.name}</div>{r.sku && <div className="font-mono text-[11px] text-muted">{r.sku}</div>}</td>
                    <td><Badge tone={ACTION_TONE[r.action]}>{ACTION_LABEL[r.action]}</Badge></td>
                    <td className="text-[12px]">
                      {r.action === "update" && Object.entries(r.changes).map(([f, [a, b]]) => (
                        <div key={f}><span className="text-muted">{FIELD_LABEL[f] ?? f}:</span> <span className="line-through decoration-rose-300">{fmtVal(f, a)}</span> → <span className="font-medium">{fmtVal(f, b)}</span></div>
                      ))}
                      {r.action === "create" && <div className="text-muted">{CATEGORY_LABEL[String(r.values.category)] ?? String(r.values.category)} · cost {fmtVal("unit_cost", r.values.unit_cost)} · list {fmtVal("list_price", r.values.list_price)}{r.values.stock_qty !== undefined && ` · stock ${r.values.stock_qty}`}</div>}
                      {r.issues.map((i, k) => (
                        <div key={k} className={clsx("mt-0.5 flex items-start gap-1", i.severity === "error" ? "text-rose-700" : i.severity === "warning" ? "text-amber-700" : "text-muted")}>
                          {i.severity === "info" ? <Info className="mt-0.5 size-3 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3 shrink-0" />}{i.message}
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button size="sm" variant="ghost" onClick={() => { setPlan(null); input.current?.click(); }}>Choose another file</Button>
        </div>
      )}
      {!plan && !!history.data?.length && (
        <div className="mt-6">
          <div className="label mb-2">Recent imports</div>
          <div className="divide-y divide-line rounded-xl border border-line">
            {history.data.slice(0, 5).map((b) => (
              <div key={b.id} className="flex items-center gap-3 px-3.5 py-2.5 text-[12.5px]">
                <FileSpreadsheet className="size-4 text-subtle" />
                <span className="font-medium">{b.filename}</span>
                <span className="text-muted">{date(b.created_at)} · {b.actor}</span>
                <span className="ml-auto text-muted tnum">{b.created} new · {b.updated} updated{b.skipped ? ` · ${b.skipped} skipped` : ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Sheet>
  );
}

function Services() {
  const { data } = useQuery({ queryKey: ["value-adds"], queryFn: api.valueAdds });
  return (
    <Card title="Bundle services" subtitle="Warranty, service and support offerings the pricing engine may include at no charge to compete on value instead of price" bodyClassName="p-0">
      <table className="table-base">
        <thead><tr><th>Service</th><th>Type</th><th>Applies to</th><th className="!text-right">Our cost</th><th className="!text-right">Client value</th></tr></thead>
        <tbody>
          {data?.map((v) => (
            <tr key={v.code}>
              <td className="max-w-[420px]"><div className="font-medium">{v.name}</div><div className="text-[12px] text-muted">{v.description}</div></td>
              <td><Badge tone={v.kind === "warranty" ? "gold" : v.kind === "support" ? "violet" : "blue"}>{titleCase(v.kind)}</Badge></td>
              <td className="max-w-[260px] text-[12px] text-muted">{v.categories.map((c) => CATEGORY_LABEL[c] ?? c).join(", ")}</td>
              <td className="text-right tnum">{v.basis === "percent" ? `${v.cost_rate}% of cost` : money(v.cost_rate)}</td>
              <td className="text-right tnum">{v.basis === "percent" ? `${v.value_rate}% of list` : money(v.value_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Tiers() {
  const { data } = useQuery({ queryKey: ["tiers"], queryFn: api.tiers });
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {Object.entries(data ?? {}).map(([cat, tiers]) => (
        <Card key={cat} title={cat === "*" ? "All other categories" : CATEGORY_LABEL[cat] ?? cat}>
          <table className="w-full text-[12.5px]"><tbody>
            {tiers.map((t) => <tr key={t.min_qty} className="border-b border-line last:border-0"><td className="py-1.5 text-muted">{t.min_qty}+ units</td><td className="py-1.5 text-right font-medium tnum">{t.discount_pct}% off list</td></tr>)}
          </tbody></table>
        </Card>
      ))}
    </div>
  );
}
