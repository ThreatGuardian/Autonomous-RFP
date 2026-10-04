import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, CheckCircle2, ChevronDown, Download, ExternalLink, FileArchive, FileCheck2, FileText, Flag, PenLine, RotateCcw, Trash2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CountryTag, StageTracker, StatusBadge } from "../../components/domain";
import { Page, PageHeader } from "../../components/layout/Shell";
import { Badge, Button, Card, Dialog, Empty, Field, Segmented, Skeleton, Spinner, Tabs } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api } from "../../lib/api";
import type { RfpDetail } from "../../lib/types";
import { date, daysUntil, getBaseCurrency, money } from "../../lib/format";
import { ActivityTab } from "./ActivityTab";
import { ComplianceTab } from "./ComplianceTab";
import { PricingTab } from "./PricingTab";
import { QuotationTab } from "./QuotationTab";
import { RequirementsTab } from "./RequirementsTab";

type Tab = "pricing" | "compliance" | "requirements" | "quotation" | "activity" | "source";

export default function RequestDetail() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("pricing");
  const [stageFocus, setStageFocus] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | "approve" | "reject" | "reopen" | "delete">(null);
  const { user } = useAuth();
  const [actor, setActor] = useState(user?.name ?? "Reviewer");
  const [note, setNote] = useState("");

  const { data: rfp, isLoading, error } = useQuery({
    queryKey: ["rfp", id],
    queryFn: () => api.rfp(id),
    refetchInterval: (q) => {
      const d = q.state.data as RfpDetail | undefined;
      return !d || d.running || d.status === "queued" || d.status === "processing" ? 900 : false;
    },
  });

  const act = useMutation({
    mutationFn: async (kind: "approve" | "reject" | "reopen" | "delete" | "retry") => {
      if (kind === "approve") return api.approve(id, actor, note || undefined);
      if (kind === "reject") return api.reject(id, actor, note || undefined);
      if (kind === "reopen") return api.reopen(id, actor, note || undefined);
      if (kind === "retry") return api.retry(id);
      return api.remove(id);
    },
    onSuccess: (_d, kind) => {
      setDialog(null);
      setNote("");
      qc.invalidateQueries({ queryKey: ["rfps"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (kind === "delete") navigate("/app/requests");
      else qc.invalidateQueries({ queryKey: ["rfp", id] });
    },
  });

  if (isLoading) return <Page><Skeleton className="mb-4 h-16" /><Skeleton className="h-72" /></Page>;
  if (error || !rfp) return <Page><Empty title="Request not found" description="It may have been deleted." action={<Link to="/app/requests"><Button>Back to requests</Button></Link>} /></Page>;

  const busy = rfp.running || rfp.status === "queued" || rfp.status === "processing";
  const ready = !!rfp.pricing?.strategy && !!rfp.proposal && !busy;
  const editable = rfp.status === "review" && !busy;
  const days = daysUntil(rfp.due_date);
  const loc = rfp.pricing?.localisation;
  const docs = rfp.proposal?.documents ?? {};

  return (
    <>
      <PageHeader
        breadcrumb={<><Link to="/app/requests" className="hover:text-ink">Requests</Link> / <span className="font-mono">{rfp.reference}</span></>}
        title={rfp.parsed?.title ?? rfp.title}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <StatusBadge status={rfp.status} />
            <span className="text-ink-soft">{rfp.client_name ?? "Client not yet identified"}</span>
            {rfp.client_country && <CountryTag code={rfp.client_country} />}
            {rfp.due_date && <span>Due {date(rfp.due_date)}{days !== null && days >= 0 && ` · ${days} days left`}</span>}
            {loc && <span className="font-medium text-ink tnum">{money(loc.grand_total, loc.currency, { decimals: loc.decimals })}</span>}
          </span>
        }
        actions={
          <>
            {docs.report && <Link to={`/app/requests/${id}/report`}><Button icon={<PenLine className="size-4" />}>Edit report</Button></Link>}
            <DocumentsMenu id={id} docs={docs} compliance={!!rfp.parsed?.document?.long_form} pack={ready} />
            {ready && (rfp.status === "approved" || rfp.status === "review") && <OutcomeControl id={id} actor={actor} currency={loc?.currency ?? getBaseCurrency()} />}
            {rfp.status === "review" && !busy && <>
              <Button variant="danger" icon={<XCircle className="size-4" />} onClick={() => setDialog("reject")}>Decline</Button>
              <Button variant="success" icon={<CheckCircle2 className="size-4" />} onClick={() => setDialog("approve")}>Approve quotation</Button>
            </>}
            {(rfp.status === "approved" || rfp.status === "rejected") && <Button icon={<RotateCcw className="size-4" />} onClick={() => setDialog("reopen")}>Reopen</Button>}
            {rfp.status === "failed" && <Button variant="primary" icon={<RotateCcw className="size-4" />} loading={act.isPending} onClick={() => act.mutate("retry")}>Retry</Button>}
            {!busy && <Button variant="ghost" aria-label="Delete" onClick={() => setDialog("delete")}><Trash2 className="size-4" /></Button>}
          </>
        }
      />
      <Page className="space-y-5">
        <StageTracker order={rfp.stage_order} stages={rfp.stages} active={stageFocus}
          onSelect={(s) => { setStageFocus(s); setTab("activity"); }} />

        {rfp.status === "failed" && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-5 py-4 text-[13px] text-rose-900">
            <div className="font-semibold">Processing stopped</div><div className="mt-1">{rfp.error}</div>
          </div>
        )}
        {rfp.status === "approved" && (
          <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-[13px] text-emerald-900">
            <CheckCircle2 className="size-4" /> Approved — the final quotation has been issued without the draft watermark and is ready to send.
          </div>
        )}

        {!ready && busy ? (
          <Card>
            <div className="flex flex-col items-center py-12 text-center">
              <Spinner className="size-6 text-ink" />
              <div className="mt-4 text-[14px] font-semibold">Preparing the quotation</div>
              <div className="mt-1 max-w-md text-[12.5px] text-muted">Reading the request, checking cost and stock, gathering competitor prices and drafting documents. This usually takes a few seconds.</div>
            </div>
          </Card>
        ) : !ready ? (
          <Card><Empty title="No pricing available" description="Processing did not complete for this request." /></Card>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <Tabs value={tab} onChange={setTab} items={[
                { value: "pricing", label: "Pricing" },
                ...(rfp.compliance ? [{ value: "compliance" as Tab, label: "Compliance", count: (rfp.compliance.counts["Deviation"] ?? 0) + (rfp.compliance.counts["Clarification required"] ?? 0) || undefined }] : []),
                { value: "requirements", label: "Requirements", count: rfp.parsed?.requirements.filter((r) => r.type !== "scope").length },
                { value: "quotation", label: "Quotation" },
                { value: "activity", label: "Activity" },
                { value: "source", label: "Source document" },
              ]} />
              {busy && <span className="flex items-center gap-2 text-[12.5px] text-muted"><Spinner className="size-3.5" /> Re-pricing…</span>}
            </div>
            {tab === "pricing" && <PricingTab rfp={rfp} editable={editable} />}
            {tab === "compliance" && <ComplianceTab rfp={rfp} editable={editable} />}
            {tab === "requirements" && <RequirementsTab rfp={rfp} />}
            {tab === "quotation" && <QuotationTab rfp={rfp} editable={editable} />}
            {tab === "activity" && <ActivityTab rfp={rfp} focus={stageFocus} />}
            {tab === "source" && (
              <Card title={rfp.source_filename ?? "Pasted text"}
                subtitle={`${rfp.raw_text.length.toLocaleString()} characters${rfp.parsed?.document ? ` · ${rfp.parsed.document.pages} ${rfp.parsed.document.pages_estimated ? "estimated " : ""}page(s)` : ""}`}
                actions={rfp.has_original ? <a href={api.originalUrl(id)} target="_blank" rel="noreferrer"><Button size="sm" icon={<ExternalLink className="size-3.5" />}>Open original</Button></a> : undefined}>
                <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap font-mono text-[12px] leading-[1.65] text-ink-soft">{rfp.raw_text}</pre>
              </Card>
            )}
          </>
        )}
      </Page>

      <Dialog open={dialog === "approve" || dialog === "reject" || dialog === "reopen"} onClose={() => setDialog(null)}
        title={dialog === "approve" ? "Approve quotation" : dialog === "reject" ? "Decline to bid" : "Reopen for review"}
        footer={<>
          <Button onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant={dialog === "approve" ? "success" : dialog === "reject" ? "danger" : "primary"} loading={act.isPending}
            onClick={() => act.mutate(dialog as "approve" | "reject" | "reopen")}>
            {dialog === "approve" ? "Approve and issue" : dialog === "reject" ? "Decline" : "Reopen"}
          </Button>
        </>}>
        <div className="space-y-4">
          {dialog === "approve" && loc && (
            <p className="text-[12.5px] text-muted">The final quotation for <span className="font-medium text-ink">{money(loc.grand_total, loc.currency, { decimals: loc.decimals })}</span> will be issued without the draft watermark, and the approval will be recorded in the pricing memo.</p>
          )}
          <Field label="Your name"><input className="input" value={actor} onChange={(e) => setActor(e.target.value)} /></Field>
          <Field label={dialog === "reject" ? "Reason" : "Note (optional)"}>
            <textarea className="input h-20 resize-none py-2" value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          {act.isError && <div className="text-[12.5px] text-rose-700">{(act.error as Error).message}</div>}
        </div>
      </Dialog>
      <Dialog open={dialog === "delete"} onClose={() => setDialog(null)} title="Delete request"
        footer={<><Button onClick={() => setDialog(null)}>Cancel</Button><Button variant="danger" loading={act.isPending} onClick={() => act.mutate("delete")}>Delete</Button></>}>
        <p className="text-[13px] text-ink-soft">This permanently removes {rfp.reference}, its pricing history and review record.</p>
      </Dialog>
    </>
  );
}

const DOCUMENTS = [
  { kind: "quotation", label: "Quotation", hint: "Client-facing offer with line items and taxes", icon: Download },
  { kind: "compliance", label: "Compliance statement", hint: "Clause-by-clause answers and deviations", icon: FileCheck2 },
  { kind: "report", label: "Bid report", hint: "Recommendation, win odds and risks", icon: BarChart3 },
  { kind: "memo", label: "Pricing memo", hint: "Internal: costs, margins and rationale", icon: FileText },
] as const;

function DocumentsMenu({ id, docs, compliance, pack }: { id: number; docs: Record<string, string | undefined>; compliance: boolean; pack: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const available = DOCUMENTS.filter((d) => docs[d.kind] && (d.kind !== "compliance" || compliance));
  if (!available.length) return null;
  return (
    <div ref={ref} className="relative">
      <Button icon={<Download className="size-4" />} onClick={() => setOpen(!open)}>
        Documents <ChevronDown className={`size-3.5 text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </Button>
      {open && (
        <div className="animate-fade-in absolute right-0 top-full z-30 mt-2 w-[300px] overflow-hidden rounded-xl border border-line bg-white py-1 shadow-[var(--shadow-pop)]">
          {available.map((d) => (
            <a key={d.kind} href={api.documentUrl(id, d.kind)} target="_blank" rel="noreferrer" onClick={() => setOpen(false)}
              className="flex items-start gap-3 px-3.5 py-2.5 hover:bg-[#f6f7f9]">
              <d.icon className="mt-0.5 size-4 shrink-0 text-ink-soft" />
              <span className="min-w-0">
                <span className="block text-[13px] font-medium text-ink">{d.label}</span>
                <span className="block text-[11.5px] text-muted">{d.hint}</span>
              </span>
            </a>
          ))}
          {pack && (
            <a href={api.packUrl(id)} onClick={() => setOpen(false)}
              className="flex items-start gap-3 border-t border-line px-3.5 py-2.5 hover:bg-[#f6f7f9]">
              <FileArchive className="mt-0.5 size-4 shrink-0 text-ink-soft" />
              <span className="min-w-0">
                <span className="block text-[13px] font-medium text-ink">Submission pack (.zip)</span>
                <span className="block text-[11.5px] text-muted">Technical proposal, forms, compliance, financial bid and OEM letters</span>
              </span>
            </a>
          )}
        </div>
      )}
    </div>
  );
}

const RESULT_LABEL = { won: "Won", lost: "Lost", cancelled: "Cancelled" } as const;

function OutcomeControl({ id, actor, currency }: { id: number; actor: string; currency: string }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["outcome", id], queryFn: () => api.outcome(id) });
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<"won" | "lost" | "cancelled">("won");
  const [total, setTotal] = useState("");
  const [winner, setWinner] = useState("");
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () => api.setOutcome(id, { result, winning_total: total ? Number(total) : undefined, winner: winner || undefined, note: note || undefined, actor }),
    onSuccess: () => { setOpen(false); qc.invalidateQueries({ queryKey: ["outcome", id] }); qc.invalidateQueries({ queryKey: ["rfp", id] }); },
  });
  const o = data?.outcome;
  const start = () => {
    setResult(o?.result ?? "won"); setTotal(o?.winning_total ? String(o.winning_total) : ""); setWinner(o?.winner ?? ""); setNote(o?.note ?? "");
    setOpen(true);
  };
  return (
    <>
      {o ? (
        <button onClick={start} title="Change the recorded outcome">
          <Badge tone={o.result === "won" ? "green" : o.result === "lost" ? "red" : "neutral"} dot>
            {RESULT_LABEL[o.result]}{o.result === "lost" && o.winner ? ` to ${o.winner}` : ""}
          </Badge>
        </button>
      ) : (
        <Button icon={<Flag className="size-4" />} onClick={start}>Record outcome</Button>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} title="Bid outcome"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save outcome</Button></>}>
        <div className="space-y-4">
          <p className="text-[12.5px] leading-relaxed text-muted">Real outcomes teach the win-probability model how buyers in your market actually decide. The winning price is optional but makes the lesson sharper.</p>
          <Segmented value={result} onChange={setResult} items={[{ value: "won", label: "Won" }, { value: "lost", label: "Lost" }, { value: "cancelled", label: "Cancelled" }]} />
          {result === "lost" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={`Winning total (${currency}, before tax)`}><input className="input tnum" type="number" min={0} value={total} onChange={(e) => setTotal(e.target.value)} /></Field>
              <Field label="Winner"><input className="input" value={winner} onChange={(e) => setWinner(e.target.value)} placeholder="e.g. Shree Sai Computers" /></Field>
            </div>
          )}
          <Field label="Note (optional)"><textarea className="input h-16 resize-none py-2" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          {save.isError && <div className="text-[12.5px] text-rose-700">{(save.error as Error).message}</div>}
        </div>
      </Dialog>
    </>
  );
}
