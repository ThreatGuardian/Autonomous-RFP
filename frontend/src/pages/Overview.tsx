import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { motion } from "motion/react";
import { ArrowUpRight, CalendarClock, CircleGauge, FileStack, Hourglass, Plus, ShieldAlert, ShieldCheck, ShieldX, Wallet } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { STAGE_LABEL, StrategyBadge } from "../components/domain";
import { Page } from "../components/layout/Shell";
import { AnimatedNumber, EASE, Rise, Stagger } from "../components/motion";
import { Button, Card, Empty, Segmented, Skeleton } from "../components/ui";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import type { Dashboard, RfpSummary } from "../lib/types";
import { date, daysUntil, duration, getBaseCurrency, money, pct } from "../lib/format";

export default function Overview() {
  const { user } = useAuth();
  const [view, setView] = useState<"focus" | "insights">("focus");
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 8000 });
  const rfps = useQuery({ queryKey: ["rfps", "all"], queryFn: () => api.rfps(), refetchInterval: 5000 });
  const d = dash.data;
  const ccy = d?.base_currency ?? getBaseCurrency();
  const all = rfps.data ?? [];
  const review = all.filter((r) => r.status === "review");
  const active = all.filter((r) => r.status === "queued" || r.status === "processing");
  const upcoming = all.filter((r) => r.due_date && (daysUntil(r.due_date) ?? -1) >= 0 && r.status !== "rejected")
    .sort((a, b) => (a.due_date! < b.due_date! ? -1 : 1)).slice(0, 5);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const next = upcoming[0];
  const nextDays = next ? daysUntil(next.due_date) : null;

  return (
    <Page className="space-y-7 pt-9">
      <motion.header initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE }}
        className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[12.5px] text-muted">{new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</div>
          <h1 className="mt-1 text-[28px] font-semibold tracking-[-0.022em] text-ink">{greeting}{user ? `, ${user.name.split(" ")[0]}` : ""}</h1>
          <p className="mt-1.5 text-[14px] text-ink-soft">
            {review.length ? <><span className="font-semibold text-ink">{review.length} quotation{review.length > 1 ? "s" : ""}</span> waiting for your decision</> : "Nothing is waiting for your decision"}
            {next && nextDays !== null && <> · next deadline <span className={clsx("font-semibold", nextDays <= 7 ? "text-rose-700" : "text-ink")}>{nextDays === 0 ? "today" : `in ${nextDays} days`}</span></>}
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Segmented value={view} onChange={setView} items={[{ value: "focus", label: "Focus" }, { value: "insights", label: "Insights" }]} />
          <Link to="/app/requests/new"><Button variant="primary" icon={<Plus className="size-4" />}>New request</Button></Link>
        </div>
      </motion.header>

      <Stagger className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Rise><Metric icon={<Wallet />} label="Open pipeline" loading={!d}
          value={d && <AnimatedNumber value={d.pipeline_value} format={(v) => money(v, ccy, { compact: true })} />}
          hint={d && `${money(d.weighted_value, ccy, { compact: true })} weighted by win chance`} /></Rise>
        <Rise><Metric icon={<Hourglass />} label="Awaiting decision" loading={!d} tone="gold"
          value={d && <AnimatedNumber value={review.length} format={(v) => String(Math.round(v))} />}
          hint={d && `${money(review.reduce((a, r) => a + (r.total_base ?? 0), 0), ccy, { compact: true })} in draft quotations`} /></Rise>
        <Rise><Metric icon={<CircleGauge />} label="Average margin" loading={!d}
          value={d && <AnimatedNumber value={d.average_margin_pct ?? 0} format={(v) => pct(v)} />}
          hint={d && `${d.counts.approved ?? 0} approved · ${d.average_turnaround_s ? `${d.average_turnaround_s.toFixed(1)} s to draft` : "—"}`} /></Rise>
      </Stagger>

      {view === "focus" ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <Card title="Needs your decision" bodyClassName="p-2"
            actions={<Link to="/app/requests?status=review" className="text-[12.5px] font-medium text-link hover:underline">View all</Link>}>
            {rfps.isLoading ? (
              <div className="space-y-2 p-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
            ) : review.length === 0 ? (
              <Empty icon={<FileStack className="size-4" />} title="You're all caught up" description="Draft quotations appear here as soon as they are ready."
                action={<Link to="/app/requests/new"><Button>Start a request</Button></Link>} />
            ) : (
              <Stagger>{review.slice(0, 6).map((r) => <Rise key={r.id}><DecisionRow r={r} ccy={ccy} /></Rise>)}</Stagger>
            )}
          </Card>
          <div className="space-y-6">
            <Card title="Upcoming deadlines" actions={<CalendarClock className="size-4 text-subtle" />}>
              {upcoming.length === 0 ? <div className="text-[12.5px] text-muted">No open deadlines.</div> : (
                <ol className="relative space-y-4 before:absolute before:bottom-1 before:left-[5px] before:top-1 before:w-px before:bg-line">
                  {upcoming.map((r) => {
                    const days = daysUntil(r.due_date)!;
                    return (
                      <li key={r.id} className="relative pl-5">
                        <span className={clsx("absolute left-0 top-1.5 size-[11px] rounded-full ring-[3px] ring-white", days <= 7 ? "bg-rose-500" : days <= 21 ? "bg-[#c98a1b]" : "bg-[#9aa3b0]")} />
                        <Link to={`/app/requests/${r.id}`} className="group block">
                          <div className="flex items-baseline justify-between gap-3">
                            <span className="truncate text-[12.5px] font-medium text-ink group-hover:underline">{r.client_name ?? r.title}</span>
                            <span className={clsx("shrink-0 text-[11.5px] tnum", days <= 7 ? "font-semibold text-rose-700" : "text-muted")}>{days === 0 ? "today" : `${days} d`}</span>
                          </div>
                          <div className="text-[11.5px] text-muted">{date(r.due_date)}</div>
                        </Link>
                      </li>
                    );
                  })}
                </ol>
              )}
            </Card>
            {active.length > 0 && (
              <Card title="Being prepared" bodyClassName="p-0">
                <ul className="divide-y divide-line">
                  {active.map((r) => (
                    <li key={r.id}><Link to={`/app/requests/${r.id}`} className="block px-5 py-3 hover:bg-[#fafbfc]">
                      <div className="truncate text-[12.5px] font-medium">{r.client_name ?? r.title}</div>
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-[#eef0f3]">
                        <motion.div className="h-full w-1/3 rounded-full bg-gradient-to-r from-transparent via-[#c98a1b] to-transparent"
                          animate={{ x: ["-100%", "300%"] }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }} />
                      </div>
                    </Link></li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        </div>
      ) : (
        <Insights d={d} ccy={ccy} />
      )}
    </Page>
  );
}

function Metric({ icon, label, value, hint, loading, tone }: { icon: ReactNode; label: string; value: ReactNode; hint: ReactNode; loading?: boolean; tone?: "gold" }) {
  return (
    <motion.div whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 380, damping: 26 }}
      className="card relative overflow-hidden px-5 py-5 hover:shadow-[0_18px_40px_-24px_rgb(11_18_32/0.35)]">
      <div className="flex items-center gap-2.5">
        <span className={clsx("grid size-8 place-items-center rounded-lg [&>svg]:size-4", tone === "gold" ? "bg-accent-soft text-[#8a5a0b]" : "bg-[#f1f3f6] text-ink-soft")}>{icon}</span>
        <span className="text-[12.5px] font-medium text-muted">{label}</span>
      </div>
      {loading ? <Skeleton className="mt-4 h-8 w-32" /> : <div className="mt-3.5 text-[30px] font-semibold tracking-[-0.025em] text-ink">{value}</div>}
      <div className="mt-1 text-[12px] text-muted">{hint}</div>
      <div className="pointer-events-none absolute -right-10 -top-10 size-32 rounded-full bg-[radial-gradient(circle,rgb(201_138_27/0.08),transparent_70%)]" />
    </motion.div>
  );
}

const REC = {
  Bid: { icon: ShieldCheck, label: "Bid", cls: "bg-emerald-50 text-emerald-800 ring-emerald-200/70" },
  "Bid with clarifications": { icon: ShieldAlert, label: "Clarify first", cls: "bg-accent-soft text-[#8a5a0b] ring-[#f1dfb8]" },
  "Do not bid": { icon: ShieldX, label: "No bid", cls: "bg-rose-50 text-rose-800 ring-rose-200/70" },
} as const;

function DecisionRow({ r, ccy }: { r: RfpSummary; ccy: string }) {
  const navigate = useNavigate();
  const days = daysUntil(r.due_date);
  const rec = r.recommendation ? REC[r.recommendation] : null;
  const initials = (r.client_name ?? r.title).split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("") || "RF";
  return (
    <motion.button whileHover={{ x: 2 }} transition={{ type: "spring", stiffness: 400, damping: 30 }}
      onClick={() => navigate(`/app/requests/${r.id}`)}
      className="group flex w-full items-center gap-4 rounded-xl px-3 py-3 text-left transition-colors hover:bg-[#f7f8fa]">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[#1e2a36] to-[#0b1220] text-[12px] font-semibold text-[#e4c98f]">{initials}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-semibold text-ink">{r.client_name ?? r.title}</span>
        <span className="mt-0.5 block truncate text-[12px] text-muted">{r.title}{r.pages ? ` · ${r.pages}-page tender` : ""}</span>
      </span>
      {rec && (
        <span className={clsx("hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-medium ring-1 ring-inset md:inline-flex", rec.cls)}>
          <rec.icon className="size-3.5" /> {rec.label}
        </span>
      )}
      <span className="w-[92px] shrink-0 text-right">
        <span className="block text-[13px] font-semibold text-ink tnum">{money(r.total_client, r.currency ?? ccy, { compact: true })}</span>
        <span className={clsx("block text-[11.5px] tnum", days !== null && days <= 7 ? "text-rose-700" : "text-muted")}>
          {days === null ? "No deadline" : days < 0 ? "Closed" : days === 0 ? "Due today" : `${days} days left`}
        </span>
      </span>
      <ArrowUpRight className="size-4 shrink-0 text-subtle opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
    </motion.button>
  );
}

function Insights({ d, ccy }: { d: Dashboard | undefined; ccy: string }) {
  const mix = Object.entries(d?.strategy_mix ?? {});
  const mixTotal = mix.reduce((a, [, v]) => a + v, 0) || 1;
  const max = Math.max(1, ...Object.values(d?.average_stage_ms ?? { a: 1 }));
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: EASE }}
      className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <Card title="Requests received" subtitle="Last 14 days" className="lg:col-span-2">
        <div className="h-[220px]">
          <ResponsiveContainer>
            <BarChart data={d?.intake_by_day ?? []} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" tickFormatter={(v) => date(v, { day: "numeric", month: "short" })} tick={{ fontSize: 11, fill: "#9aa1ad" }} axisLine={false} tickLine={false} interval={1} />
              <Tooltip cursor={{ fill: "#f3f4f6" }} contentStyle={{ borderRadius: 10, border: "1px solid #e6e8ec", fontSize: 12 }} labelFormatter={(v) => date(String(v))} />
              <Bar dataKey="received" name="Requests" fill="#0b1220" radius={[4, 4, 0, 0]} maxBarSize={22} animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="How lines were priced">
        {mix.length === 0 ? <div className="text-[12.5px] text-muted">No priced requests yet.</div> : (
          <ul className="space-y-3">
            {mix.map(([k, v], i) => (
              <li key={k}>
                <div className="flex items-center justify-between"><StrategyBadge strategy={k} /><span className="tnum text-[12.5px] text-muted">{v}</span></div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#eef0f3]">
                  <motion.div className="h-full rounded-full bg-ink/80" initial={{ width: 0 }} animate={{ width: `${(100 * v) / mixTotal}%` }} transition={{ duration: 0.8, delay: i * 0.05, ease: EASE }} />
                </div>
              </li>
            ))}
          </ul>
        )}
        {!!d?.below_cost_encounters && <p className="mt-4 border-t border-line pt-3 text-[12px] text-muted">{d.below_cost_encounters} line(s) met below-cost rivals; none were matched at a loss.</p>}
      </Card>
      <Card title="Time to draft, by stage" className="lg:col-span-3">
        <ul className="grid grid-cols-1 gap-x-10 gap-y-3 md:grid-cols-2">
          {Object.entries(STAGE_LABEL).map(([k, label], i) => {
            const ms = d?.average_stage_ms?.[k];
            return (
              <li key={k} className="grid grid-cols-[150px_1fr_64px] items-center gap-3">
                <span className="text-[12.5px] text-ink-soft">{label}</span>
                <div className="h-1.5 overflow-hidden rounded-full bg-[#eef0f3]">
                  <motion.div className="h-full rounded-full bg-[#c98a1b]" initial={{ width: 0 }} animate={{ width: `${ms ? (100 * ms) / max : 0}%` }} transition={{ duration: 0.8, delay: i * 0.05, ease: EASE }} />
                </div>
                <span className="text-right tnum text-[12px] text-muted">{duration(ms)}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-4 border-t border-line pt-3 text-[12px] text-muted">Approved value to date: {money(d?.approved_value, ccy, { compact: true })}.</p>
      </Card>
    </motion.div>
  );
}

