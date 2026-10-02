import clsx from "clsx";
import { AlertTriangle, Check, Circle, X } from "lucide-react";
import type { RfpStatus, StageRun } from "../lib/types";
import { duration } from "../lib/format";
import { Badge, Spinner } from "./ui";

const STATUS: Record<RfpStatus, { label: string; tone: "neutral" | "blue" | "amber" | "green" | "red" }> = {
  queued: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "blue" },
  review: { label: "Awaiting review", tone: "amber" },
  approved: { label: "Approved", tone: "green" },
  rejected: { label: "Declined", tone: "neutral" },
  failed: { label: "Needs attention", tone: "red" },
};

export function StatusBadge({ status }: { status: RfpStatus }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone} dot className={status === "processing" || status === "queued" ? "[&>span:first-child]:animate-pulse-dot" : ""}>
      {s.label}
    </Badge>
  );
}

const STRATEGY_TONE: Record<string, "gold" | "violet" | "blue" | "green" | "neutral" | "amber" | "red"> = {
  "Value differentiation": "gold",
  "Floor defence": "amber",
  "Competitive undercut": "blue",
  "Competitive match": "blue",
  "Margin capture": "green",
  "Value premium": "violet",
  "Standard pricing": "neutral",
  "Reviewer override": "red",
};

export function StrategyBadge({ strategy }: { strategy: string }) {
  return <Badge tone={STRATEGY_TONE[strategy] ?? "neutral"}>{strategy}</Badge>;
}

export const STAGE_LABEL: Record<string, string> = {
  intake: "Intake & parsing",
  costing: "Internal costing",
  compliance: "Tender compliance",
  strategy: "Market & strategy",
  localisation: "Currency & tax",
  drafting: "Proposal drafting",
};

export function StageTracker({ order, stages, onSelect, active }: { order: string[]; stages: StageRun[]; onSelect?: (stage: string) => void; active?: string | null }) {
  // Latest run per stage.
  const latest = new Map<string, StageRun>();
  stages.forEach((s) => latest.set(s.stage, s));
  return (
    <ol className="grid gap-0 overflow-hidden rounded-xl border border-line bg-white" style={{ gridTemplateColumns: `repeat(${order.length}, minmax(0, 1fr))` }}>
      {order.map((key, i) => {
        const run = latest.get(key);
        const state = run?.status ?? "pending";
        return (
          <li key={key} className={clsx(i > 0 && "border-l border-line")}>
            <button
              disabled={!run}
              onClick={() => onSelect?.(key)}
              className={clsx("flex w-full items-center gap-2.5 px-4 py-2.5 text-left transition-colors disabled:cursor-default",
                run && "hover:bg-[#fafbfc]", active === key && "bg-[#fafbfc]")}
            >
              <span className={clsx("grid size-5 shrink-0 place-items-center rounded-full",
                state === "completed" && "bg-emerald-600 text-white", state === "failed" && "bg-rose-600 text-white",
                state === "running" && "bg-blue-50 text-blue-700", state === "pending" && "bg-[#eef0f3] text-subtle")}>
                {state === "completed" ? <Check className="size-3" strokeWidth={3} /> : state === "failed" ? <X className="size-3" strokeWidth={3} />
                  : state === "running" ? <Spinner className="size-3" /> : <Circle className="size-2" />}
              </span>
              <span className="min-w-0">
                <span className="block text-[12.5px] font-medium text-ink">{STAGE_LABEL[key] ?? key}</span>
                <span className="block truncate text-[11.5px] text-muted">
                  {state === "completed" ? duration(run?.duration_ms) : state === "running" ? "In progress" : state === "failed" ? "Failed" : "Waiting"}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export function WarningList({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="rounded-xl border border-amber-200 bg-[#fffaf0] px-4 py-3">
      <ul className="space-y-1.5">
        {items.map((w, i) => (
          <li key={i} className="flex gap-2 text-[12.5px] text-[#7a4a00]">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {w}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CountryTag({ code, name }: { code: string | null; name?: string | null }) {
  if (!code) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="rounded border border-line-strong bg-white px-1 font-mono text-[10px] font-semibold leading-4 text-ink-soft">{code}</span>
      {name && <span>{name}</span>}
    </span>
  );
}
