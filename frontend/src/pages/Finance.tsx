import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { Page, PageHeader } from "../components/layout/Shell";
import { Badge, Button, Card, Field } from "../components/ui";
import { api } from "../lib/api";
import { date, titleCase } from "../lib/format";

const MAJOR = ["USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD", "JPY", "SAR", "CHF", "QAR", "ZAR"];
const INCOTERMS = ["DDP", "DAP", "CIF", "FOB", "EXW", "FCA"];

export default function Finance() {
  const qc = useQueryClient();
  const fx = useQuery({ queryKey: ["fx"], queryFn: api.fx });
  const refresh = useMutation({ mutationFn: api.fxRefresh, onSuccess: (d) => qc.setQueryData(["fx"], d) });
  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries });
  const [country, setCountry] = useState("DE");
  const [region, setRegion] = useState("");
  const [taxId, setTaxId] = useState("");
  const [incoterm, setIncoterm] = useState("DDP");
  const preview = useQuery({
    queryKey: ["tax-preview", country, region, taxId, incoterm],
    queryFn: () => api.taxPreview({ country, region: region || undefined, tax_id: taxId || undefined, incoterm: country === "IN" ? undefined : incoterm }),
  });
  const selected = countries.data?.find((c) => c.code === country);

  return (
    <>
      <PageHeader title="Tax & currency" description="Exchange rates and indirect-tax rules applied when quoting domestic and international clients." />
      <Page className="grid grid-cols-1 gap-6 xl:grid-cols-[420px_1fr]">
        <Card title="Exchange rates" subtitle={fx.data ? <>Source: {fx.data.source} · as of {fx.data.as_of.length > 10 ? date(fx.data.as_of, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : date(fx.data.as_of)}</> : undefined}
          actions={<Button size="sm" icon={<RefreshCw className="size-3.5" />} loading={refresh.isPending} onClick={() => refresh.mutate()}>Refresh</Button>} bodyClassName="p-0">
          {fx.data?.stale && <div className="border-b border-amber-200 bg-amber-50 px-5 py-2.5 text-[12px] text-amber-900">Live providers are unreachable; using the most recent available rates. Confirm before sending international quotations.</div>}
          <table className="table-base">
            <thead><tr><th>Currency</th><th className="!text-right">1 unit in INR</th><th className="!text-right">Per ₹1,00,000</th></tr></thead>
            <tbody>
              {MAJOR.filter((c) => fx.data?.rates[c]).map((c) => {
                const r = fx.data!.rates[c];
                return (
                  <tr key={c}><td className="font-medium">{c}</td><td className="text-right tnum">₹{(1 / r).toFixed(r > 1 ? 4 : 2)}</td><td className="text-right tnum text-muted">{(r * 100000).toLocaleString("en-US", { maximumFractionDigits: 2 })}</td></tr>
                );
              })}
            </tbody>
          </table>
          <div className="border-t border-line px-5 py-3 text-[12px] text-muted">A 1.5% buffer is added to non-rupee quotations by default; it can be changed per quotation.</div>
        </Card>

        <div className="space-y-6">
          <Card title="Tax treatment preview" subtitle="How a quotation to a given jurisdiction will be taxed, by product tax category">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Field label="Client country"><select className="input" value={country} onChange={(e) => { setCountry(e.target.value); setRegion(""); }}>
                {countries.data?.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></Field>
              <Field label="State / province"><select className="input" value={region} onChange={(e) => setRegion(e.target.value)} disabled={!selected?.regions.length}>
                <option value="">{selected?.regions.length ? "Not specified" : "Not applicable"}</option>{selected?.regions.map((r) => <option key={r}>{r}</option>)}</select></Field>
              <Field label="Client tax ID"><input className="input" placeholder="Optional" value={taxId} onChange={(e) => setTaxId(e.target.value)} /></Field>
              <Field label="Delivery terms"><select className="input" value={incoterm} onChange={(e) => setIncoterm(e.target.value)} disabled={country === "IN"}>
                {INCOTERMS.map((i) => <option key={i}>{i}</option>)}</select></Field>
            </div>
            {preview.data && (
              <div className="mt-5 rounded-xl border border-line">
                <div className="flex items-center justify-between border-b border-line px-4 py-3">
                  <div><div className="font-medium">{preview.data.summary}</div><div className="text-[12px] text-muted">{preview.data.jurisdiction}</div></div>
                </div>
                <table className="table-base">
                  <thead><tr><th>Tax category</th><th>Treatment</th><th>Components</th><th className="!text-right">Rate</th></tr></thead>
                  <tbody>
                    {Object.entries(preview.data.treatments).map(([cat, t]) => (
                      <tr key={cat}>
                        <td className="font-medium">{titleCase(cat.replace("goods_standard", "goods"))}</td>
                        <td>{t.regime}{t.note && <div className="text-[11.5px] text-muted">{t.note}</div>}</td>
                        <td><div className="flex flex-wrap gap-1">{t.components.map((c) => <Badge key={c.name}>{c.name} {c.rate_pct}%</Badge>)}</div></td>
                        <td className="text-right font-semibold tnum">{t.rate_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.data.notes.length > 0 && <ul className="space-y-1 border-t border-line px-4 py-3 text-[12px] text-muted">{preview.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
              </div>
            )}
          </Card>
          <Card title="Rules in force">
            <ul className="grid grid-cols-1 gap-3 text-[12.5px] text-ink-soft md:grid-cols-2">
              <li><span className="font-medium text-ink">Within India.</span> CGST + SGST when delivered inside Maharashtra; IGST for every other state.</li>
              <li><span className="font-medium text-ink">Exports (EXW to DAP).</span> Zero-rated under Letter of Undertaking; the importer settles destination taxes.</li>
              <li><span className="font-medium text-ink">Exports (DDP).</span> Destination VAT, GST or sales tax is charged, with state and category brackets.</li>
              <li><span className="font-medium text-ink">Cross-border B2B services.</span> Licences and services are reverse-charged when the client provides a tax registration.</li>
            </ul>
          </Card>
        </div>
      </Page>
    </>
  );
}
