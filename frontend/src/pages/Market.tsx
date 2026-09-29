import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Page, PageHeader } from "../components/layout/Shell";
import { Badge, Card, Field, Meter } from "../components/ui";
import { api } from "../lib/api";
import { money } from "../lib/format";

export default function Market() {
  const competitors = useQuery({ queryKey: ["competitors"], queryFn: api.competitors });
  const products = useQuery({ queryKey: ["products", "", ""], queryFn: () => api.products() });
  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries });
  const [sku, setSku] = useState("MSS-LT-101");
  const [country, setCountry] = useState("IN");
  const [qty, setQty] = useState(25);
  const offers = useQuery({ queryKey: ["offers", sku, country, qty], queryFn: () => api.marketOffers(sku, country, qty), enabled: !!sku });
  const o = offers.data;
  const chart = (o?.offers ?? []).map((x) => ({ name: x.competitor, price: Math.round(x.unit_price_base), below: x.unit_price_base < (o?.product.unit_cost ?? 0) }));

  return (
    <>
      <PageHeader title="Market" description="Competitor price intelligence, queried live from the market data service and normalised to rupees." />
      <Page className="space-y-6">
        <Card title="Price check" subtitle="What competitors are offering for one of our products, for a given market and quantity">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_200px_120px]">
            <Field label="Product"><select className="input" value={sku} onChange={(e) => setSku(e.target.value)}>
              {products.data?.map((p) => <option key={p.sku} value={p.sku}>{p.name}</option>)}</select></Field>
            <Field label="Client market"><select className="input" value={country} onChange={(e) => setCountry(e.target.value)}>
              {countries.data?.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></Field>
            <Field label="Quantity"><input className="input tnum" type="number" min={1} value={qty} onChange={(e) => setQty(Math.max(1, Number(e.target.value)))} /></Field>
          </div>
          {o && (
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
              <div className="overflow-hidden rounded-xl border border-line">
                <table className="table-base">
                  <thead><tr><th>Competitor</th><th className="!text-right">Quoted</th><th className="!text-right">In INR</th><th className="!text-right">vs our cost</th><th className="!text-right">Warranty</th><th className="!text-right">Lead</th></tr></thead>
                  <tbody>
                    {o.offers.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-muted">No competitor offers this product in {country}.</td></tr>}
                    {o.offers.map((x) => (
                      <tr key={x.competitor}>
                        <td><div className="font-medium">{x.competitor}</div><div className="text-[11.5px] text-muted">{x.positioning}{x.promotion && <> · <span className="text-rose-700">{x.promotion}</span></>}</div></td>
                        <td className="text-right tnum">{money(x.unit_price, x.currency)}</td>
                        <td className="text-right tnum font-medium">{money(x.unit_price_base)}</td>
                        <td className={clsx("text-right tnum", x.vs_cost_pct < 0 ? "text-rose-700" : "text-muted")}>{x.vs_cost_pct > 0 ? "+" : ""}{x.vs_cost_pct.toFixed(1)}%</td>
                        <td className="text-right tnum">{x.warranty_months} mo</td>
                        <td className="text-right tnum">{x.lead_time_days} d</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between text-[12px] text-muted"><span>Unit price in INR</span><span>Cost {money(o.product.unit_cost)} · List {money(o.product.list_price)}</span></div>
                <div className="h-[220px]">
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
                <p className="mt-2 text-[11.5px] text-muted">Dashed line marks our landed cost. Source: {o.endpoint}, {o.latency_ms} ms.</p>
              </div>
            </div>
          )}
        </Card>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {competitors.data?.map((c) => (
            <Card key={c.id} title={c.name} subtitle={`${c.positioning} · ${c.hq}`}>
              <dl className="space-y-2.5 text-[12.5px]">
                <div className="flex justify-between"><dt className="text-muted">Pricing currency</dt><dd>{c.currency}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Standard warranty</dt><dd>{c.default_warranty_months} months</dd></div>
                <div><div className="flex justify-between"><dt className="text-muted">Delivery reliability</dt><dd className="tnum">{Math.round(c.reliability * 100)}%</dd></div><div className="mt-1.5"><Meter value={c.reliability} tone={c.reliability >= 0.85 ? "green" : c.reliability >= 0.75 ? "amber" : "red"} /></div></div>
                <div className="flex flex-wrap gap-1 pt-1">{c.serves.map((s) => <Badge key={s}>{s}</Badge>)}</div>
                {c.bundle && <div className="border-t border-line pt-2 text-muted">Typically bundles: <span className="text-ink">{c.bundle}</span></div>}
              </dl>
            </Card>
          ))}
        </div>
      </Page>
    </>
  );
}
