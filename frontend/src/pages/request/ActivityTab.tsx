import clsx from "clsx";
import { useState } from "react";
import { STAGE_LABEL } from "../../components/domain";
import { Badge, Card } from "../../components/ui";
import type { RfpDetail } from "../../lib/types";
import { date, duration } from "../../lib/format";

function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-IN") : v.toLocaleString("en-IN", { maximumFractionDigits: 4 });
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function ActivityTab({ rfp, focus }: { rfp: RfpDetail; focus: string | null }) {
  const [stage, setStage] = useState<string | null>(focus);
  const runs = [...rfp.stages].reverse().filter((s) => !stage || s.stage === stage);
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <Card title="Processing log" subtitle="What each stage observed and decided, in order" bodyClassName="p-0"
        actions={
          <select className="input h-8 w-48" value={stage ?? ""} onChange={(e) => setStage(e.target.value || null)}>
            <option value="">All stages</option>
            {rfp.stage_order.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
          </select>
        }>
        <div className="divide-y divide-line">
          {runs.map((run) => (
            <details key={run.id} open={runs.length <= 5} className="group">
              <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-3 hover:bg-[#fafbfc]">
                <Badge tone={run.status === "completed" ? "green" : run.status === "failed" ? "red" : "blue"}>{run.status}</Badge>
                <span className="font-medium">{run.agent}</span>
                <span className="flex-1 truncate text-[12.5px] text-muted">{run.summary}</span>
                <span className="text-[12px] text-muted tnum">{duration(run.duration_ms)}</span>
              </summary>
              <ol className="space-y-2 bg-[#fcfcfd] px-5 pb-4 pt-1">
                {run.log.map((e, i) => (
                  <li key={i} className="grid grid-cols-[52px_1fr] gap-3 text-[12.5px]">
                    <span className="pt-0.5 text-right font-mono text-[11px] text-subtle">{e.t_ms} ms</span>
                    <div className={clsx("rounded-lg border px-3 py-2", e.level === "decision" ? "border-[#e8dcc3] bg-[#fffcf5]" : e.level === "warning" ? "border-amber-200 bg-amber-50" : "border-line bg-white")}>
                      <div className="font-medium text-ink">{e.message}</div>
                      {Object.keys(e.data).length > 0 && (
                        <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 text-[11.5px]">
                          {Object.entries(e.data).filter(([k]) => k !== "trace").map(([k, v]) => (
                            <div key={k} className="contents"><dt className="text-muted">{k.replace(/_/g, " ")}</dt><dd className="break-words font-mono text-ink-soft">{fmtValue(v)}</dd></div>
                          ))}
                        </dl>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </details>
          ))}
        </div>
      </Card>
      <Card title="Review history">
        {rfp.events.length === 0 ? <div className="text-[12.5px] text-muted">No review actions yet.</div> : (
          <ol className="space-y-4">
            {[...rfp.events].reverse().map((e) => (
              <li key={e.id} className="text-[12.5px]">
                <div className="flex items-center justify-between"><span className="font-medium capitalize">{e.action}</span><span className="text-muted">{date(e.created_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span></div>
                <div className="text-muted">by {e.actor}</div>
                {e.note && <div className="mt-1 rounded-md bg-[#f6f7f9] px-2 py-1 text-ink-soft">{e.note}</div>}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
