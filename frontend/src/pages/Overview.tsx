import { useQuery } from "@tanstack/react-query";
import { FileStack } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { CountryTag, STAGE_LABEL, StatusBadge, StrategyBadge } from "../components/domain";
import { Page, PageHeader } from "../components/layout/Shell";
import { Button, Card, Empty, Skeleton, Stat, StatGrid } from "../components/ui";
import { api } from "../lib/api";
import { date, daysUntil, duration, money, pct, prob, relative } from "../lib/format";

export default function Overview() {
  const navigate = useNavigate();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 8000 });
  const rfps = useQuery({ queryKey: ["rfps", "all"], queryFn: () => api.rfps(), refetchInterval: 5000 });
  const d = dash.data;
  const ccy = d?.base_currency ?? "INR";
  const review = (rfps.data ?? []).filter((r) => r.status === "review");
  const active = (rfps.data ?? []).filter((r) => r.status === "queued" || r.status === "processing");
  const mix = Object.entries(d?.strategy_mix ?? {});
  const mixTotal = mix.reduce((a, [, v]) => a + v, 0);
  const today = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(new Date());

  return (
    <>
      <PageHeader
        title="Overview"
        description={today}
        actions={<Link to="/app/requests/new"><Button variant="primary">New request</Button></Link>}
      />
      <Page className="space-y-6">
        {d ? (
          <StatGrid cols={5}>
            <Stat label="Open pipeline" value={money(d.pipeline_value, ccy, { compact: true })} hint={`${d.counts.review ?? 0} quotations awaiting review`} />
            <Stat label="Probability-weighted" value={money(d.weighted_value, ccy, { compact: true })} hint="Revenue × modelled win rate" />
            <Stat label="Approved value" value={money(d.approved_value, ccy, { compact: true })} hint={`${d.counts.approved ?? 0} quotations approved`} />
            <Stat label="Average margin" value={pct(d.average_margin_pct)} hint="Gross, after bundled services" />
            <Stat label="Turnaround" value={d.average_turnaround_s ? `${d.average_turnaround_s.toFixed(1)} s` : "—"} hint="Request received → draft ready" />
          </StatGrid>
        ) : (
          <Skeleton className="h-[104px] w-full rounded-xl" />
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_310px]">
          <Card title="Awaiting your review" subtitle="Draft quotations ready for commercial sign-off" bodyClassName="p-0"
            actions={<Link to="/app/requests?status=review" className="text-[12.5px] font-medium text-link hover:underline">View all</Link>}>
            {rfps.isLoading ? (
              <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            ) : review.length === 0 ? (
              <Empty icon={<FileStack className="size-4" />} title="Nothing waiting" description="New requests appear here as soon as their draft quotation is ready."
                action={<Link to="/app/requests/new"><Button>Start a request</Button></Link>} />
            ) : (
              <div className="overflow-x-auto"><table className="table-base">
                <thead><tr><th>Request</th><th>Client</th><th>Due</th><th className="!text-right">Value</th><th className="!text-right">Margin</th><th className="!text-right">Win</th></tr></thead>
                <tbody>
                  {review.slice(0, 8).map((r) => {
                    const days = daysUntil(r.due_date);
                    return (
                      <tr key={r.id} onClick={() => navigate(`/app/requests/${r.id}`)} className="cursor-pointer hover:bg-[#fafbfc]">
                        <td className="max-w-[230px]"><div className="truncate font-medium">{r.title}</div><div className="text-[11.5px] text-muted">{r.reference}</div></td>
                        <td className="max-w-[190px]"><div className="truncate">{r.client_name ?? "—"}</div><div className="mt-0.5"><CountryTag code={r.client_country} /></div></td>
                        <td className="whitespace-nowrap">{date(r.due_date)}{days !== null && <div className={days <= 7 ? "text-[11.5px] text-rose-700" : "text-[11.5px] text-muted"}>{days < 0 ? "Closed" : `${days} days left`}</div>}</td>
                        <td className="text-right tnum font-medium">{money(r.total_client, r.currency ?? ccy)}</td>
                        <td className="text-right tnum">{pct(r.margin_pct)}</td>
                        <td className="text-right tnum">{prob(r.win_probability)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table></div>
            )}
          </Card>

          <div className="space-y-6">
            <Card title="In progress" subtitle={active.length ? `${active.length} request(s) being processed` : "No requests in progress"} bodyClassName="p-0">
              {active.length === 0 ? <div className="px-5 py-4 text-[12.5px] text-muted">New requests are parsed, priced and drafted automatically.</div> : (
                <ul className="divide-y divide-line">
                  {active.map((r) => (
                    <li key={r.id}><Link to={`/app/requests/${r.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-[#fafbfc]">
                      <span className="truncate font-medium">{r.client_name ?? r.title}</span><StatusBadge status={r.status} /></Link></li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Pricing strategies applied" subtitle="Across all priced line items">
              {mix.length === 0 ? <div className="text-[12.5px] text-muted">No priced requests yet.</div> : (
                <ul className="space-y-3">
                  {mix.map(([k, v]) => (
                    <li key={k}>
                      <div className="flex items-center justify-between"><StrategyBadge strategy={k} /><span className="tnum text-[12.5px] text-muted">{v}</span></div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#eef0f3]"><div className="h-full rounded-full bg-ink/80" style={{ width: `${(100 * v) / mixTotal}%` }} /></div>
                    </li>
                  ))}
                </ul>
              )}
              {!!d?.below_cost_encounters && (
                <p className="mt-4 border-t border-line pt-3 text-[12px] text-muted">
                  {d.below_cost_encounters} line(s) met competitors priced below our landed cost; none were matched at a loss.
                </p>
              )}
            </Card>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card title="Requests received" subtitle="Last 14 days">
            <div className="h-[180px]">
              <ResponsiveContainer>
                <BarChart data={d?.intake_by_day ?? []} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                  <XAxis dataKey="date" tickFormatter={(v) => date(v, { day: "numeric", month: "short" })} tick={{ fontSize: 11, fill: "#9aa1ad" }} axisLine={false} tickLine={false} interval={1} />
                  <Tooltip cursor={{ fill: "#f3f4f6" }} contentStyle={{ borderRadius: 8, border: "1px solid #e6e8ec", fontSize: 12 }} labelFormatter={(v) => date(String(v))} />
                  <Bar dataKey="received" name="Requests" fill="#0b1220" radius={[3, 3, 0, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Processing time by stage" subtitle="Average per request">
            <ul className="space-y-3">
              {Object.entries(STAGE_LABEL).map(([k, label]) => {
                const ms = d?.average_stage_ms?.[k];
                const max = Math.max(1, ...Object.values(d?.average_stage_ms ?? { a: 1 }));
                return (
                  <li key={k} className="grid grid-cols-[150px_1fr_64px] items-center gap-3">
                    <span className="text-[12.5px] text-ink-soft">{label}</span>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#eef0f3]"><div className="h-full rounded-full bg-[#c98a1b]" style={{ width: `${ms ? (100 * ms) / max : 0}%` }} /></div>
                    <span className="text-right tnum text-[12px] text-muted">{duration(ms)}</span>
                  </li>
                );
              })}
            </ul>
            <p className="mt-4 border-t border-line pt-3 text-[12px] text-muted">
              Last updated {rfps.data?.[0] ? relative(rfps.data[0].updated_at) : "—"}.
            </p>
          </Card>
        </div>
      </Page>
    </>
  );
}
