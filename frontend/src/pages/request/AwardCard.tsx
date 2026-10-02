import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { motion } from "motion/react";
import { Crosshair, Gavel, Trophy } from "lucide-react";
import { Button } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api } from "../../lib/api";
import type { AwardAnalysis } from "../../lib/types";
import { money } from "../../lib/format";

const RULE_LABEL = { L1: "Lowest price (L1)", QCBS: "Quality and cost (QCBS)", Weighted: "Weighted evaluation" } as const;

export function AwardCard({ rfpId, award, currency, editable }: { rfpId: number; award: AwardAnalysis; currency: string; editable: boolean }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const apply = useMutation({
    mutationFn: () => api.reprice(rfpId, {
      lines: Object.fromEntries(Object.entries(award.target_prices).map(([k, v]) => [k, { unit_price: v }])),
      actor: user?.name, note: "Applied the L1 target price from the award analysis",
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rfp", rfpId] }),
  });
  const bars = [
    ...award.competitors.map((c) => ({ name: c.name, total: c.total, us: false })),
    { name: "Our bid", total: award.our_total, us: true },
  ].sort((a, b) => a.total - b.total);
  const max = Math.max(...bars.map((b) => b.total));
  const min = Math.min(award.floor_total, ...bars.map((b) => b.total)) * 0.94;
  const frac = (v: number) => (v - min) / (max - min || 1);
  const x = (v: number) => `${100 * frac(v)}%`;
  const good = award.recommendation.startsWith("Submit");
  const Icon = award.rule === "L1" ? Gavel : award.rule === "QCBS" ? Crosshair : Trophy;

  return (
    <section className="card overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="border-b border-line px-6 py-5 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-2 text-[11.5px] font-medium uppercase tracking-[0.08em] text-muted">
            <Icon className="size-3.5" /> Award position · {RULE_LABEL[award.rule]}
          </div>
          <div className={clsx("mt-2 text-[18px] font-semibold tracking-[-0.01em]", good ? "text-emerald-800" : "text-ink")}>{award.recommendation}</div>
          <ul className="mt-2 space-y-1.5 text-[12.5px] leading-[1.55] text-ink-soft">
            {award.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
          {award.rule === "L1" && award.target_feasible && (award.rank ?? 1) > 1 && editable && (
            <Button className="mt-4" variant="primary" loading={apply.isPending} onClick={() => apply.mutate()}>
              Apply L1 prices · {money(award.target_total, currency, { compact: true })}
            </Button>
          )}
        </div>
        <div className="px-6 py-5">
          <div className="flex items-baseline justify-between">
            <div className="text-[12px] font-medium text-ink">Estimated whole-bid totals</div>
            {award.rank && <div className="text-[12px] text-muted">We rank <span className="font-semibold text-ink">{award.rule === "L1" ? `L${award.rank}` : `#${award.rank} on price`}</span></div>}
          </div>
          <div className="relative mt-4 space-y-2.5">
            <div className="pointer-events-none absolute inset-y-0 z-10 border-l border-dashed border-rose-400"
              style={{ left: `calc(144px + (100% - 234px) * ${frac(award.floor_total)})` }}>
              <span className="absolute -top-4 -translate-x-1/2 whitespace-nowrap text-[10.5px] text-rose-600">our floor</span>
            </div>
            {bars.map((b, i) => (
              <div key={b.name} className="grid grid-cols-[132px_minmax(0,1fr)_78px] items-center gap-3">
                <span className={clsx("truncate text-[12px]", b.us ? "font-semibold text-ink" : "text-ink-soft")}>{b.name}</span>
                <div className="h-2.5 overflow-hidden rounded-full bg-[#f0f1f4]">
                  <motion.div initial={{ width: 0 }} animate={{ width: x(b.total) }} transition={{ duration: 0.8, delay: 0.05 * i, ease: [0.22, 1, 0.36, 1] }}
                    className={clsx("h-full rounded-full", b.us ? "bg-gradient-to-r from-[#e2c182] to-[#c98a1b]" : "bg-[#b9c0cc]")} />
                </div>
                <span className={clsx("text-right text-[12px] tnum", b.us ? "font-semibold text-ink" : "text-muted")}>{money(b.total, currency, { compact: true })}</span>
              </div>
            ))}
          </div>
          {award.rule !== "L1" && award.combined_score !== null && (
            <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-3 text-[12px]">
              <div><div className="text-muted">Our technical (est.)</div><div className="font-semibold text-ink tnum">{award.technical_score}</div></div>
              <div><div className="text-muted">Our combined</div><div className="font-semibold text-ink tnum">{award.combined_score}</div></div>
              <div><div className="text-muted">Best rival combined</div><div className="font-semibold text-ink tnum">{award.best_competitor_combined}</div></div>
            </div>
          )}
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {award.options.map((o) => (
              <div key={o.label} className={clsx("rounded-lg border px-3 py-2.5", o.feasible ? "border-line" : "border-dashed border-line-strong bg-[#fbfbfc]")}>
                <div className="truncate text-[11.5px] text-muted">{o.label}</div>
                <div className="mt-0.5 text-[13.5px] font-semibold text-ink tnum">{money(o.total, currency, { compact: true })}</div>
                <div className={clsx("text-[11px] tnum", o.margin < 0 ? "text-rose-700" : "text-muted")}>{o.margin_pct.toFixed(1)}% margin</div>
                <div className="mt-1 text-[11px] leading-[1.4] text-ink-soft">{o.outcome}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
