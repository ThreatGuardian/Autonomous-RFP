import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { StrategyBadge, WarningList } from "../../components/domain";
import { Badge, Card, Meter, Stat, StatGrid } from "../../components/ui";
import type { RfpDetail } from "../../lib/types";
import { money, pct, prob } from "../../lib/format";
import { LineSheet } from "./LineSheet";

export function PricingTab({ rfp, editable }: { rfp: RfpDetail; editable: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const strat = rfp.pricing?.strategy;
  const costing = rfp.pricing?.costing;
  if (!strat) return null;
  const base = strat.base_currency;
  const selected = strat.lines.find((l) => l.line_no === open) ?? null;
  const warnings = [...(costing?.warnings ?? []), ...strat.warnings];

  return (
    <div className="space-y-5">
      <StatGrid cols={6}>
        <Stat label="Net revenue" value={money(strat.revenue, base, { compact: true })} hint={`${strat.lines.length} priced lines`} />
        <Stat label="Gross margin" value={pct(strat.margin_pct)} hint={money(strat.margin, base, { compact: true })} />
        <Stat label="Bundled services" value={money(strat.bundle_cost, base, { compact: true })} hint="Our cost of inclusions" />
        <Stat label="Expected profit" value={money(strat.expected_profit, base, { compact: true })} hint="Margin × win probability" />
        <Stat label="Win probability" value={prob(strat.win_probability)} hint="Revenue-weighted" />
        <Stat label="Below-cost rivals" value={strat.below_cost_competitors} hint="Lines where matching loses money" />
      </StatGrid>

      <div className="rounded-xl border border-line bg-white px-5 py-3.5 text-[13px] leading-[1.6] text-ink-soft">
        <span className="font-medium text-ink">Summary. </span>{strat.summary}
        {strat.market_endpoint && <span className="text-muted"> Market data from {strat.market_endpoint} in {strat.market_latency_ms} ms.</span>}
      </div>
      <WarningList items={warnings} />

      <Card title="Line pricing" subtitle={`Amounts in ${base} (base currency). Select a line for the full rationale and to adjust it.`} bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th className="w-10">#</th><th>Product</th><th className="!text-right">Qty</th><th className="!text-right">Landed cost</th>
                <th className="!text-right">Best competitor</th><th className="!text-right">Our price</th><th className="!text-right">Margin</th>
                <th className="w-[120px]">Win probability</th><th>Strategy</th><th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {strat.lines.map((l) => {
                const best = l.market.best;
                const belowCost = best && best.unit_price_base < l.unit_cost;
                return (
                  <tr key={l.line_no} onClick={() => setOpen(l.line_no)} className="group cursor-pointer hover:bg-[#fafbfc]">
                    <td className="text-muted tnum">{l.line_no}</td>
                    <td className="max-w-[300px]">
                      <div className="truncate font-medium">{l.name}</div>
                      <div className="flex items-center gap-1.5 text-[11.5px] text-muted">
                        <span className="font-mono">{l.sku}</span>
                        {l.bundle && <span className="truncate text-[#8a5a0b]">· + {l.bundle.name}</span>}
                      </div>
                    </td>
                    <td className="text-right tnum">{l.quantity.toLocaleString()}</td>
                    <td className="text-right tnum text-muted">{money(l.unit_cost, base)}</td>
                    <td className="text-right">
                      {best ? (
                        <>
                          <div className={clsx("tnum", belowCost && "text-rose-700")}>{money(best.unit_price_base, base)}</div>
                          <div className="truncate text-[11.5px] text-muted">{best.competitor}</div>
                        </>
                      ) : <span className="text-muted">No offers</span>}
                    </td>
                    <td className="text-right"><div className="tnum font-semibold">{money(l.unit_price, base)}</div>
                      <div className="text-[11.5px] text-muted tnum">{l.discount_pct > 0.05 ? `${l.discount_pct.toFixed(1)}% off list` : "List price"}</div></td>
                    <td className={clsx("text-right tnum", l.margin_pct < 0 && "text-rose-700")}>{pct(l.margin_pct)}</td>
                    <td>
                      <div className="flex items-center gap-2"><Meter value={l.win_probability} tone={l.win_probability >= 0.5 ? "green" : l.win_probability >= 0.25 ? "amber" : "red"} />
                        <span className="w-8 text-right tnum text-[12px]">{prob(l.win_probability)}</span></div>
                    </td>
                    <td>
                      <div className="flex flex-wrap items-center gap-1"><StrategyBadge strategy={l.strategy} />{l.flags.length > 0 && <Badge tone="red">{l.flags.length} flag{l.flags.length > 1 ? "s" : ""}</Badge>}</div>
                    </td>
                    <td className="text-subtle group-hover:text-ink"><ChevronRight className="size-4" /></td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="bg-[#fafbfc] font-medium">
                <td /><td className="px-3 py-3">Total</td><td /><td className="px-3 py-3 text-right tnum text-muted">{money(strat.cost, base)}</td><td />
                <td className="px-3 py-3 text-right tnum">{money(strat.revenue, base)}</td><td className="px-3 py-3 text-right tnum">{pct(strat.margin_pct)}</td>
                <td className="px-3 py-3 tnum">{prob(strat.win_probability)}</td><td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
        {!!costing?.excluded.length && (
          <div className="border-t border-line px-5 py-3 text-[12.5px] text-muted">
            <span className="font-medium text-ink">Not quoted: </span>
            {costing.excluded.map((e) => `line ${e.line_no} “${e.description}” (${e.reason.toLowerCase()})`).join("; ")}.
          </div>
        )}
      </Card>

      <LineSheet rfpId={rfp.id} line={selected} currency={base} editable={editable}
        costed={costing?.lines.find((c) => c.line_no === open)}
        requested={rfp.parsed?.line_items.find((i) => i.line_no === open)}
        onClose={() => setOpen(null)} />
    </div>
  );
}
