import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AnimatePresence, motion, Reorder, useDragControls } from "motion/react";
import {
  ArrowLeft, ArrowUp, Check, ChevronDown, CloudCheck, Eye, EyeOff, FileDown, FileText, GripVertical, ListPlus, Loader2,
  MessageSquareText, Plus, Redo2, RefreshCw, RotateCcw, Trash2, Undo2,
} from "lucide-react";
import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EASE } from "../../components/motion";
import { Button, Spinner } from "../../components/ui";
import { type ChatMessage, report, type ReportBlock, type ReportDocument, type ReportSection } from "../../lib/api";
import { relative } from "../../lib/format";

const uid = () => Math.random().toString(16).slice(2, 10);
type SaveState = "saved" | "dirty" | "saving" | "error";

export default function ReportEditor() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["report", id], queryFn: () => report.get(id) });
  const [doc, setDoc] = useState<ReportDocument | null>(null);
  const [save, setSave] = useState<SaveState>("saved");
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [version, setVersion] = useState(0); // bumps when the server replaces the document, re-seeding editable text
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef<ReportDocument | null>(null);

  useEffect(() => { if (data && !doc) { setDoc(data); latest.current = data; } }, [data, doc]);

  const persist = useCallback(async () => {
    window.clearTimeout(timer.current);
    const d = latest.current;
    if (!d) return;
    setSave("saving");
    try {
      const saved = await report.save(id, { title: d.title, sections: d.sections });
      setDoc((cur) => (cur ? { ...cur, can_undo: saved.can_undo, can_redo: saved.can_redo, updated_at: saved.updated_at, edited: true } : cur));
      setSave("saved");
    } catch {
      setSave("error");
    }
  }, [id]);

  const update = useCallback((fn: (d: ReportDocument) => ReportDocument) => {
    setDoc((cur) => {
      if (!cur) return cur;
      const next = fn(structuredClone(cur));
      latest.current = next;
      return next;
    });
    setSave("dirty");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(persist, 900);
  }, [persist]);

  const replace = useCallback((next: ReportDocument, changed?: string[]) => {
    latest.current = next;
    setDoc(next);
    setVersion((v) => v + 1);
    qc.setQueryData(["report", id], next);
    if (changed?.length) {
      setFlash(new Set(changed));
      window.setTimeout(() => setFlash(new Set()), 1900);
      const first = document.getElementById(`blk-${changed[0]}`) ?? document.getElementById(`sec-${changed[0]}`);
      first?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [id, qc]);

  const step = useMutation({
    mutationFn: async (kind: "undo" | "redo" | "reset") => {
      if (save === "dirty") await persist();
      return kind === "undo" ? report.undo(id) : kind === "redo" ? report.redo(id) : report.reset(id);
    },
    onSuccess: (d) => replace(d),
  });

  if (isLoading || !doc) {
    return <div className="grid h-screen place-items-center bg-canvas">{error ? <div className="text-[13px] text-muted">{(error as Error).message}</div> : <Spinner className="size-5 text-muted" />}</div>;
  }

  return (
    <div className="flex h-screen flex-col bg-[#f3f1ec]">
      <TopBar id={id} doc={doc} save={save} busy={step.isPending} onStep={(k) => step.mutate(k)} onFlush={persist} />
      {doc.stale && (
        <div className="flex items-center justify-center gap-3 border-b border-amber-200 bg-[#fff8ea] px-4 py-2 text-[12.5px] text-[#7a4a00]">
          Prices or compliance have changed since this report was edited.
          <button className="font-semibold underline-offset-2 hover:underline" onClick={() => document.dispatchEvent(new CustomEvent("assistant:send", { detail: "refresh everything" }))}>
            Refresh the generated sections
          </button>
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-[250px_minmax(0,1fr)_380px]">
        <Outline doc={doc} update={update} />
        <main className="min-h-0 overflow-y-auto px-10 py-10" id="canvas">
          <motion.article initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE }}
            className="mx-auto max-w-[780px] rounded-[18px] bg-white px-16 pb-16 pt-14 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_24px_60px_-24px_rgb(60_40_10/0.25)] ring-1 ring-[#ece6d9]">
            <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.28em] text-[#b8862b]">
              <span className="size-2 rotate-45 bg-[#b8862b]" /> Bid analysis · {doc.quote_number}
            </div>
            <Editable key={`title-${version}`} as="h1" value={doc.title} placeholder="Report title"
              className="editable mt-5 -mx-2 px-2 font-serif text-[38px] font-semibold leading-[1.12] tracking-[-0.01em] text-[#1e2a36]"
              onCommit={(v) => update((d) => ({ ...d, title: v }))} />
            <div className="mt-3 text-[12.5px] text-[#8a7e6b]">{doc.subtitle}</div>
            <div className="mt-8 h-px bg-[#efe3cb]" />
            {doc.sections.map((s) => (
              <SectionView key={`${s.id}-${version}`} section={s} flash={flash} update={update} />
            ))}
            <AddSection update={update} />
          </motion.article>
          <div className="h-16" />
        </main>
        <Assistant id={id} doc={doc} beforeSend={async () => { if (latest.current && save !== "saved") await persist(); }} onReply={replace} />
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------- top bar

function TopBar({ id, doc, save, busy, onStep, onFlush }: {
  id: number; doc: ReportDocument; save: SaveState; busy: boolean; onStep: (k: "undo" | "redo" | "reset") => void; onFlush: () => Promise<void>;
}) {
  const [menu, setMenu] = useState(false);
  const exportAs = async (format: "pdf" | "docx") => {
    await onFlush();
    window.open(report.exportUrl(id, format), "_blank");
  };
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-[#e8e2d4] bg-white/80 px-4 backdrop-blur">
      <Link to={`/app/requests/${id}`} className="grid size-8 place-items-center rounded-lg text-ink-soft transition hover:bg-black/[0.05]" aria-label="Back to request">
        <ArrowLeft className="size-4" />
      </Link>
      <div className="min-w-0">
        <div className="truncate text-[13.5px] font-semibold text-ink">{doc.title}</div>
        <div className="flex items-center gap-1.5 text-[11.5px] text-muted">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={save} initial={{ opacity: 0, y: 3 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -3 }}
              transition={{ duration: 0.18 }} className="inline-flex items-center gap-1">
              {save === "saving" ? <><Loader2 className="size-3 animate-spin" /> Saving…</>
                : save === "dirty" ? <>Unsaved changes</>
                : save === "error" ? <span className="text-rose-700">Couldn't save — retrying on next edit</span>
                : <><CloudCheck className="size-3.5" /> {doc.edited ? `Saved ${relative(doc.updated_at)}` : "Generated from the latest pricing"}</>}
            </motion.span>
          </AnimatePresence>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        <IconButton label="Undo" disabled={!doc.can_undo || busy} onClick={() => onStep("undo")}><Undo2 className="size-4" /></IconButton>
        <IconButton label="Redo" disabled={!doc.can_redo || busy} onClick={() => onStep("redo")}><Redo2 className="size-4" /></IconButton>
        <div className="relative">
          <IconButton label="More" onClick={() => setMenu(!menu)}><ChevronDown className="size-4" /></IconButton>
          <AnimatePresence>
            {menu && (
              <motion.div initial={{ opacity: 0, y: -4, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4, scale: 0.98 }}
                transition={{ duration: 0.16 }} className="absolute right-0 top-full z-40 mt-2 w-[260px] rounded-xl border border-line bg-white p-1 shadow-[var(--shadow-pop)]">
                <button onClick={() => { setMenu(false); if (confirm("Replace the report with a freshly generated version? You can undo this.")) onStep("reset"); }}
                  className="flex w-full items-start gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-[#f6f7f9]">
                  <RotateCcw className="mt-0.5 size-4 text-ink-soft" />
                  <span><span className="block text-[12.5px] font-medium">Regenerate report</span><span className="block text-[11.5px] text-muted">Start again from the latest figures</span></span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <div className="mx-2 h-6 w-px bg-line" />
        <Button icon={<FileText className="size-4" />} onClick={() => exportAs("docx")}>Word</Button>
        <Button variant="primary" icon={<FileDown className="size-4" />} onClick={() => exportAs("pdf")}>Export PDF</Button>
      </div>
    </header>
  );
}

function IconButton({ label, children, ...rest }: { label: string; children: React.ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...rest} aria-label={label} title={label}
      className="grid size-8 place-items-center rounded-lg text-ink-soft transition hover:bg-black/[0.05] disabled:opacity-35 disabled:hover:bg-transparent">
      {children}
    </button>
  );
}

// ----------------------------------------------------------------------------- outline

function Outline({ doc, update }: { doc: ReportDocument; update: (fn: (d: ReportDocument) => ReportDocument) => void }) {
  return (
    <aside className="min-h-0 overflow-y-auto border-r border-[#e8e2d4] bg-[#faf8f4] px-3 py-5">
      <div className="px-2 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#8a7e6b]">Outline</div>
      <Reorder.Group axis="y" values={doc.sections} className="mt-3 space-y-0.5"
        onReorder={(next) => update((d) => ({ ...d, sections: next }))}>
        {doc.sections.map((s) => <OutlineItem key={s.id} section={s} update={update} />)}
      </Reorder.Group>
      <p className="mt-4 px-2 text-[11px] leading-[1.5] text-[#a39884]">Drag to reorder. Hidden sections stay here but are left out of exports.</p>
    </aside>
  );
}

function OutlineItem({ section, update }: { section: ReportSection; update: (fn: (d: ReportDocument) => ReportDocument) => void }) {
  const controls = useDragControls();
  return (
    <Reorder.Item value={section} dragListener={false} dragControls={controls}
      whileDrag={{ scale: 1.02, boxShadow: "0 12px 30px -12px rgb(60 40 10 / 0.35)" }}
      className="group flex items-center gap-1.5 rounded-lg bg-[#faf8f4] px-1.5 py-1.5 hover:bg-white">
      <span onPointerDown={(e) => controls.start(e)} className="cursor-grab touch-none text-[#c9bfae] opacity-0 transition group-hover:opacity-100 active:cursor-grabbing">
        <GripVertical className="size-3.5" />
      </span>
      <button onClick={() => document.getElementById(`sec-${section.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
        className={clsx("min-w-0 flex-1 truncate text-left text-[12.5px]", section.hidden ? "text-[#b8ae9c] line-through decoration-[#d9cfbd]" : "text-[#3f4a56]")}>
        {section.title}
      </button>
      <button title={section.hidden ? "Show in exports" : "Hide from exports"} onClick={() => update((d) => ({ ...d, sections: d.sections.map((x) => x.id === section.id ? { ...x, hidden: !x.hidden } : x) }))}
        className="text-[#b8ae9c] opacity-0 transition hover:text-ink group-hover:opacity-100">
        {section.hidden ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
      </button>
    </Reorder.Item>
  );
}

// ----------------------------------------------------------------------------- document

function Editable({ value, onCommit, className, as = "div", placeholder, multiline = true }: {
  value: string; onCommit: (v: string) => void; className?: string; as?: "div" | "h1" | "h2" | "p" | "span" | "li" | "td" | "th";
  placeholder?: string; multiline?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { if (ref.current && document.activeElement !== ref.current) ref.current.innerText = value; }, [value]);
  const Tag = as as "div";
  return (
    <Tag ref={ref as React.RefObject<HTMLDivElement>} contentEditable suppressContentEditableWarning data-placeholder={placeholder}
      spellCheck className={className}
      onKeyDown={(e: KeyboardEvent) => { if (!multiline && e.key === "Enter") { e.preventDefault(); (e.target as HTMLElement).blur(); } }}
      onBlur={(e) => { const v = (e.target as HTMLElement).innerText.trim(); if (v !== value) onCommit(v); }} />
  );
}

function SectionView({ section, flash, update }: { section: ReportSection; flash: Set<string>; update: (fn: (d: ReportDocument) => ReportDocument) => void }) {
  const setSection = (fn: (s: ReportSection) => ReportSection) =>
    update((d) => ({ ...d, sections: d.sections.map((s) => (s.id === section.id ? fn(s) : s)) }));
  const setBlock = (bid: string, fn: (b: ReportBlock) => ReportBlock) =>
    setSection((s) => ({ ...s, blocks: s.blocks.map((b) => (b.id === bid ? fn(b) : b)) }));
  const removeBlock = (bid: string) => setSection((s) => ({ ...s, blocks: s.blocks.filter((b) => b.id !== bid) }));
  const moveBlock = (bid: string, dir: -1 | 1) => setSection((s) => {
    const i = s.blocks.findIndex((b) => b.id === bid);
    const j = i + dir;
    if (j < 0 || j >= s.blocks.length) return s;
    const blocks = [...s.blocks];
    [blocks[i], blocks[j]] = [blocks[j], blocks[i]];
    return { ...s, blocks };
  });
  const [adding, setAdding] = useState(false);

  return (
    <motion.section id={`sec-${section.id}`} layout="position" transition={{ duration: 0.4, ease: EASE }}
      className={clsx("group/sec relative mt-10 scroll-mt-10 rounded-xl", flash.has(section.id) && "flash", section.hidden && "opacity-45")}>
      <div className="flex items-center gap-3">
        <Editable value={section.title} multiline={false} as="h2" placeholder="Section title"
          className="editable -mx-1.5 px-1.5 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#b8862b]"
          onCommit={(v) => setSection((s) => ({ ...s, title: v || s.title }))} />
        {section.hidden && <span className="rounded-full bg-[#f3eee4] px-2 py-0.5 text-[10.5px] text-[#8a7e6b]">Hidden from exports</span>}
        <button onClick={() => { if (confirm(`Delete “${section.title}”?`)) update((d) => ({ ...d, sections: d.sections.filter((s) => s.id !== section.id) })); }}
          className="ml-auto text-[#c9bfae] opacity-0 transition hover:text-rose-600 group-hover/sec:opacity-100" title="Delete section">
          <Trash2 className="size-3.5" />
        </button>
      </div>
      <div className="mt-3 space-y-4">
        {section.blocks.map((b) => (
          <div key={b.id} id={`blk-${b.id}`} className={clsx("group/blk relative -mx-3 rounded-xl px-3 py-1", flash.has(b.id) && "flash")}>
            <BlockView block={b} onChange={(fn) => setBlock(b.id, fn)} />
            <div className="absolute -left-9 top-1 flex flex-col opacity-0 transition group-hover/blk:opacity-100">
              <button title="Move up" onClick={() => moveBlock(b.id, -1)} className="grid size-6 place-items-center rounded text-[#c9bfae] hover:bg-[#f6f1e7] hover:text-ink"><ArrowUp className="size-3" /></button>
              <button title="Move down" onClick={() => moveBlock(b.id, 1)} className="grid size-6 place-items-center rounded text-[#c9bfae] hover:bg-[#f6f1e7] hover:text-ink"><ArrowUp className="size-3 rotate-180" /></button>
              <button title="Delete block" onClick={() => removeBlock(b.id)} className="grid size-6 place-items-center rounded text-[#c9bfae] hover:bg-rose-50 hover:text-rose-600"><Trash2 className="size-3" /></button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 h-8">
        <AnimatePresence mode="wait" initial={false}>
          {adding ? (
            <motion.div key="menu" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex gap-1.5">
              {([["paragraph", "Paragraph"], ["bullets", "Bullet list"], ["note", "Small note"], ["callout", "Callout"]] as const).map(([t, label]) => (
                <button key={t} onClick={() => { setAdding(false); setSection((s) => ({ ...s, blocks: [...s.blocks, newBlock(t)] })); }}
                  className="rounded-full border border-[#ece3d2] bg-white px-2.5 py-1 text-[11.5px] text-[#5b5245] transition hover:border-[#d9c49a] hover:bg-[#fbf7ef]">{label}</button>
              ))}
              <button onClick={() => setAdding(false)} className="px-2 text-[11.5px] text-muted">Cancel</button>
            </motion.div>
          ) : (
            <motion.button key="add" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setAdding(true)}
              className="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11.5px] text-[#b3a78f] opacity-0 transition hover:bg-[#fbf7ef] hover:text-[#8a5a0b] group-hover/sec:opacity-100">
              <Plus className="size-3" /> Add block
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}

function newBlock(type: "paragraph" | "bullets" | "note" | "callout"): ReportBlock {
  if (type === "bullets") return { id: uid(), type, items: ["New point"] };
  if (type === "callout") return { id: uid(), type, text: "Key message", tone: "warn" };
  return { id: uid(), type, text: "" };
}

const TONE = { good: "border-[#2f7d6d] text-[#1f5c50] bg-[#f1f8f5]", warn: "border-[#c98a1b] text-[#7a4f0c] bg-[#fdf8ee]", bad: "border-[#b4443c] text-[#8a2f28] bg-[#fcf2f1]", neutral: "border-[#9aa3b0] text-[#3f4a56] bg-[#f6f7f9]" };

function BlockView({ block: b, onChange }: { block: ReportBlock; onChange: (fn: (b: ReportBlock) => ReportBlock) => void }) {
  switch (b.type) {
    case "lead":
      return <Editable value={b.text ?? ""} placeholder="Headline" onCommit={(v) => onChange((x) => ({ ...x, text: v }))}
        className="editable -mx-1.5 px-1.5 font-serif text-[21px] font-semibold leading-[1.35] text-[#1e2a36]" />;
    case "paragraph":
      return <Editable value={b.text ?? ""} placeholder="Write something…" onCommit={(v) => onChange((x) => ({ ...x, text: v }))}
        className="editable -mx-1.5 px-1.5 text-[14px] leading-[1.75] text-[#3f4a56]" />;
    case "note":
      return <Editable value={b.text ?? ""} placeholder="Note" onCommit={(v) => onChange((x) => ({ ...x, text: v }))}
        className="editable -mx-1.5 px-1.5 text-[12px] leading-[1.6] text-[#8a7e6b]" />;
    case "callout":
      return (
        <div className={clsx("rounded-xl border-l-[3px] px-4 py-3", TONE[b.tone ?? "neutral"])}>
          <Editable value={b.text ?? ""} onCommit={(v) => onChange((x) => ({ ...x, text: v }))} className="editable -mx-1.5 px-1.5 text-[14px] font-semibold leading-[1.55]" />
        </div>
      );
    case "bullets":
      return (
        <ul className="space-y-2">
          <AnimatePresence initial={false}>
            {(b.items ?? []).map((item: string, i: number) => (
              <motion.li key={`${i}-${item.slice(0, 12)}`} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, height: 0 }}
                className="group/li flex items-start gap-3">
                <span className="mt-[9px] size-[7px] shrink-0 rounded-full bg-[#c98a1b]" />
                <Editable value={item} onCommit={(v) => onChange((x) => ({ ...x, items: v ? x.items!.map((it, j) => (j === i ? v : it)) : x.items!.filter((_, j) => j !== i) }))}
                  className="editable -mx-1.5 flex-1 px-1.5 text-[14px] leading-[1.7] text-[#3f4a56]" />
              </motion.li>
            ))}
          </AnimatePresence>
          <li>
            <button onClick={() => onChange((x) => ({ ...x, items: [...(x.items ?? []), "New point"] }))}
              className="ml-5 inline-flex items-center gap-1 text-[11.5px] text-[#b3a78f] opacity-0 transition hover:text-[#8a5a0b] group-hover/blk:opacity-100">
              <ListPlus className="size-3" /> Add point
            </button>
          </li>
        </ul>
      );
    case "kpis":
      return (
        <div className="grid gap-2.5" style={{ gridTemplateColumns: `repeat(${Math.min(4, b.items?.length ?? 1)}, minmax(0,1fr))` }}>
          {(b.items ?? []).map((k: { value: string; label: string }, i: number) => (
            <div key={i} className="rounded-2xl border border-[#efe3cb] bg-[#fbf7ef] px-3 py-4 text-center">
              <Editable value={k.value} multiline={false} onCommit={(v) => onChange((x) => ({ ...x, items: x.items!.map((it, j) => (j === i ? { ...it, value: v } : it)) }))}
                className={clsx("editable font-serif font-semibold text-[#1e2a36] tnum whitespace-nowrap", k.value.length > 11 ? "text-[16px]" : "text-[20px]")} />
              <Editable value={k.label} multiline={false} onCommit={(v) => onChange((x) => ({ ...x, items: x.items!.map((it, j) => (j === i ? { ...it, label: v } : it)) }))}
                className="editable mt-1 text-[11px] text-[#8a7e6b]" />
            </div>
          ))}
        </div>
      );
    case "bars":
      return (
        <div className="space-y-3">
          {(b.items ?? []).map((it: { label: string; note: string; value: number; display: string }, i: number) => (
            <div key={i}>
              <div className="flex items-baseline gap-2 text-[12.5px]"><span className="font-semibold text-[#1e2a36]">{it.label}</span><span className="text-[11.5px] text-[#8a7e6b]">{it.note}</span>
                <span className="ml-auto font-semibold text-[#1e2a36] tnum">{it.display}</span></div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#f4ecdd]">
                <motion.div initial={{ width: 0 }} whileInView={{ width: `${Math.max(3, it.value * 100)}%` }} viewport={{ once: true }}
                  transition={{ duration: 0.9, delay: i * 0.04, ease: EASE }} className="h-full rounded-full bg-gradient-to-r from-[#e4c98f] to-[#b8862b]" />
              </div>
            </div>
          ))}
        </div>
      );
    case "table":
      return (
        <div className="overflow-hidden rounded-xl border border-[#efe3cb]">
          <table className="w-full border-collapse text-[12.5px]">
            <thead className="bg-[#fbf7ef]"><tr>{(b.header ?? []).map((h, i) => (
              <th key={i} className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8a7e6b]">
                <Editable value={h} multiline={false} as="span" onCommit={(v) => onChange((x) => ({ ...x, header: x.header!.map((c, j) => (j === i ? v : c)) }))} className="editable" />
              </th>))}</tr></thead>
            <tbody>{(b.rows ?? []).map((r, ri) => (
              <tr key={ri} className="border-t border-[#f3ead9] align-top">{r.map((c, ci) => (
                <td key={ci} className="px-3 py-2 text-[#3f4a56]">
                  <Editable value={c} onCommit={(v) => onChange((x) => ({ ...x, rows: x.rows!.map((row, i) => (i === ri ? row.map((cc, j) => (j === ci ? v : cc)) : row)) }))} className="editable -mx-1 px-1" />
                </td>))}</tr>))}
            </tbody>
          </table>
        </div>
      );
    default:
      return null;
  }
}

function AddSection({ update }: { update: (fn: (d: ReportDocument) => ReportDocument) => void }) {
  return (
    <button onClick={() => update((d) => ({ ...d, sections: [...d.sections, { id: uid(), key: "custom", title: "New section", hidden: false, blocks: [{ id: uid(), type: "paragraph", text: "" }] }] }))}
      className="mt-12 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[#e3d8c3] py-4 text-[12.5px] text-[#a39884] transition hover:border-[#c98a1b] hover:bg-[#fdfaf4] hover:text-[#8a5a0b]">
      <Plus className="size-4" /> Add section
    </button>
  );
}

// ----------------------------------------------------------------------------- assistant

const STARTERS = ["Rename risks to Key risks", "Move delivery above risks", "Add a next step: confirm OEM letters by Friday",
  "Shorten the risks section", "Add the total price to the summary", "Mention our ISO 27001 certification in risks"];

function Assistant({ id, doc, beforeSend, onReply }: { id: number; doc: ReportDocument; beforeSend: () => Promise<void>; onReply: (d: ReportDocument, changed?: string[]) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>(doc.chat ?? []);
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const ask = useMutation({
    mutationFn: async (text: string) => { await beforeSend(); return report.ask(id, text); },
    onSuccess: (r) => {
      setMessages(r.document.chat);
      setSuggestions(r.suggestions);
      if (r.changed) onReply(r.document, r.changes.map((c) => c.block ?? c.section).filter(Boolean) as string[]);
    },
    onError: (e: Error) => setMessages((m) => [...m, { role: "assistant", text: `Something went wrong: ${e.message}`, at: new Date().toISOString() }]),
  });
  const send = useCallback((text: string) => {
    const t = text.trim();
    if (!t || ask.isPending) return;
    setMessages((m) => [...m, { role: "user", text: t, at: new Date().toISOString() }]);
    setInput("");
    ask.mutate(t);
  }, [ask]);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [messages, ask.isPending]);
  useEffect(() => {
    const h = (e: Event) => send((e as CustomEvent<string>).detail);
    document.addEventListener("assistant:send", h);
    return () => document.removeEventListener("assistant:send", h);
  }, [send]);
  const starters = useMemo(() => (messages.length ? suggestions : STARTERS), [messages.length, suggestions]);

  return (
    <aside className="flex min-h-0 flex-col border-l border-[#e8e2d4] bg-white">
      <div className="flex items-center gap-3 border-b border-line px-5 py-4">
        <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-[#1e2a36] to-[#0b1220] text-[#e4c98f] shadow-[0_6px_16px_-6px_rgb(11_18_32/0.6)]">
          <MessageSquareText className="size-4" />
        </span>
        <div>
          <div className="text-[13.5px] font-semibold text-ink">Editing assistant</div>
          <div className="text-[11.5px] text-muted">Tell it what to change — it edits the report for you</div>
        </div>
      </div>
      <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}
            className="rounded-2xl border border-[#efe7d8] bg-[#fbf8f2] px-4 py-3.5 text-[12.5px] leading-[1.6] text-[#5b5245]">
            Type an instruction in plain words — rename, move, hide or delete sections, add points, replace wording, shorten a
            section, insert a figure or a fact from the company knowledge base. Every change can be undone. You can also click
            anywhere in the document and type.
          </motion.div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div key={`${i}-${m.at}`} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.32, ease: EASE }} className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div className={clsx("max-w-[88%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-[12.5px] leading-[1.55]",
                m.role === "user" ? "rounded-br-md bg-ink text-white" : "rounded-bl-md border border-line bg-[#fafbfc] text-ink-soft")}>
                {m.text}
                {m.role === "assistant" && m.changes && m.changes.length > 0 && (
                  <div className="mt-1.5 flex items-center gap-1 text-[11px] font-medium text-emerald-700"><Check className="size-3" /> Applied to the document</div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {ask.isPending && (
          <div className="flex gap-1 rounded-2xl rounded-bl-md border border-line bg-[#fafbfc] px-3.5 py-3 w-fit">
            {[0, 1, 2].map((i) => <span key={i} className="typing-dot size-1.5 rounded-full bg-[#9aa1ad]" style={{ animationDelay: `${i * 0.15}s` }} />)}
          </div>
        )}
      </div>
      <div className="border-t border-line p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {starters.map((s) => (
            <button key={s} onClick={() => (s.endsWith(": ") ? (setInput(s), area.current?.focus()) : send(s))}
              className="rounded-full border border-line bg-white px-2.5 py-1 text-[11.5px] text-ink-soft transition hover:-translate-y-px hover:border-[#d9c49a] hover:bg-[#fbf7ef] hover:text-[#8a5a0b]">
              {s.trim()}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-2 rounded-2xl border border-line-strong bg-white px-3 py-2 shadow-[var(--shadow-card)] focus-within:border-[#d9c49a] focus-within:ring-4 focus-within:ring-[#c98a1b]/10">
          <textarea ref={area} value={input} onChange={(e) => setInput(e.target.value)} rows={1} placeholder="e.g. move compliance to the top"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
            className="max-h-32 min-h-[24px] flex-1 resize-none bg-transparent py-1 text-[13px] outline-none placeholder:text-subtle" />
          <button onClick={() => send(input)} disabled={!input.trim() || ask.isPending}
            className="grid size-8 shrink-0 place-items-center rounded-xl bg-ink text-white transition hover:bg-ink-soft disabled:opacity-30">
            {ask.isPending ? <RefreshCw className="size-3.5 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </div>
      </div>
    </aside>
  );
}
