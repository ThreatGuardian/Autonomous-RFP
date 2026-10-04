import clsx from "clsx";
import { AlertTriangle, ChevronDown, ChevronRight, MessageSquareQuote, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { StrategyBadge, WarningList } from "../../components/domain";
import { Badge, Button, Card, Meter, Stat, StatGrid } from "../../components/ui";
import type { RfpDetail } from "../../lib/types";
import { money, pct, prob } from "../../lib/format";
import { AnimatedNumber } from "../../components/motion";
import { AwardCard } from "./AwardCard";
import { LineSheet } from "./LineSheet";
import { Workbench } from "./Workbench";

export function PricingTab({ rfp, editable }: { rfp: RfpDetail; editable: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const [bench, setBench] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const strat = rfp.pricing?.strategy;
  const costing = rfp.pricing?.costing;
  if (!strat) return null;
  const base = strat.base_currency;
  const selected = strat.lines.find((l) => l.line_no === open) ?? null;
  const warnings = [...(costing?.warnings ?? []), ...strat.warnings];

  return (
    <div className="space-y-5">
      <StatGrid cols={4}>
        <Stat label="Net revenue" value={<AnimatedNumber value={strat.revenue} format={(v) => money(v, base, { compact: true })} />} hint={`${strat.lines.length} priced lines`} />
        <Stat label="Gross margin" value={<AnimatedNumber value={strat.margin_pct} format={(v) => pct(v)} />} hint={`${money(strat.margin, base, { compact: true })}${strat.bundle_cost ? ` after ${money(strat.bundle_cost, base, { compact: true })} of services` : ""}`} />
        <Stat label="Win probability" value={<AnimatedNumber value={strat.win_probability * 100} format={(v) => `${Math.round(v)}%`} />} hint={`${strat.below_cost_competitors} line(s) with below-cost rivals`} />
        <Stat label="Expected profit" value={<AnimatedNumber value={strat.expected_profit} format={(v) => money(v, base, { compact: true })} />} hint="Margin × win probability" />
      </StatGrid>

      {strat.agent_summary && (
        <div className="flex gap-3 rounded-2xl border border-line bg-white px-5 py-4 shadow-[var(--shadow-card)]">
          <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-accent" />
          <div>
            <div className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted">Pricing analyst's assessment</div>
            <p className="mt-1 text-[13px] leading-[1.6] text-ink-soft">{strat.agent_summary}</p>
          </div>
        </div>
      )}

      {strat.award && <AwardCard rfpId={rfp.id} award={strat.award} currency={base} editable={editable} />}

      {warnings.length > 0 && (
        <div>
          <button onClick={() => setShowNotes(!showNotes)} className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-[#fffaf0] px-3 py-1 text-[12px] font-medium text-[#7a4a00] transition hover:bg-[#fff4df]">
            <AlertTriangle className="size-3.5" /> {warnings.length} notice{warnings.length > 1 ? "s" : ""} on stock, warranty and matching
            <ChevronDown className={clsx("size-3.5 transition-transform", showNotes && "rotate-180")} />
          </button>
          {showNotes && <div className="mt-2 animate-rise"><WarningList items={warnings} /></div>}
        </div>
      )}

      <Card title="Line pricing" subtitle={strat.summary} bodyClassName="p-0"
        actions={editable && <Button variant="primary" icon={<SlidersHorizontal className="size-4" />} onClick={() => setBench(true)}>Adjust quotation</Button>}>
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
                      <div className="font-mono text-[11.5px] text-muted">{l.sku}</div>
                      {l.bundle && <div className="truncate text-[11.5px] text-[#8a5a0b]">+ {l.bundle.name}</div>}
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

      {bench && <Workbench key={`${rfp.proposal?.version}-${rfp.updated_at}`} rfp={rfp} open onClose={() => setBench(false)} />}

      <LineSheet rfpId={rfp.id} line={selected} currency={base} editable={editable}
        costed={costing?.lines.find((c) => c.line_no === open)}
        requested={rfp.parsed?.line_items.find((i) => i.line_no === open)}
        onClose={() => setOpen(null)} />
    </div>
  );
}
