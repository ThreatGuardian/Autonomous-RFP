import { useQuery } from "@tanstack/react-query";
import { FileStack, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CountryTag, StatusBadge, StrategyBadge } from "../components/domain";
import { Page, PageHeader } from "../components/layout/Shell";
import { Button, Empty, Skeleton, Tabs } from "../components/ui";
import { api } from "../lib/api";
import type { RfpSummary } from "../lib/types";
import { date, daysUntil, money, pct, prob, relative } from "../lib/format";

const FILTERS = [
  { value: "all", label: "All", match: () => true },
  { value: "active", label: "In progress", match: (r: RfpSummary) => r.status === "queued" || r.status === "processing" },
  { value: "review", label: "Awaiting review", match: (r: RfpSummary) => r.status === "review" },
  { value: "approved", label: "Approved", match: (r: RfpSummary) => r.status === "approved" },
  { value: "closed", label: "Declined & failed", match: (r: RfpSummary) => r.status === "rejected" || r.status === "failed" },
] as const;
type Filter = (typeof FILTERS)[number]["value"];

export default function Requests() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const filter = (params.get("status") as Filter) || "all";
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["rfps", "all"], queryFn: () => api.rfps(), refetchInterval: 4000 });
  const all = data ?? [];
  const needle = q.trim().toLowerCase();
  const rows = all
    .filter(FILTERS.find((f) => f.value === filter)!.match)
    .filter((r) => !needle || [r.title, r.client_name, r.reference].some((s) => s?.toLowerCase().includes(needle)));

  return (
    <>
      <PageHeader title="Requests" description="Every request for proposal received, with its pricing outcome and review status."
        actions={<Link to="/requests/new"><Button variant="primary">New request</Button></Link>} />
      <Page>
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between gap-4 px-4">
            <Tabs value={filter} onChange={(v) => setParams(v === "all" ? {} : { status: v })}
              items={FILTERS.map((f) => ({ value: f.value, label: f.label, count: all.filter(f.match).length }))} />
            <div className="relative w-72">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-subtle" />
              <input className="input h-8 pl-8" placeholder="Search client, title or reference" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
          {isLoading ? (
            <div className="space-y-2 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}</div>
          ) : rows.length === 0 ? (
            <Empty icon={<FileStack className="size-4" />} title={all.length ? "No requests match" : "No requests yet"}
              description={all.length ? "Try a different filter or search term." : "Paste or upload a request for proposal to produce a priced quotation."}
              action={!all.length && <Link to="/requests/new"><Button variant="primary">New request</Button></Link>} />
          ) : (
            <div className="overflow-x-auto border-t border-line">
              <table className="table-base">
                <thead>
                  <tr><th>Reference</th><th>Request</th><th>Client</th><th>Status</th><th>Due</th><th className="!text-right">Quoted value</th><th className="!text-right">Margin</th><th className="!text-right">Win</th><th>Main strategy</th><th>Updated</th></tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const days = daysUntil(r.due_date);
                    return (
                      <tr key={r.id} className="cursor-pointer hover:bg-[#fafbfc]" onClick={() => navigate(`/requests/${r.id}`)}>
                        <td className="whitespace-nowrap font-mono text-[12px] text-ink-soft">{r.reference}</td>
                        <td className="max-w-[300px]"><div className="truncate font-medium">{r.title}</div><div className="text-[11.5px] text-muted">{r.line_count ? `${r.line_count} line items` : r.source_filename ?? "Pasted text"}</div></td>
                        <td className="max-w-[220px]"><div className="truncate">{r.client_name ?? "—"}</div><div className="mt-0.5"><CountryTag code={r.client_country} /></div></td>
                        <td><StatusBadge status={r.status} /></td>
                        <td className="whitespace-nowrap">{date(r.due_date)}{days !== null && r.status === "review" && <div className={days <= 7 ? "text-[11.5px] text-rose-700" : "text-[11.5px] text-muted"}>{days < 0 ? "Closed" : `${days} days left`}</div>}</td>
                        <td className="text-right tnum font-medium">{money(r.total_client, r.currency ?? "INR")}</td>
                        <td className="text-right tnum">{pct(r.margin_pct)}</td>
                        <td className="text-right tnum">{prob(r.win_probability)}</td>
                        <td>{r.strategy_summary ? <StrategyBadge strategy={r.strategy_summary} /> : <span className="text-muted">—</span>}</td>
                        <td className="whitespace-nowrap text-muted">{relative(r.updated_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Page>
    </>
  );
}
