import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, Field, Segmented } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api } from "../../lib/api";
import type { RfpDetail } from "../../lib/types";
import { date, money } from "../../lib/format";

export function QuotationTab({ rfp, editable }: { rfp: RfpDetail; editable: boolean }) {
  const [view, setView] = useState<"summary" | "pdf">("summary");
  const loc = rfp.pricing?.localisation;
  const prop = rfp.proposal;
  if (!loc || !prop) return null;
  const m = (v: number) => money(v, loc.currency, { decimals: loc.decimals });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <Segmented value={view} onChange={setView} items={[{ value: "summary", label: "Quotation content" }, { value: "pdf", label: "PDF preview" }]} />
        <div className="text-[12px] text-muted">{prop.quote_number} · version {prop.version} · valid until {date(prop.valid_until)}</div>
      </div>

      {view === "pdf" ? (
        <div className="card overflow-hidden">
          <iframe key={`${prop.version}-${rfp.status}`} title="Quotation PDF" src={`${api.documentUrl(rfp.id, "quotation")}#view=FitH`} className="h-[82vh] w-full bg-[#f3f4f6]" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-5">
            <Card title="Commercial schedule" subtitle={`In ${loc.currency} · ${loc.tax_summary}`} bodyClassName="p-0">
              <table className="table-base">
                <thead><tr><th className="w-10">#</th><th>Item</th><th className="!text-right">Qty</th><th className="!text-right">Unit price</th><th className="!text-right">Net</th><th>Tax</th><th className="!text-right">Total</th></tr></thead>
                <tbody>
                  {loc.lines.map((l) => (
                    <tr key={l.line_no}>
                      <td className="text-muted tnum">{l.line_no}</td>
                      <td className="max-w-[320px]"><div className="font-medium">{l.name}</div>
                        {l.bundle_name && <div className="text-[11.5px] text-[#8a5a0b]">Includes {l.bundle_name.toLowerCase()} at no charge</div>}</td>
                      <td className="text-right tnum">{l.quantity.toLocaleString()}</td>
                      <td className="text-right tnum">{m(l.unit_price)}</td>
                      <td className="text-right tnum">{m(l.net)}</td>
                      <td className="whitespace-nowrap"><span className="tnum">{l.tax_rate_pct}%</span><div className="text-[11px] text-muted">{l.tax_regime}</div></td>
                      <td className="text-right tnum font-medium">{m(l.gross)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex justify-end border-t border-line bg-[#fafbfc] px-5 py-4">
                <dl className="w-[320px] space-y-1.5 text-[13px]">
                  <div className="flex justify-between"><dt className="text-muted">Subtotal</dt><dd className="tnum">{m(loc.subtotal)}</dd></div>
                  {loc.tax_breakdown.map((t) => <div key={t.name + t.rate_pct} className="flex justify-between"><dt className="text-muted">{t.name} @ {t.rate_pct}%</dt><dd className="tnum">{m(t.amount)}</dd></div>)}
                  <div className="flex justify-between border-t border-line pt-2 text-[15px] font-semibold"><dt>Total</dt><dd className="tnum">{m(loc.grand_total)}</dd></div>
                </dl>
              </div>
            </Card>

            <Card title="Cover letter">
              <div className="max-w-[680px] space-y-3 text-[13px] leading-[1.65] text-ink-soft">
                <p>{prop.salutation}</p>
                {prop.cover_letter.map((p, i) => <p key={i}>{p}</p>)}
                <p className="pt-1">Yours sincerely,<br /><span className="font-medium text-ink">{prop.signatory.name}</span><br />{prop.signatory.title}</p>
              </div>
            </Card>

            <Card title="Delivery plan">
              <ol className="relative ml-2 space-y-4 border-l border-line pl-5">
                {prop.milestones.map((ms) => (
                  <li key={ms.label} className="relative">
                    <span className="absolute -left-[26px] top-1 size-2.5 rounded-full border-2 border-white bg-ink ring-1 ring-line" />
                    <div className="flex items-baseline gap-2"><span className="font-medium">{ms.label}</span><span className="text-[12px] text-muted tnum">Day {ms.day}</span></div>
                    <div className="text-[12.5px] text-muted">{ms.detail}</div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>

          <div className="space-y-5">
            <CurrencyCard rfp={rfp} editable={editable} />
            <Card title="Included at no charge" subtitle={prop.inclusions.length ? `Worth ${m(loc.bundled_value)} to the client` : undefined}>
              {prop.inclusions.length === 0 ? <div className="text-[12.5px] text-muted">No value-added services included.</div> : (
                <ul className="space-y-3">
                  {prop.inclusions.map((inc) => (
                    <li key={inc.line_no} className="text-[12.5px]"><div className="flex justify-between gap-2"><span className="font-medium">{inc.service}</span><span className="tnum text-muted">{m(inc.value)}</span></div>
                      <div className="text-muted">{inc.item} × {inc.quantity.toLocaleString()}</div></li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Grounding sources" subtitle="Knowledge-base passages cited in the proposal">
              <ul className="space-y-2">
                {Array.from(new Map(prop.retrieval_log.flatMap((r) => r.passages.map((p) => [p.section, p]))).values()).slice(0, 10).map((p) => (
                  <li key={p.section} className="flex items-center justify-between gap-2 text-[12.5px]"><span className="truncate">{p.section}</span><Badge>{p.source.replace(/^\d+_|\.md$/g, "").replace(/_/g, " ")}</Badge></li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function CurrencyCard({ rfp, editable }: { rfp: RfpDetail; editable: boolean }) {
  const loc = rfp.pricing!.localisation!;
  const qc = useQueryClient();
  const { user } = useAuth();
  const [ccy, setCcy] = useState(loc.currency);
  const [buffer, setBuffer] = useState(String(loc.fx_buffer_pct));
  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries, enabled: editable });
  const currencies = Array.from(new Set(["INR", "USD", "EUR", "GBP", "AED", ...(countries.data ?? []).map((c) => c.currency)])).sort();
  const apply = useMutation({
    mutationFn: () => api.reprice(rfp.id, { currency: ccy, fx_buffer_pct: Number(buffer), actor: user?.name, note: `Currency set to ${ccy}` }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rfp", rfp.id] }),
  });
  return (
    <Card title="Currency and tax">
      <dl className="space-y-2 text-[12.5px]">
        <div className="flex justify-between"><dt className="text-muted">Rate</dt><dd className="tnum">1 {loc.currency} = {(1 / loc.fx_effective_rate).toFixed(4)} {loc.base_currency}</dd></div>
        <div className="flex justify-between"><dt className="text-muted">Source</dt><dd className="text-right">{loc.fx_source}{loc.fx_stale && <Badge tone="amber" className="ml-1.5">Fallback</Badge>}</dd></div>
        <div className="flex justify-between"><dt className="text-muted">Buffer</dt><dd className="tnum">{loc.fx_buffer_pct}%</dd></div>
        <div className="flex justify-between"><dt className="text-muted">Jurisdiction</dt><dd className="text-right">{loc.jurisdiction}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-muted">Treatment</dt><dd className="text-right">{loc.tax_summary}</dd></div>
      </dl>
      {loc.tax_notes.length > 0 && <ul className="mt-3 space-y-1 border-t border-line pt-3 text-[12px] text-muted">{loc.tax_notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      {editable && (
        <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4">
          <Field label="Quote currency"><select className="input" value={ccy} onChange={(e) => setCcy(e.target.value)}>{currencies.map((c) => <option key={c}>{c}</option>)}</select></Field>
          <Field label="FX buffer %"><input className="input tnum" type="number" min={0} max={10} step={0.5} value={buffer} onChange={(e) => setBuffer(e.target.value)} /></Field>
          <Button className="col-span-2" disabled={ccy === loc.currency && Number(buffer) === loc.fx_buffer_pct} loading={apply.isPending} onClick={() => apply.mutate()}>Update currency</Button>
        </div>
      )}
    </Card>
  );
}
