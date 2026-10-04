import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle, CalendarClock, Check, ChevronRight, FileCheck2, FileText, ListChecks, Pencil, RotateCcw, Scale, Search,
  ShieldAlert, ShieldCheck, ShieldX, Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, Card, Empty, Field, Meter, Segmented, Sheet } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api } from "../../lib/api";
import type {
  ComplianceItem, ComplianceReport, ComplianceStatus, EligibilityCheck, EligibilityStatus, RfpDetail, TenderDocument, TenderSection,
} from "../../lib/types";
import { date, daysUntil, getBaseCurrency, money } from "../../lib/format";
import { MotionRow, rowMotion } from "../../components/motion";

type Tone = "neutral" | "blue" | "amber" | "green" | "red" | "violet" | "gold";

export const STATUS_TONE: Record<ComplianceStatus, Tone> = {
  Complies: "green", "Complies with note": "amber", "Clarification required": "blue", Deviation: "red", Noted: "neutral",
};
const ELIGIBILITY_TONE: Record<EligibilityStatus, Tone> = {
  Meets: "green", "Documents required": "gold", "Needs review": "amber", "Does not meet": "red",
};
const CATEGORY_LABEL: Record<string, string> = {
  eligibility: "Eligibility", technical: "Technical", scope: "Scope of work", delivery: "Delivery", warranty: "Warranty & support",
  commercial: "Commercial", standards: "Standards", legal: "Legal & contractual", submission: "Bid submission", evaluation: "Evaluation",
};
const KIND_LABEL: Record<string, string> = {
  notice: "Notice", instructions: "Instructions", eligibility: "Eligibility", scope: "Scope", technical: "Technical",
  boq: "Bill of quantities", commercial: "Commercial", evaluation: "Evaluation", conditions: "Conditions", forms: "Forms", general: "General",
};
const KIND_DOT: Record<string, string> = {
  notice: "bg-slate-400", instructions: "bg-slate-300", eligibility: "bg-[#c98a1b]", scope: "bg-sky-500", technical: "bg-indigo-500",
  boq: "bg-emerald-500", commercial: "bg-amber-500", evaluation: "bg-violet-500", conditions: "bg-rose-400", forms: "bg-slate-300",
  general: "bg-slate-200",
};
const STATUSES: ComplianceStatus[] = ["Complies", "Complies with note", "Clarification required", "Deviation", "Noted"];
const ELIGIBILITY_STATUSES: EligibilityStatus[] = ["Meets", "Documents required", "Needs review", "Does not meet"];

type Filter = "all" | "exceptions" | "Deviation" | "Clarification required" | "verify";

export function ComplianceTab({ rfp, editable }: { rfp: RfpDetail; editable: boolean }) {
  const report = rfp.compliance;
  const doc = rfp.parsed?.document ?? null;
  const [openItem, setOpenItem] = useState<ComplianceItem | null>(null);
  const [openCheck, setOpenCheck] = useState<EligibilityCheck | null>(null);
  if (!report) return <Card><Empty title="Compliance review not available" description="It is prepared after the request has been parsed and costed." /></Card>;

  return (
    <div className="space-y-5">
      <RecommendationBanner report={report} doc={doc} />
      {doc?.long_form && (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <KeyDates doc={doc} />
          <TenderData doc={doc} report={report} currency={rfp.parsed?.currency.code ?? getBaseCurrency()} />
          <Evaluation doc={doc} />
        </div>
      )}
      {report.eligibility.length > 0 && <EligibilityCard report={report} onOpen={setOpenCheck} />}
      <Matrix report={report} doc={doc} onOpen={setOpenItem} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Risks report={report} />
        <Checklist report={report} />
      </div>
      {openItem && <ItemSheet rfp={rfp} item={openItem} editable={editable} onClose={() => setOpenItem(null)} />}
      {openCheck && <CheckSheet rfp={rfp} check={openCheck} editable={editable} onClose={() => setOpenCheck(null)} />}
    </div>
  );
}

// ----------------------------------------------------------------------------- recommendation

function RecommendationBanner({ report, doc }: { report: ComplianceReport; doc: TenderDocument | null }) {
  const rec = report.recommendation;
  const tone = rec === "Bid" ? "green" : rec === "Do not bid" ? "red" : "amber";
  const Icon = rec === "Bid" ? ShieldCheck : rec === "Do not bid" ? ShieldX : ShieldAlert;
  const deviations = report.counts["Deviation"] ?? 0;
  const clarifications = report.counts["Clarification required"] ?? 0;
  const met = report.mandatory_total ? report.mandatory_met / report.mandatory_total : 1;
  return (
    <section className={clsx("card overflow-hidden border-l-[3px]",
      tone === "green" ? "border-l-emerald-600" : tone === "red" ? "border-l-rose-600" : "border-l-[#c98a1b]")}>
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
        <div className="flex gap-4 px-6 py-5">
          <span className={clsx("grid size-10 shrink-0 place-items-center rounded-full",
            tone === "green" ? "bg-emerald-50 text-emerald-700" : tone === "red" ? "bg-rose-50 text-rose-700" : "bg-accent-soft text-[#8a5a0b]")}>
            <Icon className="size-5" />
          </span>
          <div className="min-w-0">
            <div className="label">Bid recommendation</div>
            <div className="mt-1 text-[19px] font-semibold tracking-[-0.01em] text-ink">{rec}</div>
            <ul className="mt-2 space-y-1 text-[12.5px] text-ink-soft">
              {report.reasons.map((r, i) => <li key={i} className="flex gap-2"><ChevronRight className="mt-0.5 size-3.5 shrink-0 text-subtle" />{r}</li>)}
            </ul>
            {doc?.long_form && (
              <div className="mt-3 text-[11.5px] text-muted">
                Read {doc.pages} {doc.pages_estimated ? "estimated " : ""}pages · {doc.sections.length} sections · {doc.tables} tables
                {doc.removed_lines > 0 && ` · ${doc.removed_lines} running header and footer lines ignored`}
                {doc.scanned_pages.length > 0 && ` · ${doc.scanned_pages.length} scanned page(s) need OCR`}
              </div>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 divide-x divide-line border-t border-line bg-[#fbfbfc] lg:border-l lg:border-t-0">
          <div className="px-5 py-4">
            <div className="label">Eligibility</div>
            <div className="mt-1.5 text-[14px] font-semibold text-ink">{report.eligibility_verdict}</div>
            <div className="mt-1 text-[11.5px] text-muted">
              {report.eligibility.length ? `${report.eligibility.filter((e) => e.status === "Meets").length} of ${report.eligibility.length} criteria met outright` : "No pre-qualification criteria"}
            </div>
          </div>
          <div className="px-5 py-4">
            <div className="label">Mandatory clauses</div>
            <div className="mt-1.5 text-[20px] font-semibold text-ink tnum">{report.mandatory_met}<span className="text-[13px] text-muted">/{report.mandatory_total}</span></div>
            <div className="mt-2"><Meter value={met} tone={met >= 0.95 ? "green" : met >= 0.85 ? "amber" : "red"} /></div>
          </div>
          <div className="px-5 py-4">
            <div className="label">Exceptions</div>
            <div className="mt-1.5 flex items-baseline gap-3 tnum">
              <span className="text-[20px] font-semibold text-rose-700">{deviations}</span>
              <span className="text-[20px] font-semibold text-blue-700">{clarifications}</span>
            </div>
            <div className="mt-1 text-[11.5px] text-muted">deviations · clarifications</div>
          </div>
        </div>
      </div>
      {report.benefits.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-line bg-[#f7fbf8] px-6 py-2.5 text-[12px] text-emerald-900">
          <span className="inline-flex items-center gap-1.5 font-semibold"><Sparkles className="size-3.5" /> MSE advantages</span>
          {report.benefits.map((b) => <span key={b}>{b}</span>)}
        </div>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------- tender overview

function KeyDates({ doc }: { doc: TenderDocument }) {
  const next = doc.key_dates.find((d) => (daysUntil(d.date) ?? -1) >= 0);
  return (
    <Card title="Key dates" subtitle="From the notice inviting tender" actions={<CalendarClock className="size-4 text-subtle" />}>
      {doc.key_dates.length === 0 ? <div className="text-[12.5px] text-muted">No dated milestones found.</div> : (
        <ol className="relative space-y-3.5 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-line">
          {doc.key_dates.map((d) => {
            const days = daysUntil(d.date);
            const passed = days !== null && days < 0;
            const key = d.key === "submission";
            return (
              <li key={d.key} className="relative flex gap-3 pl-5">
                <span className={clsx("absolute left-0 top-1.5 size-[11px] rounded-full ring-[3px] ring-white",
                  key ? "bg-[#c98a1b]" : d === next ? "bg-ink" : passed ? "bg-[#d5d8de]" : "bg-[#9aa3b0]")} />
                <div className="min-w-0 flex-1">
                  <div className={clsx("text-[12.5px]", key ? "font-semibold text-ink" : "text-ink-soft", passed && "text-muted")}>{d.label}</div>
                  <div className="text-[11.5px] text-muted">{date(d.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}{d.time && ` · ${d.time}`}</div>
                </div>
                <span className={clsx("self-start whitespace-nowrap text-[11.5px] tnum", passed ? "text-subtle" : key ? "font-semibold text-[#8a5a0b]" : "text-muted")}>
                  {days === null ? "" : passed ? "passed" : days === 0 ? "today" : `in ${days} d`}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

function TenderData({ doc, report, currency }: { doc: TenderDocument; report: ComplianceReport; currency: string }) {
  const facts = doc.facts.filter((f) => !["reference", "payment", "local_content", "msme"].includes(f.key));
  const payment = doc.facts.find((f) => f.key === "payment");
  return (
    <Card title="Tender data" subtitle="Values as stated in the document" actions={<FileText className="size-4 text-subtle" />}>
      <dl className="space-y-2.5">
        {facts.map((f) => (
          <div key={f.key} className="flex items-baseline justify-between gap-4">
            <dt className="shrink-0 text-[12px] text-muted">{f.label}</dt>
            <dd className="min-w-0 text-right text-[12.5px] text-ink" title={f.evidence ?? undefined}>
              {f.amount && ["estimated_value", "emd", "tender_fee"].includes(f.key) ? money(f.amount, currency, { compact: f.amount >= 1e5 }) : f.value}
              {f.key === "emd" && f.value.includes("exempt") && <span className="ml-1.5"><Badge tone="green">MSE exempt</Badge></span>}
            </dd>
          </div>
        ))}
        {payment && (
          <div className="border-t border-line pt-2.5">
            <dt className="text-[12px] text-muted">Payment milestones</dt>
            <dd className="mt-1 text-[12px] leading-[1.55] text-ink-soft">{payment.value}</dd>
          </div>
        )}
        <div className="flex items-baseline justify-between gap-4 border-t border-line pt-2.5">
          <dt className="text-[12px] text-muted">Our estimate at standard price</dt>
          <dd className="text-[12.5px] font-medium text-ink tnum">{money(report.contract_value_estimate, getBaseCurrency(), { compact: true })}</dd>
        </div>
      </dl>
    </Card>
  );
}

function Evaluation({ doc }: { doc: TenderDocument }) {
  const ev = doc.evaluation;
  const maxMarks = Math.max(1, ...ev.criteria.map((c) => c.marks));
  return (
    <Card title="Evaluation" subtitle="How the award will be decided" actions={<Scale className="size-4 text-subtle" />}>
      <div className="text-[18px] font-semibold tracking-[-0.01em] text-ink">
        {ev.method === "L1" ? "L1 — lowest evaluated price" : ev.method === "QCBS" ? "Quality and cost (QCBS)" : ev.method === "Weighted" ? "Weighted scoring" : "Not stated"}
      </div>
      {ev.method === "QCBS" && ev.technical_weight !== null && ev.financial_weight !== null && (
        <div className="mt-3">
          <div className="flex h-2 overflow-hidden rounded-full">
            <div className="bg-ink" style={{ width: `${ev.technical_weight}%` }} />
            <div className="bg-[#c98a1b]" style={{ width: `${ev.financial_weight}%` }} />
          </div>
          <div className="mt-1.5 flex justify-between text-[11.5px] text-muted">
            <span><span className="font-medium text-ink">{ev.technical_weight}%</span> technical</span>
            <span><span className="font-medium text-ink">{ev.financial_weight}%</span> price</span>
          </div>
        </div>
      )}
      {ev.min_technical_score !== null && <div className="mt-2 text-[12px] text-ink-soft">Minimum technical score to qualify: <span className="font-medium text-ink">{ev.min_technical_score}</span></div>}
      {ev.criteria.length > 0 && (
        <ul className="mt-3 space-y-2">
          {ev.criteria.map((c) => (
            <li key={c.criterion}>
              <div className="flex justify-between gap-3 text-[12px]"><span className="truncate text-ink-soft">{c.criterion}</span><span className="tnum text-muted">{c.marks}</span></div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-[#eceef1]"><div className="h-full rounded-full bg-[#9aa3b0]" style={{ width: `${(100 * c.marks) / maxMarks}%` }} /></div>
            </li>
          ))}
        </ul>
      )}
      {ev.evidence && ev.criteria.length === 0 && <p className="mt-3 border-l-2 border-line pl-3 text-[12px] leading-[1.55] text-muted">{ev.evidence}</p>}
      {ev.notes.length > 0 && (
        <ul className="mt-3 space-y-1 text-[11.5px] text-muted">{ev.notes.map((n) => <li key={n}>· {n}</li>)}</ul>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- eligibility

function EligibilityCard({ report, onOpen }: { report: ComplianceReport; onOpen: (c: EligibilityCheck) => void }) {
  return (
    <Card title="Eligibility and pre-qualification" subtitle="Each criterion checked against the company profile — turnover, credentials, certifications, partnerships and offices"
      actions={<Badge tone={report.eligibility_verdict === "Not eligible" ? "red" : report.eligibility_verdict === "Eligible" ? "green" : "amber"}>{report.eligibility_verdict}</Badge>}
      bodyClassName="p-0">
      <table className="table-base">
        <thead><tr><th className="w-[74px]">Clause</th><th className="w-[200px]">Criterion</th><th className="w-[150px]">Status</th><th>Our position</th><th className="w-10" /></tr></thead>
        <tbody>
          {report.eligibility.map((c, rowIndex) => (
            <MotionRow {...rowMotion(rowIndex)} key={c.id} className="cursor-pointer" onClick={() => onOpen(c)}>
              <td className="font-mono text-[11.5px] text-muted">{c.clause ?? c.id}</td>
              <td><div className="font-medium">{c.label}</div><div className="line-clamp-1 text-[11.5px] text-muted" title={c.text}>{c.text}</div></td>
              <td><Badge tone={ELIGIBILITY_TONE[c.status]} dot>{c.status}</Badge>{c.overridden && <div className="mt-1 text-[11px] text-muted">Set by reviewer</div>}</td>
              <td className="text-ink-soft"><div className="line-clamp-2">{c.position}</div>
                {c.evidence.length > 0 && <div className="mt-0.5 line-clamp-1 text-[11.5px] text-muted">{c.evidence.join(" · ")}</div>}</td>
              <td><ChevronRight className="size-4 text-subtle" /></td>
            </MotionRow>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// ----------------------------------------------------------------------------- matrix

function descendants(sections: TenderSection[], id: string): Set<string> {
  const out = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const s of sections) {
      if (s.parent && out.has(s.parent) && !out.has(s.id)) {
        out.add(s.id);
        grew = true;
      }
    }
  }
  return out;
}

function Matrix({ report, doc, onOpen }: { report: ComplianceReport; doc: TenderDocument | null; onOpen: (i: ComplianceItem) => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [mandatoryOnly, setMandatoryOnly] = useState(false);
  const [section, setSection] = useState<string | null>(null);
  const sections = doc?.long_form ? doc.sections : [];
  const scope = useMemo(() => (section ? descendants(sections, section) : null), [section, sections]);

  const items = report.items.filter((i) => {
    if (filter === "exceptions" && !["Deviation", "Clarification required", "Complies with note"].includes(i.status)) return false;
    if ((filter === "Deviation" || filter === "Clarification required") && i.status !== filter) return false;
    if (filter === "verify" && !i.verify) return false;
    if (category && i.category !== category) return false;
    if (mandatoryOnly && i.modality !== "mandatory") return false;
    if (scope && (!i.section || !scope.has(i.section))) return false;
    if (q && !`${i.text} ${i.response} ${i.clause ?? ""}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const count = (f: (i: ComplianceItem) => boolean) => report.items.filter(f).length;
  const categories = Array.from(new Set(report.items.map((i) => i.category)));

  return (
    <Card title="Clause-by-clause compliance" subtitle={`${report.items.length} obligations answered from product data, the company profile and the knowledge base`}
      bodyClassName="p-0">
      <div className="flex flex-wrap items-center gap-2.5 border-b border-line px-5 py-3">
        <div className="relative w-[240px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-subtle" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search clauses and responses" className="input h-8 pl-8 text-[12.5px]" />
        </div>
        <Segmented value={filter} onChange={setFilter} items={[
          { value: "all", label: `All ${report.items.length}` },
          { value: "exceptions", label: `Qualified ${count((i) => ["Deviation", "Clarification required", "Complies with note"].includes(i.status))}` },
          { value: "Deviation", label: `Deviations ${count((i) => i.status === "Deviation")}` },
          { value: "Clarification required", label: `Clarify ${count((i) => i.status === "Clarification required")}` },
          { value: "verify", label: `To verify ${count((i) => i.verify)}` },
        ]} />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="input h-8 w-[170px] text-[12.5px]">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? c}</option>)}
        </select>
        <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-[12.5px] text-ink-soft">
          <input type="checkbox" checked={mandatoryOnly} onChange={(e) => setMandatoryOnly(e.target.checked)} className="size-3.5 accent-[#0b1220]" />
          Mandatory only
        </label>
      </div>
      <div className={clsx("grid", sections.length > 0 && "lg:grid-cols-[250px_minmax(0,1fr)]")}>
        {sections.length > 0 && (
          <nav className="max-h-[640px] overflow-y-auto border-b border-line py-2 lg:border-b-0 lg:border-r">
            <button onClick={() => setSection(null)} className={clsx("flex w-full items-center justify-between px-4 py-1.5 text-left text-[12.5px]",
              section === null ? "bg-[#f3f4f6] font-medium text-ink" : "text-ink-soft hover:bg-[#fafbfc]")}>
              <span>Whole document</span><span className="text-[11px] text-muted tnum">{report.items.length}</span>
            </button>
            {sections.map((s) => {
              const n = report.items.filter((i) => i.section && descendants(sections, s.id).has(i.section)).length;
              return (
                <button key={s.id} onClick={() => setSection(s.id)} title={s.title}
                  className={clsx("flex w-full items-center gap-2 py-1.5 pr-4 text-left text-[12px]",
                    section === s.id ? "bg-[#f3f4f6] font-medium text-ink" : "text-ink-soft hover:bg-[#fafbfc]")}
                  style={{ paddingLeft: 16 + Math.min(2, s.level - 1) * 14 }}>
                  <span className={clsx("size-1.5 shrink-0 rounded-full", KIND_DOT[s.kind] ?? "bg-slate-200")} title={KIND_LABEL[s.kind]} />
                  <span className="min-w-0 flex-1 truncate">{s.number && !s.title.startsWith(s.number) && !s.title.startsWith("Annex") ? `${s.number} ` : ""}{s.title}</span>
                  {s.page_start && <span className="text-[10.5px] text-subtle tnum">p{s.page_start}</span>}
                  {n > 0 && <span className="min-w-[18px] text-right text-[11px] text-muted tnum">{n}</span>}
                </button>
              );
            })}
          </nav>
        )}
        <div className="max-h-[640px] min-w-0 overflow-auto">
          {items.length === 0 ? <Empty title="No clauses match" description="Change the filters to see more of the matrix." /> : (
            <table className="table-base">
              <thead className="sticky top-0 z-10 bg-white"><tr><th className="w-[84px]">Clause</th><th>Requirement</th><th className="w-[170px]">Status</th><th className="w-[36%]">Response</th></tr></thead>
              <tbody>
                {items.map((i, rowIndex) => (
                  <MotionRow {...rowMotion(rowIndex)} key={i.id} className="cursor-pointer" onClick={() => onOpen(i)}>
                    <td className="align-top">
                      <div className="font-mono text-[11.5px] text-ink-soft">{i.clause ?? i.id}</div>
                      {i.page && !doc?.pages_estimated && <div className="text-[11px] text-subtle">p. {i.page}</div>}
                    </td>
                    <td className="align-top">
                      <div className="line-clamp-2 text-ink">{i.text}</div>
                      <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted">
                        <span>{CATEGORY_LABEL[i.category] ?? i.category}</span>
                        {i.modality !== "mandatory" && <span>· {i.modality}</span>}
                        {i.line_no && <span>· line {i.line_no}</span>}
                      </div>
                    </td>
                    <td className="align-top">
                      <div className="flex flex-wrap gap-1">
                        <Badge tone={STATUS_TONE[i.status]} dot>{i.status}</Badge>
                        {i.verify && <Badge tone="violet">Verify</Badge>}
                        {i.overridden && <Badge>Edited</Badge>}
                      </div>
                    </td>
                    <td className="align-top text-ink-soft"><div className="line-clamp-2">{i.response}</div></td>
                  </MotionRow>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------------------------------- risks and documents

function Risks({ report }: { report: ComplianceReport }) {
  return (
    <Card title="Risks to price in" subtitle="Contractual exposure and delivery obligations found in the tender" actions={<AlertTriangle className="size-4 text-subtle" />}>
      {report.risks.length === 0 ? <div className="text-[12.5px] text-muted">No material contractual risks found.</div> : (
        <ul className="space-y-3">
          {report.risks.map((r) => (
            <li key={r.title} className="flex gap-3">
              <span className={clsx("mt-1.5 size-2 shrink-0 rounded-full", r.severity === "high" ? "bg-rose-600" : r.severity === "medium" ? "bg-amber-500" : "bg-slate-300")} />
              <div className="min-w-0">
                <div className="text-[12.5px] font-medium text-ink">{r.title}
                  <span className="ml-2 text-[11px] font-normal text-muted">{r.severity}{r.clause && ` · clause ${r.clause}`}</span></div>
                <div className="text-[12px] text-ink-soft">{r.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Checklist({ report }: { report: ComplianceReport }) {
  const tally = (s: string) => report.checklist.filter((c) => c.status === s).length;
  return (
    <Card title="Bid documents" subtitle={`${tally("Ready")} ready · ${tally("To prepare")} to prepare · ${tally("To obtain")} to obtain from third parties`}
      actions={<ListChecks className="size-4 text-subtle" />} bodyClassName="p-0">
      {report.checklist.length === 0 ? <div className="px-5 py-4 text-[12.5px] text-muted">No supporting documents requested.</div> : (
        <ul className="max-h-[360px] divide-y divide-line overflow-y-auto">
          {report.checklist.map((c) => (
            <li key={c.name} className="flex items-start gap-3 px-5 py-2.5">
              <span className={clsx("mt-0.5 grid size-4 shrink-0 place-items-center rounded-full",
                c.status === "Ready" ? "bg-emerald-600 text-white" : c.status === "To obtain" ? "bg-rose-50 text-rose-700 ring-1 ring-rose-200" : "bg-[#eef0f3] text-muted")}>
                {c.status === "Ready" ? <Check className="size-2.5" strokeWidth={3} /> : <FileCheck2 className="size-2.5" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[12.5px] text-ink">{c.name}</div>
                {c.note && <div className="line-clamp-1 text-[11.5px] text-muted">{c.note}</div>}
              </div>
              <span className={clsx("whitespace-nowrap text-[11.5px]", c.status === "Ready" ? "text-emerald-700" : c.status === "To obtain" ? "text-rose-700" : "text-muted")}>{c.status}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- reviewer decisions

function useComplianceUpdate(rfpId: number, onDone: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof api.updateCompliance>[1]) => api.updateCompliance(rfpId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rfp", rfpId] });
      onDone();
    },
  });
}

function ItemSheet({ rfp, item, editable, onClose }: { rfp: RfpDetail; item: ComplianceItem; editable: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const [status, setStatus] = useState<ComplianceStatus>(item.status);
  const [response, setResponse] = useState(item.response);
  const save = useComplianceUpdate(rfp.id, onClose);
  const line = item.line_no ? rfp.pricing?.costing?.lines.find((l) => l.line_no === item.line_no) : undefined;
  const changed = status !== item.status || response !== item.response;
  return (
    <Sheet open onClose={onClose} width={620} title={`Clause ${item.clause ?? item.id}`}
      subtitle={[item.section_title, item.page && !rfp.parsed?.document?.pages_estimated ? `page ${item.page}` : null].filter(Boolean).join(" · ")}
      footer={editable ? (
        <div className="flex items-center justify-between gap-3">
          {item.overridden ? (
            <Button variant="ghost" icon={<RotateCcw className="size-3.5" />} loading={save.isPending && !changed}
              onClick={() => save.mutate({ clear: [item.id], actor: user?.name })}>Restore automatic assessment</Button>
          ) : <span className="text-[11.5px] text-muted">Saving re-runs compliance, pricing and documents.</span>}
          <div className="flex gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={!changed} loading={save.isPending && changed} icon={<Pencil className="size-3.5" />}
              onClick={() => save.mutate({ items: { [item.id]: { status, response } }, actor: user?.name, note: `Clause ${item.clause ?? item.id}: ${status}` })}>
              Save decision
            </Button>
          </div>
        </div>
      ) : undefined}>
      <div className="space-y-5">
        <blockquote className="rounded-lg border border-line bg-[#fafbfc] px-4 py-3 text-[13px] leading-[1.6] text-ink">{item.text}</blockquote>
        <dl className="grid grid-cols-3 gap-4 text-[12.5px]">
          <div><dt className="label">Category</dt><dd className="mt-1 text-ink">{CATEGORY_LABEL[item.category] ?? item.category}</dd></div>
          <div><dt className="label">Obligation</dt><dd className="mt-1 capitalize text-ink">{item.modality}</dd></div>
          <div><dt className="label">Assessed by</dt><dd className="mt-1 text-ink">{item.basis}</dd></div>
        </dl>
        {line && (
          <div className="rounded-lg border border-line px-4 py-3">
            <div className="label">Offered for line {line.line_no}</div>
            <div className="mt-1 text-[13px] font-medium text-ink">{line.name}</div>
            <div className="mt-0.5 text-[12px] text-muted">{line.sku} · {line.warranty_months} months warranty · lead time {line.lead_time_days} days
              {line.included_addons && line.included_addons.length > 0 && ` · includes ${line.included_addons.map((a) => a.name.toLowerCase()).join(", ")}`}</div>
          </div>
        )}
        <div>
          <div className="label mb-2">Automatic assessment</div>
          <div className="flex items-start gap-2">
            <Badge tone={STATUS_TONE[item.status]} dot>{item.status}</Badge>
            {item.verify && <Badge tone="violet">Verify before submission</Badge>}
          </div>
          <p className="mt-2 text-[13px] leading-[1.6] text-ink-soft">{item.response}</p>
        </div>
        {item.evidence.length > 0 && (
          <div>
            <div className="label mb-2">Supporting evidence</div>
            <ul className="space-y-2">
              {item.evidence.map((e, i) => (
                <li key={i} className="border-l-2 border-[#e8d3a6] pl-3">
                  <div className="text-[12.5px] leading-[1.55] text-ink-soft">“{e.text}”</div>
                  <div className="mt-0.5 text-[11px] text-muted">{e.section} · {e.source} · relevance {Math.round(e.score * 100)}%</div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {editable && (
          <div className="space-y-3 border-t border-line pt-5">
            <div className="label">Your decision</div>
            <div className="flex flex-wrap gap-1.5">
              {STATUSES.map((s) => (
                <button key={s} onClick={() => setStatus(s)} className={clsx("rounded-full px-2.5 py-1 text-[12px] ring-1 ring-inset transition",
                  status === s ? "bg-ink text-white ring-ink" : "bg-white text-ink-soft ring-line-strong hover:bg-[#fafbfc]")}>{s}</button>
              ))}
            </div>
            <Field label="Response shown in the compliance statement">
              <textarea value={response} onChange={(e) => setResponse(e.target.value)} rows={4} className="input h-auto py-2 text-[13px] leading-[1.55]" />
            </Field>
          </div>
        )}
      </div>
    </Sheet>
  );
}

function CheckSheet({ rfp, check, editable, onClose }: { rfp: RfpDetail; check: EligibilityCheck; editable: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const [status, setStatus] = useState<EligibilityStatus>(check.status);
  const [position, setPosition] = useState(check.position);
  const save = useComplianceUpdate(rfp.id, onClose);
  const changed = status !== check.status || position !== check.position;
  return (
    <Sheet open onClose={onClose} width={580} title={check.label} subtitle={[check.clause && `Clause ${check.clause}`, check.page && `page ${check.page}`].filter(Boolean).join(" · ")}
      footer={editable ? (
        <div className="flex items-center justify-between gap-3">
          {check.overridden ? (
            <Button variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => save.mutate({ clear: [check.id], actor: user?.name })}>Restore automatic check</Button>
          ) : <span className="text-[11.5px] text-muted">A reviewer decision replaces the automatic check.</span>}
          <div className="flex gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={!changed} loading={save.isPending}
              onClick={() => save.mutate({ eligibility: { [check.id]: { status, position } }, actor: user?.name, note: `${check.label}: ${status}` })}>Save decision</Button>
          </div>
        </div>
      ) : undefined}>
      <div className="space-y-5">
        <blockquote className="rounded-lg border border-line bg-[#fafbfc] px-4 py-3 text-[13px] leading-[1.6] text-ink">{check.text}</blockquote>
        <div>
          <div className="label mb-2">Automatic check</div>
          <Badge tone={ELIGIBILITY_TONE[check.status]} dot>{check.status}</Badge>
          <p className="mt-2 text-[13px] leading-[1.6] text-ink-soft">{check.position}</p>
          {check.evidence.length > 0 && (
            <ul className="mt-2 space-y-1 text-[12px] text-muted">{check.evidence.map((e) => <li key={e}>· {e}</li>)}</ul>
          )}
          {check.documents && <div className="mt-3 text-[12px] text-ink-soft"><span className="text-muted">Documents requested:</span> {check.documents}</div>}
        </div>
        {editable && (
          <div className="space-y-3 border-t border-line pt-5">
            <div className="label">Your decision</div>
            <div className="flex flex-wrap gap-1.5">
              {ELIGIBILITY_STATUSES.map((s) => (
                <button key={s} onClick={() => setStatus(s)} className={clsx("rounded-full px-2.5 py-1 text-[12px] ring-1 ring-inset transition",
                  status === s ? "bg-ink text-white ring-ink" : "bg-white text-ink-soft ring-line-strong hover:bg-[#fafbfc]")}>{s}</button>
              ))}
            </div>
            <Field label="Our position">
              <textarea value={position} onChange={(e) => setPosition(e.target.value)} rows={3} className="input h-auto py-2 text-[13px] leading-[1.55]" />
            </Field>
          </div>
        )}
      </div>
    </Sheet>
  );
}
