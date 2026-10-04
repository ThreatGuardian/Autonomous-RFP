import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileText, UploadCloud, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Page, PageHeader } from "../components/layout/Shell";
import { Button, Card, Segmented } from "../components/ui";
import { RegionPicker } from "../components/RegionPicker";
import { api, type ClientRegion } from "../lib/api";

const ACCEPT = ".pdf,.docx,.txt,.md";

export default function NewRequest() {
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samples });
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const [region, setRegion] = useState<ClientRegion | null>(null);
  // Start from the workspace's own country; the user confirms or changes it for each request.
  useEffect(() => {
    if (!region && workspace.data) setRegion({ country: workspace.data.operating_region.country, region: null });
  }, [workspace.data, region]);

  const sample = useMutation({
    mutationFn: (filename: string) => api.processSample(filename, region!),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["rfps"] });
      navigate(`/app/requests/${created[0].id}`);
    },
    onError: (e: Error) => setError(e.message),
  });

  const submit = useMutation({
    mutationFn: async () => {
      if (mode === "paste") return [await api.createRfp(text, region!)];
      return api.uploadRfps(files, region!);
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["rfps"] });
      navigate(created.length === 1 ? `/app/requests/${created[0].id}` : "/app/requests?status=active");
    },
    onError: (e: Error) => setError(e.message),
  });

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    setError(null);
    setFiles((prev) => [...prev, ...Array.from(list)].slice(0, 12));
  };
  const canSubmit = Boolean(region?.country) && (mode === "paste" ? text.trim().length >= 40 : files.length > 0);

  return (
    <>
      <PageHeader title="New request" breadcrumb="Requests / New"
        description="Upload the client's request for proposal or paste its text. Parsing, costing, market analysis and drafting start immediately." />
      <Page className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <Card title="Client region" subtitle="Sets the quotation currency, the tax treatment and the regional rules that apply">
            <RegionPicker value={region} onChange={setRegion} />
          </Card>
          <Card title="Request document" actions={
            <Segmented value={mode} onChange={(v) => { setMode(v); setError(null); }} items={[{ value: "upload", label: "Upload files" }, { value: "paste", label: "Paste text" }]} />
          }>
            {mode === "upload" ? (
              <>
                <motion.div animate={{ scale: drag ? 1.01 : 1 }} transition={{ type: "spring", stiffness: 400, damping: 28 }}
                  onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
                  onClick={() => input.current?.click()}
                  className={clsx("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors",
                    drag ? "border-ink/40 bg-[#f6f7f9]" : "border-line-strong hover:bg-[#fafbfc]")}
                >
                  <motion.div animate={{ y: drag ? -4 : 0 }} transition={{ type: "spring", stiffness: 500, damping: 20 }}
                    className="grid size-11 place-items-center rounded-full bg-[#f1f2f4] text-ink-soft"><UploadCloud className="size-5" /></motion.div>
                  <div className="mt-3 text-[14px] font-medium">Drop files here or <span className="text-link">browse</span></div>
                  <div className="mt-1 text-[12.5px] text-muted">PDF, Word (.docx) or plain text, up to 10 MB each. Several files are processed in parallel.</div>
                  <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => addFiles(e.target.files)} />
                </motion.div>
                {files.length > 0 && (
                  <ul className="mt-4 divide-y divide-line overflow-hidden rounded-xl border border-line">
                    <AnimatePresence initial={false}>
                    {files.map((f, i) => (
                      <motion.li key={`${f.name}-${f.size}-${f.lastModified}`} layout initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.22 }}
                        className="flex items-center gap-3 px-4 py-2.5">
                        <FileText className="size-4 text-muted" />
                        <span className="flex-1 truncate">{f.name}</span>
                        <span className="text-[12px] text-muted tnum">{(f.size / 1024).toFixed(0)} KB</span>
                        <button className="rounded p-1 text-muted hover:bg-black/5" onClick={() => setFiles(files.filter((_, j) => j !== i))}><X className="size-3.5" /></button>
                      </motion.li>
                    ))}
                    </AnimatePresence>
                  </ul>
                )}
              </>
            ) : (
              <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full text of the request, including the schedule of items, delivery and commercial terms…"
                className="input h-[420px] resize-y py-3 font-mono text-[12.5px] leading-[1.6]" />
            )}
            {error && <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12.5px] text-rose-800">{error}</div>}
            <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
              <div className="text-[12px] text-muted">{mode === "paste" ? `${text.length.toLocaleString()} characters` : `${files.length} file(s) selected`}</div>
              <Button variant="primary" disabled={!canSubmit} loading={submit.isPending} onClick={() => submit.mutate()}>
                {mode === "upload" && files.length > 1 ? `Process ${files.length} requests` : "Process request"}
              </Button>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Sample requests" subtitle="Realistic requests for trying the workflow" bodyClassName="p-0">
            <ul className="divide-y divide-line">
              {(samples.data ?? []).map((s, i) => (
                <motion.li key={s.filename} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: Math.min(i, 10) * 0.035 }}>
                  {s.kind === "file" ? (
                    <button className="group flex w-full items-start gap-3 px-5 py-3 text-left transition-colors hover:bg-[#fafbfc] disabled:opacity-60" disabled={sample.isPending || !region}
                      onClick={() => { setError(null); sample.mutate(s.filename); }}>
                      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-accent-soft text-[9.5px] font-bold text-[#8a5a0b] transition-transform duration-200 group-hover:-rotate-6 group-hover:scale-110">{s.format}</span>
                      <span className="min-w-0">
                        <span className="line-clamp-2 text-[13px] font-medium">{s.title}</span>
                        <span className="block truncate text-[11.5px] text-muted">{s.pages} pages · full tender · processes immediately</span>
                      </span>
                    </button>
                  ) : (
                    <button className="w-full px-5 py-3 text-left hover:bg-[#fafbfc]" onClick={() => { setMode("paste"); setText(s.text); setError(null); }}>
                      <div className="truncate text-[13px] font-medium">{s.title}</div>
                      <div className="truncate text-[11.5px] text-muted">{s.filename}</div>
                    </button>
                  )}
                </motion.li>
              ))}
            </ul>
          </Card>
          <Card title="What happens next">
            <ol className="space-y-3 text-[12.5px] text-ink-soft">
              {[
                ["Intake", "Client, location, currency, deadlines, terms and every requested item are extracted and matched to the catalogue."],
                ["Costing", "Landed cost, margin floor, volume tier, stock and lead time are read from the pricing database."],
                ["Compliance", "Long tenders are split into sections; eligibility, specifications and terms are checked clause by clause."],
                ["Market & strategy", "Competitor prices are gathered and each line is priced to maximise expected profit within policy."],
                ["Currency & tax", "The quote is converted to the selected region's currency and its tax treatment is applied."],
                ["Drafting", "A branded quotation, pricing memo, bid report and compliance statement are produced for your review."],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-[#eef0f3] text-[11px] font-semibold text-ink-soft">{i + 1}</span>
                  <span><span className="font-medium text-ink">{t}.</span> {d}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </Page>
    </>
  );
}
