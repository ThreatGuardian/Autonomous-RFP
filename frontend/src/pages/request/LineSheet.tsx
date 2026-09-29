import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check, Info } from "lucide-react";
import { useEffect, useState } from "react";
import { StrategyBadge } from "../../components/domain";
import { Badge, Button, Field, Sheet } from "../../components/ui";
import { api, type LineOverride } from "../../lib/api";
import type { CostedLine, PricedLine, RequestedItem } from "../../lib/types";
import { money, pct, prob } from "../../lib/format";
import { PricePosition, WinCurve } from "./charts";

export function LineSheet({ rfpId, line, costed, requested, currency, editable, onClose }: {
  rfpId: number; line: PricedLine | null; costed?: CostedLine; requested?: RequestedItem; currency: string; editable: boolean; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [price, setPrice] = useState("");
  const [bundle, setBundle] = useState<string>("");
  const [sku, setSku] = useState<string>("");
  const [exclude, setExclude] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!line) return;
    setPrice(String(line.unit_price));
    setBundle(line.bundle?.code ?? "");
    setSku(line.sku);
    setExclude(false);
    setNote("");
  }, [line]);

  const apply = useMutation({
    mutationFn: () => {
      const ov: LineOverride = {};
      if (exclude) ov.exclude = true;
      if (sku && line && sku !== line.sku) ov.sku = sku;
      const p = Number(price);
      if (line && p && Math.abs(p - line.unit_price) > 0.005) ov.unit_price = p;
      if (line && bundle !== (line.bundle?.code ?? "")) {
        if (bundle) ov.bundle = bundle;
        else ov.clear_bundle = true;
        if (!ov.unit_price) ov.unit_price = p || line.unit_price;
      }
      return api.reprice(rfpId, { lines: { [String(line!.line_no)]: ov }, note: note || undefined, actor: "Priya Shah" });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rfp", rfpId] });
      qc.invalidateQueries({ queryKey: ["rfps"] });
      onClose();
    },
  });

  if (!line) return <Sheet open={false} onClose={onClose} title="">{null}</Sheet>;
  const p = Number(price) || line.unit_price;
  const chosenBundle = costed?.value_adds.find((v) => v.code === bundle);
  const marginUnit = p - line.unit_cost - (chosenBundle?.unit_cost ?? 0);
  const previewMargin = (100 * marginUnit) / p;
  const belowFloor = p - (chosenBundle?.unit_cost ?? 0) < line.floor_price - 0.01;
  const dirty = exclude || sku !== line.sku || Math.abs(p - line.unit_price) > 0.005 || bundle !== (line.bundle?.code ?? "");

  return (
    <Sheet open onClose={onClose} width={760}
      title={<span className="flex items-center gap-2">Line {line.line_no} · {line.name}</span>}
      subtitle={<span>{line.sku} · {line.quantity.toLocaleString()} {line.unit}{line.quantity === 1 ? "" : "s"}{requested ? ` · requested as “${requested.description}”` : ""}</span>}
      footer={editable ? (
        <div className="flex items-center justify-between gap-3">
          <div className="text-[12px] text-muted">Changes re-run costing, strategy, tax and drafting for this request.</div>
          <div className="flex gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={!dirty} loading={apply.isPending} onClick={() => apply.mutate()}>Apply and re-price</Button>
          </div>
        </div>
      ) : undefined}
    >
      <div className="space-y-6">
        <div className="rounded-xl border border-line bg-[#fafbfc] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2"><StrategyBadge strategy={line.strategy} />{line.flags.map((f) => <Badge key={f} tone="red">{f}</Badge>)}</div>
          <div className="mt-2 text-[14px] font-semibold text-ink">{line.headline}</div>
          <div className="mt-3 grid grid-cols-4 gap-4 border-t border-line pt-3">
            {[["Unit price", money(line.unit_price, currency)], ["Margin", pct(line.margin_pct)], ["Win probability", prob(line.win_probability)], ["Expected profit", money(line.expected_profit, currency)]].map(([k, v]) => (
              <div key={k}><div className="label">{k}</div><div className="mt-1 text-[15px] font-semibold tnum">{v}</div></div>
            ))}
          </div>
        </div>

        <section>
          <h4 className="mb-2 text-[13px] font-semibold">Pricing rationale</h4>
          <ol className="space-y-2">
            {line.rationale.map((r, i) => (
              <li key={i} className="flex gap-3 text-[12.5px] leading-[1.55] text-ink-soft">
                <span className="mt-[3px] grid size-4 shrink-0 place-items-center rounded-full bg-[#eef0f3] text-[10px] font-semibold text-muted">{i + 1}</span>{r}
              </li>
            ))}
          </ol>
        </section>

        {line.market.count > 0 && (
          <section>
            <h4 className="mb-1 text-[13px] font-semibold">Price position</h4>
            <p className="mb-3 text-[12px] text-muted">Shaded band is the policy-compliant range. Red markers are competitors below our landed cost.</p>
            <PricePosition line={line} currency={currency} />
          </section>
        )}

        <section>
          <h4 className="mb-1 text-[13px] font-semibold">Win probability and expected profit</h4>
          <p className="mb-2 text-[12px] text-muted">Modelled across the permitted price range{line.bundle ? `, with ${line.bundle.name.toLowerCase()} included` : ""}.</p>
          <WinCurve line={line} currency={currency} />
        </section>

        {line.scenarios.length > 0 && (
          <section>
            <h4 className="mb-2 text-[13px] font-semibold">Alternatives considered</h4>
            <div className="overflow-hidden rounded-xl border border-line">
              <table className="table-base">
                <thead><tr><th>Scenario</th><th className="!text-right">Unit price</th><th>Bundle</th><th className="!text-right">Margin</th><th className="!text-right">Win</th><th className="!text-right">Expected profit</th></tr></thead>
                <tbody>
                  {line.scenarios.map((s) => (
                    <tr key={s.label} className={clsx(s.label === "Recommended" && "bg-[#fafbfc]")}>
                      <td><div className="font-medium">{s.label}</div>{(!s.feasible || s.note) && <div className="text-[11.5px] text-rose-700">{s.note ?? "Outside pricing policy"}</div>}</td>
                      <td className="text-right tnum">{money(s.unit_price, currency)}</td>
                      <td className="text-muted">{s.bundle ?? "—"}</td>
                      <td className={clsx("text-right tnum", s.margin_pct < 0 && "text-rose-700")}>{pct(s.margin_pct)}</td>
                      <td className="text-right tnum">{prob(s.win_probability)}</td>
                      <td className={clsx("text-right tnum", s.expected_profit < 0 && "text-rose-700")}>{money(s.expected_profit, currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section>
          <h4 className="mb-2 text-[13px] font-semibold">Market offers <span className="font-normal text-muted">({line.market.count})</span></h4>
          {line.market.count === 0 ? <div className="rounded-xl border border-line px-4 py-3 text-[12.5px] text-muted">No competitor carries this product in the client's market.</div> : (
            <div className="overflow-hidden rounded-xl border border-line">
              <table className="table-base">
                <thead><tr><th>Competitor</th><th className="!text-right">Quoted</th><th className="!text-right">In {currency}</th><th className="!text-right">vs our cost</th><th className="!text-right">Warranty</th><th className="!text-right">Lead time</th></tr></thead>
                <tbody>
                  {line.market.offers.map((o) => {
                    const vs = 100 * (o.unit_price_base / line.unit_cost - 1);
                    return (
                      <tr key={o.competitor_id}>
                        <td><div className="font-medium">{o.competitor}</div><div className="text-[11.5px] text-muted">{o.positioning}{o.promotion ? ` · ${o.promotion}` : ""}{o.in_stock ? "" : " · out of stock"}</div></td>
                        <td className="text-right tnum">{money(o.unit_price, o.currency)}</td>
                        <td className="text-right tnum font-medium">{money(o.unit_price_base, currency)}</td>
                        <td className={clsx("text-right tnum", vs < 0 ? "text-rose-700" : "text-muted")}>{vs >= 0 ? "+" : ""}{vs.toFixed(1)}%</td>
                        <td className="text-right tnum">{o.warranty_months} mo</td>
                        <td className="text-right tnum">{o.lead_time_days} d</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="grid grid-cols-2 gap-4 rounded-xl border border-line p-4 text-[12.5px]">
          {[
            ["Landed cost", money(line.unit_cost, currency)], ["Margin floor", money(line.floor_price, currency)],
            ["List price", money(line.list_price, currency)], ["Standard (after volume tier)", money(line.standard_price, currency)],
            ["Stock", costed ? `${costed.stock_qty.toLocaleString()} available${costed.stock_ok ? "" : " — backorder"}` : "—"],
            ["Lead time / warranty", `${line.lead_time_days} days · ${line.warranty_months} months`],
          ].map(([k, v]) => <div key={k} className="flex justify-between gap-3"><span className="text-muted">{k}</span><span className="tnum font-medium text-ink">{v}</span></div>)}
        </section>

        {editable && (
          <section className="rounded-xl border border-line p-4">
            <h4 className="text-[13px] font-semibold">Adjust this line</h4>
            <p className="mb-4 mt-0.5 text-[12px] text-muted">Overrides are recorded in the activity log and flagged in the pricing memo.</p>
            <div className="grid grid-cols-2 gap-4">
              <Field label={`Unit price (${currency})`} hint={<span className={clsx(belowFloor && "text-rose-700")}>Margin {previewMargin.toFixed(1)}%{belowFloor ? " — below the minimum-margin floor" : ""}</span>}>
                <input className="input tnum" type="number" min={0} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} disabled={exclude} />
              </Field>
              <Field label="Included service" hint={chosenBundle ? `Costs ${money(chosenBundle.unit_cost, currency)} per unit · worth ${money(chosenBundle.unit_value, currency)}` : "No value-added service included"}>
                <select className="input" value={bundle} onChange={(e) => setBundle(e.target.value)} disabled={exclude}>
                  <option value="">None</option>
                  {costed?.value_adds.map((v) => <option key={v.code} value={v.code}>{v.name}</option>)}
                </select>
              </Field>
              {requested && requested.candidates.length > 1 && (
                <Field label="Catalogue match" hint="Changing the product re-costs the line.">
                  <select className="input" value={sku} onChange={(e) => setSku(e.target.value)} disabled={exclude}>
                    {requested.candidates.map((c) => <option key={c.sku} value={c.sku}>{c.name} ({Math.round(c.score * 100)}%)</option>)}
                  </select>
                </Field>
              )}
              <Field label="Note for the record">
                <input className="input" placeholder="Optional" value={note} onChange={(e) => setNote(e.target.value)} />
              </Field>
            </div>
            <label className="mt-4 flex items-center gap-2 text-[12.5px]">
              <input type="checkbox" checked={exclude} onChange={(e) => setExclude(e.target.checked)} className="size-4 accent-[#0b1220]" /> Exclude this line from the quotation
            </label>
            {apply.isError && <div className="mt-3 flex items-center gap-2 text-[12.5px] text-rose-700"><AlertTriangle className="size-4" />{(apply.error as Error).message}</div>}
          </section>
        )}
        {!editable && (
          <div className="flex items-center gap-2 rounded-xl border border-line bg-[#fafbfc] px-4 py-3 text-[12.5px] text-muted">
            {line.overridden ? <Check className="size-4" /> : <Info className="size-4" />} Reopen the request to change pricing.
          </div>
        )}
      </div>
    </Sheet>
  );
}
