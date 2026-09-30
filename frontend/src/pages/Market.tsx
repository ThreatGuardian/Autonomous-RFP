import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Award, FileSpreadsheet, Globe2, Radio, Trash2, Upload } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Page, PageHeader } from "../components/layout/Shell";
import { Button, Card, Field, Meter, Segmented, Sheet } from "../components/ui";
import { api } from "../lib/api";
import { date, money } from "../lib/format";

const ADAPTER_ICON = { feed: Radio, quotes: FileSpreadsheet, awards: Award, web: Globe2 } as const;
const ADAPTER_HINT: Record<string, string> = {
  feed: "Live price feed, queried for every bid",
  quotes: "Quotes your sales team collected",
  awards: "Public results — who won, at what price",
  web: "Prices read from saved product pages",
};

export default function Market() {
  const competitors = useQuery({ queryKey: ["competitors"], queryFn: api.competitors });
  const products = useQuery({ queryKey: ["products", "", ""], queryFn: () => api.products() });
  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries });
  const [sku, setSku] = useState("");
  const [country, setCountry] = useState("IN");
  const [qty, setQty] = useState(50);
  useEffect(() => {
    if (!sku && products.data?.length) setSku(products.data.find((p) => p.category !== "service")?.sku ?? products.data[0].sku);
  }, [products.data, sku]);
  const offers = useQuery({ queryKey: ["offers", sku, country, qty], queryFn: () => api.marketOffers(sku, country, qty), enabled: !!sku });
  const o = offers.data;
  const chart = (o?.offers ?? []).map((x) => ({ name: x.competitor, price: Math.round(x.unit_price_base), below: x.unit_price_base < (o?.product.unit_cost ?? 0) }));

  return (
    <>
      <PageHeader title="Market" description="Competitor prices from the live feed, collected quotes, public award results and saved web pages — every figure dated and sourced." />
      <Page className="space-y-6">
        <Card title="Price check" subtitle="What competitors are offering for one of our products, for a given market and quantity">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_200px_120px]">
            <Field label="Product"><select className="input" value={sku} onChange={(e) => setSku(e.target.value)}>
              {products.data?.filter((p) => p.category !== "service").map((p) => <option key={p.sku} value={p.sku}>{p.name}</option>)}</select></Field>
            <Field label="Client market"><select className="input" value={country} onChange={(e) => setCountry(e.target.value)}>
              {countries.data?.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></Field>
            <Field label="Quantity"><input className="input tnum" type="number" min={1} value={qty} onChange={(e) => setQty(Math.max(1, Number(e.target.value)))} /></Field>
          </div>
          {o && (
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="overflow-hidden rounded-xl border border-line">
                <table className="table-base">
                  <thead><tr><th>Competitor</th><th className="!text-right">Unit price</th><th className="!text-right">vs our cost</th><th className="!text-right">Warranty</th><th>Source</th></tr></thead>
                  <tbody>
                    {o.offers.length === 0 && <tr><td colSpan={5} className="py-8 text-center text-muted">No competitor price on record for this product in {country}.</td></tr>}
                    {o.offers.map((x) => (
                      <tr key={x.competitor}>
                        <td className="max-w-[260px]">
                          <div className="font-medium">{x.competitor}</div>
                          <div className="text-[11.5px] text-muted">
                            {x.equivalent ? <>Offers its own <span className="text-ink-soft">{x.equivalent}</span></> : x.positioning}
                            {x.promotion && <> · <span className="text-rose-700">{x.promotion}</span></>}
                          </div>
                        </td>
                        <td className="text-right tnum font-medium">{money(x.unit_price_base)}{x.currency !== "INR" && <div className="text-[11px] font-normal text-muted">{money(x.unit_price, x.currency)}</div>}</td>
                        <td className={clsx("text-right tnum", x.vs_cost_pct < 0 ? "text-rose-700" : "text-muted")}>{x.vs_cost_pct > 0 ? "+" : ""}{x.vs_cost_pct.toFixed(1)}%</td>
                        <td className="text-right tnum">{x.warranty_months} mo</td>
                        <td className="max-w-[200px] text-[12px]"><div className="truncate">{x.source ?? "Market feed"}</div><div className="text-[11px] text-muted">{x.observed_on ? date(x.observed_on) : "today"}</div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between text-[12px] text-muted"><span>Unit price in INR</span><span>Cost {money(o.product.unit_cost)} · List {money(o.product.list_price)}</span></div>
                <div className="h-[240px]">
                  <ResponsiveContainer>
                    <BarChart data={chart} layout="vertical" margin={{ left: 0, right: 12 }}>
                      <XAxis type="number" dataKey="price" hide domain={[0, (max: number) => Math.max(max, o.product.unit_cost) * 1.05]} />
                      <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11, fill: "#4b5260" }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(v) => money(Number(v))} contentStyle={{ borderRadius: 8, border: "1px solid #e6e8ec", fontSize: 12 }} />
                      <ReferenceLine x={o.product.unit_cost} stroke="#be123c" strokeDasharray="3 3" />
                      <Bar dataKey="price" radius={[0, 3, 3, 0]} maxBarSize={18}>
                        {chart.map((c) => <Cell key={c.name} fill={c.below ? "#e11d48" : "#0b1220"} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-[11.5px] text-muted">Dashed line marks our landed cost. For each competitor the freshest price wins; older observations count for less.</p>
              </div>
            </div>
          )}
        </Card>

        <Intelligence />

        <div>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-[15px] font-semibold tracking-[-0.01em]">Competitors</h2>
            <span className="text-[12px] text-muted">{competitors.data?.length ?? 0} tracked</span>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {competitors.data?.map((c, i) => (
              <motion.div key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04, duration: 0.35 }}>
                <Card title={c.name} subtitle={`${c.positioning} · ${c.hq}`} className="h-full">
                  <dl className="space-y-2.5 text-[12.5px]">
                    <div className="flex justify-between gap-3"><dt className="text-muted">Sells</dt><dd className="text-right">{c.brands === "*" ? "All brands" : `${c.brands.join(", ")} only`}</dd></div>
                    <div className="flex justify-between"><dt className="text-muted">Standard warranty</dt><dd>{c.default_warranty_months} months</dd></div>
                    <div><div className="flex justify-between"><dt className="text-muted">Delivery reliability</dt><dd className="tnum">{Math.round(c.reliability * 100)}%</dd></div><div className="mt-1.5"><Meter value={c.reliability} tone={c.reliability >= 0.85 ? "green" : c.reliability >= 0.75 ? "amber" : "red"} /></div></div>
                    {c.notes && <p className="border-t border-line pt-2 leading-relaxed text-muted">{c.notes}</p>}
                    {c.bundle && <div className="text-muted">Typically bundles: <span className="text-ink">{c.bundle}</span></div>}
                  </dl>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </Page>
    </>
  );
}

function Intelligence() {
  const qc = useQueryClient();
  const sources = useQuery({ queryKey: ["market-sources"], queryFn: api.marketSources });
  const [adapter, setAdapter] = useState<"all" | "quotes" | "awards" | "web">("all");
  const obs = useQuery({ queryKey: ["observations", adapter], queryFn: () => api.observations({ adapter: adapter === "all" ? undefined : adapter, limit: 120 }) });
  const [upload, setUpload] = useState<null | "quotes" | "awards">(null);
  const [web, setWeb] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["observations"] }); qc.invalidateQueries({ queryKey: ["market-sources"] }); qc.invalidateQueries({ queryKey: ["offers"] }); };
  const send = useMutation({ mutationFn: (f: File) => api.uploadObservations(upload!, f), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteObservation(id), onSuccess: refresh });
  const stats = sources.data?.adapters ?? {};

  return (
    <Card title="Competitor intelligence" subtitle="Every source of competitor prices, merged per bid — freshest price per competitor wins"
      actions={<div className="flex gap-2">
        <Button size="sm" icon={<Upload className="size-3.5" />} onClick={() => { setUpload("quotes"); setTimeout(() => file.current?.click()); }}>Upload quotes</Button>
        <Button size="sm" icon={<Award className="size-3.5" />} onClick={() => { setUpload("awards"); setTimeout(() => file.current?.click()); }}>Upload award results</Button>
        <Button size="sm" icon={<Globe2 className="size-3.5" />} onClick={() => setWeb(true)}>Add web page</Button>
      </div>}>
      <input ref={file} type="file" className="hidden" accept=".csv,.xlsx,.xlsm"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) send.mutate(f); e.target.value = ""; }} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {(["feed", "quotes", "awards", "web"] as const).map((k, i) => {
          const s = stats[k];
          const Icon = ADAPTER_ICON[k];
          return (
            <motion.div key={k} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
              className="rounded-xl border border-line bg-[#fbfbfc] px-4 py-3">
              <div className="flex items-center gap-2 text-[12px] font-medium text-ink-soft"><Icon className="size-3.5" /> {s?.label ?? k}</div>
              <div className="mt-1.5 text-[20px] font-semibold tracking-[-0.02em] tnum">{k === "feed" ? "Live" : (s?.observations ?? 0).toLocaleString()}</div>
              <div className="text-[11.5px] text-muted">{k === "feed" ? `${s?.competitors ?? 0} competitors` : s?.latest ? `${s.competitors} sellers · latest ${date(s.latest)}` : ADAPTER_HINT[k]}</div>
            </motion.div>
          );
        })}
      </div>
      {send.data && <div className="mt-3 text-[12.5px] text-emerald-700">Added {send.data.added} observation(s){send.data.skipped ? `, skipped ${send.data.skipped}` : ""}.{send.data.issues[0] && <span className="text-amber-700"> Row {send.data.issues[0].row}: {send.data.issues[0].message}</span>}</div>}
      {send.isError && <div className="mt-3 text-[12.5px] text-rose-700">{(send.error as Error).message}</div>}
      <div className="mb-2 mt-5 flex items-center justify-between">
        <div className="label">Observations</div>
        <Segmented value={adapter} onChange={setAdapter} items={[{ value: "all", label: "All" }, { value: "quotes", label: "Quotes" }, { value: "awards", label: "Awards" }, { value: "web", label: "Web" }]} />
      </div>
      <div className="max-h-[420px] overflow-auto rounded-xl border border-line">
        <table className="table-base">
          <thead className="sticky top-0 z-10 bg-white"><tr><th>Date</th><th>Competitor</th><th>Product</th><th className="!text-right">Unit price</th><th className="!text-right">Qty</th><th>Source</th><th /></tr></thead>
          <tbody>
            {obs.data?.length === 0 && <tr><td colSpan={7} className="py-8 text-center text-muted">No observations yet.</td></tr>}
            {obs.data?.map((x) => (
              <tr key={x.id} className="group">
                <td className="whitespace-nowrap tnum text-muted">{date(x.observed_on)}</td>
                <td className="font-medium">{x.competitor}</td>
                <td className="max-w-[260px]"><div className="truncate">{x.product ?? x.mpn}</div><div className="font-mono text-[11px] text-muted">{x.mpn}</div></td>
                <td className="text-right tnum">{money(x.unit_price, x.currency)}</td>
                <td className="text-right tnum text-muted">{x.quantity}</td>
                <td className="max-w-[220px] text-[12px]"><div className="truncate">{x.source}</div>{x.reference && <div className="truncate text-[11px] text-muted">{x.reference}</div>}</td>
                <td className="w-8"><button aria-label="Delete" onClick={() => remove.mutate(x.id)} className="rounded p-1 text-subtle opacity-0 transition-opacity hover:bg-rose-50 hover:text-rose-700 group-hover:opacity-100"><Trash2 className="size-3.5" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11.5px] text-muted">Sheets are read by column name (date, seller or winner, part number or product, unit price, source). Templates: <a className="underline" href="/api/market/observations/template?adapter=quotes">quotes</a> · <a className="underline" href="/api/market/observations/template?adapter=awards">award results</a>.</p>
      {web && <WebPageSheet onClose={() => setWeb(false)} onDone={refresh} />}
    </Card>
  );
}

function WebPageSheet({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [competitor, setCompetitor] = useState("");
  const [url, setUrl] = useState("");
  const [html, setHtml] = useState("");
  const add = useMutation({ mutationFn: () => api.webObservation({ competitor, html, url: url || undefined }), onSuccess: (r) => { if (r.added) onDone(); } });
  const readFile = (f: File) => f.text().then(setHtml);
  return (
    <Sheet open onClose={onClose} width={560} title="Add a price from a saved web page"
      subtitle="Save the competitor's product page (Ctrl+S) and add it here. The price is read from the page's product markup or visible price; the system never visits the site itself."
      footer={<div className="flex justify-end gap-2"><Button onClick={onClose}>Close</Button><Button variant="primary" disabled={!competitor || html.length < 20} loading={add.isPending} onClick={() => add.mutate()}>Read price</Button></div>}>
      <div className="space-y-4">
        <Field label="Competitor"><input className="input" value={competitor} onChange={(e) => setCompetitor(e.target.value)} placeholder="e.g. Amazon Business" /></Field>
        <Field label="Page address (optional)"><input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></Field>
        <Field label="Saved page (.html)"><input type="file" accept=".html,.htm,.txt" className="text-[12.5px]" onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])} /></Field>
        {html && <div className="text-[12px] text-muted">{(html.length / 1024).toFixed(0)} KB loaded.</div>}
        {add.data && (add.data.added ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-[12.5px] text-emerald-900">
            Recorded {money(add.data.price)} for <span className="font-medium">{add.data.name}</span> (matched to {add.data.mpn}; read from {add.data.method}).
          </div>
        ) : <div className="text-[12.5px] text-amber-700">{add.data.message}</div>)}
        {add.isError && <div className="text-[12.5px] text-rose-700">{(add.error as Error).message}</div>}
      </div>
    </Sheet>
  );
}
