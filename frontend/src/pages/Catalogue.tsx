import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Page, PageHeader } from "../components/layout/Shell";
import { Badge, Button, Card, Field, Segmented, Sheet, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import type { Product } from "../lib/types";
import { CATEGORY_LABEL, money, pct, titleCase } from "../lib/format";

export default function Catalogue() {
  const [view, setView] = useState<"products" | "services" | "tiers">("products");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [edit, setEdit] = useState<Product | null>(null);
  const deferred = useDeferredValue(q.trim());
  const products = useQuery({ queryKey: ["products", deferred, category], queryFn: () => api.products({ q: deferred || undefined, category: category || undefined }) });
  const all = useQuery({ queryKey: ["products", "", ""], queryFn: () => api.products() });
  const categories = Array.from(new Set((all.data ?? []).map((p) => p.category)));

  return (
    <>
      <PageHeader title="Catalogue" description="Internal pricing database: landed cost, list price, margin floor, stock and lead time for every product."
        actions={<Segmented value={view} onChange={setView} items={[{ value: "products", label: "Products" }, { value: "services", label: "Bundle services" }, { value: "tiers", label: "Volume tiers" }]} />} />
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
                        <td className="max-w-[360px]"><div className="truncate font-medium">{p.name}</div><div className="text-[11.5px] text-muted"><span className="font-mono">{p.sku}</span> · {p.mpn}</div></td>
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
        <Field label="Landed cost (INR)"><input className="input tnum" type="number" value={form.unit_cost} onChange={num("unit_cost")} /></Field>
        <Field label="List price (INR)"><input className="input tnum" type="number" value={form.list_price} onChange={num("list_price")} /></Field>
        <Field label="Minimum margin %" hint={`Floor ${money(form.unit_cost * (1 + form.min_margin_pct / 100))}`}><input className="input tnum" type="number" value={form.min_margin_pct} onChange={num("min_margin_pct")} /></Field>
        <Field label="Stock on hand"><input className="input tnum" type="number" value={form.stock_qty} onChange={num("stock_qty")} /></Field>
        <Field label="Lead time (days)"><input className="input tnum" type="number" value={form.lead_time_days} onChange={num("lead_time_days")} /></Field>
        <Field label="Status"><select className="input" value={form.active ? "1" : "0"} onChange={(e) => setForm({ ...form, active: e.target.value === "1" })}><option value="1">Active</option><option value="0">Inactive</option></select></Field>
      </div>
      <div className="mt-6">
        <div className="label mb-2">Specification</div>
        <div className="flex flex-wrap gap-1.5">{Object.entries(product.specs).map(([k, v]) => <Badge key={k}>{titleCase(k)}: {String(v)}</Badge>)}</div>
      </div>
      {save.isError && <div className="mt-4 text-[12.5px] text-rose-700">{(save.error as Error).message}</div>}
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
