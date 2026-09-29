import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileText, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Page, PageHeader } from "../components/layout/Shell";
import { Button, Card, Segmented } from "../components/ui";
import { api } from "../lib/api";

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

  const submit = useMutation({
    mutationFn: async () => {
      if (mode === "paste") return [await api.createRfp(text)];
      return api.uploadRfps(files);
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["rfps"] });
      navigate(created.length === 1 ? `/requests/${created[0].id}` : "/requests?status=active");
    },
    onError: (e: Error) => setError(e.message),
  });

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    setError(null);
    setFiles((prev) => [...prev, ...Array.from(list)].slice(0, 12));
  };
  const canSubmit = mode === "paste" ? text.trim().length >= 40 : files.length > 0;

  return (
    <>
      <PageHeader title="New request" breadcrumb="Requests / New"
        description="Upload the client's request for proposal or paste its text. Parsing, costing, market analysis and drafting start immediately." />
      <Page className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card title="Request document" actions={
          <Segmented value={mode} onChange={(v) => { setMode(v); setError(null); }} items={[{ value: "upload", label: "Upload files" }, { value: "paste", label: "Paste text" }]} />
        }>
          {mode === "upload" ? (
            <>
              <div
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
                onClick={() => input.current?.click()}
                className={clsx("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors",
                  drag ? "border-ink/40 bg-[#f6f7f9]" : "border-line-strong hover:bg-[#fafbfc]")}
              >
                <div className="grid size-11 place-items-center rounded-full bg-[#f1f2f4] text-ink-soft"><UploadCloud className="size-5" /></div>
                <div className="mt-3 text-[14px] font-medium">Drop files here or <span className="text-link">browse</span></div>
                <div className="mt-1 text-[12.5px] text-muted">PDF, Word (.docx) or plain text, up to 10 MB each. Several files are processed in parallel.</div>
                <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => addFiles(e.target.files)} />
              </div>
              {files.length > 0 && (
                <ul className="mt-4 divide-y divide-line rounded-xl border border-line">
                  {files.map((f, i) => (
                    <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                      <FileText className="size-4 text-muted" />
                      <span className="flex-1 truncate">{f.name}</span>
                      <span className="text-[12px] text-muted tnum">{(f.size / 1024).toFixed(0)} KB</span>
                      <button className="rounded p-1 text-muted hover:bg-black/5" onClick={() => setFiles(files.filter((_, j) => j !== i))}><X className="size-3.5" /></button>
                    </li>
                  ))}
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

        <div className="space-y-6">
          <Card title="Sample requests" subtitle="Realistic requests for trying the workflow" bodyClassName="p-0">
            <ul className="divide-y divide-line">
              {(samples.data ?? []).map((s) => (
                <li key={s.filename}>
                  <button className="w-full px-5 py-3 text-left hover:bg-[#fafbfc]" onClick={() => { setMode("paste"); setText(s.text); setError(null); }}>
                    <div className="truncate text-[13px] font-medium">{s.title}</div>
                    <div className="truncate text-[11.5px] text-muted">{s.filename}</div>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="What happens next">
            <ol className="space-y-3 text-[12.5px] text-ink-soft">
              {[
                ["Intake", "Client, location, currency, deadlines, terms and every requested item are extracted and matched to the catalogue."],
                ["Costing", "Landed cost, margin floor, volume tier, stock and lead time are read from the pricing database."],
                ["Market & strategy", "Competitor prices are gathered and each line is priced to maximise expected profit within policy."],
                ["Currency & tax", "The quote is converted to the client's currency and the correct regional tax treatment is applied."],
                ["Drafting", "A branded quotation and an internal pricing memo are produced for your review."],
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
