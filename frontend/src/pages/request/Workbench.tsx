import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Minus, Plus, RotateCcw, Search, Trash2, Undo2, X } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Badge, Button, Field, Segmented, Spinner } from "../../components/ui";
import { api, type LineOverride, type RepriceBody } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { Product, RfpDetail } from "../../lib/types";
import { CATEGORY_LABEL, getBaseCurrency, money, titleCase } from "../../lib/format";

const REVIEWER = "added by reviewer";
const INCOTERMS = ["", "EXW", "FCA", "FOB", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"];
const SEGMENTS = ["enterprise", "smb", "public", "education", "healthcare"] as const;

interface Row {
  lineNo: number;
  name: string;
  sku: string | null;
  requested: string;
  qty: number;
  price: number | null; // current recommended/overridden price
  unitCost: number | null;
  floor: number | null;
  list: number | null;
  bundle: string; // "" = none
  bundles: { code: string; name: string; unit_cost: number }[];
  included: boolean;
  added: boolean;
  unmatched: boolean;
  candidates: { sku: string; name: string; score: number }[];
  strategy: string | null;
}

function buildRows(rfp: RfpDetail): Row[] {
  const strat = rfp.pricing?.strategy;
  const costing = rfp.pricing?.costing;
  const excluded = new Map((costing?.excluded ?? []).map((e) => [e.line_no, e]));
  return (rfp.parsed?.line_items ?? []).map((it) => {
    const p = strat?.lines.find((l) => l.line_no === it.line_no);
    const c = costing?.lines.find((l) => l.line_no === it.line_no);
    return {
      lineNo: it.line_no,
      name: p?.name ?? it.candidates.find((x) => x.sku === it.selected_sku)?.name ?? it.description,
      sku: p?.sku ?? it.selected_sku,
      requested: it.description,
      qty: p?.quantity ?? it.quantity,
      price: p?.unit_price ?? null,
      unitCost: c?.unit_cost ?? null,
      floor: c?.floor_price ?? null,
      list: c?.list_price ?? null,
      bundle: p?.bundle?.code ?? "",
      bundles: c?.value_adds.map((v) => ({ code: v.code, name: v.name, unit_cost: v.unit_cost })) ?? [],
      included: !excluded.has(it.line_no) && !!p,
      added: it.quantity_source === REVIEWER,
      unmatched: !it.selected_sku,
      candidates: it.candidates.map((x) => ({ sku: x.sku, name: x.name, score: x.score })),
      strategy: p?.strategy ?? (excluded.get(it.line_no)?.reason ?? null),
    };
  });
}

function Stepper({ value, onChange, disabled }: { value: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <div className={clsx("inline-flex h-8 items-center rounded-lg border border-line-strong bg-white", disabled && "opacity-50")}>
      <button type="button" disabled={disabled || value <= 1} onClick={() => onChange(value - 1)} className="grid h-full w-7 place-items-center text-muted hover:text-ink disabled:opacity-40"><Minus className="size-3" /></button>
      <input type="number" min={1} value={value} disabled={disabled} onChange={(e) => onChange(Math.max(1, Number(e.target.value) || 1))}
        className="h-full w-14 border-x border-line bg-transparent text-center text-[12.5px] tnum outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none" />
      <button type="button" disabled={disabled} onClick={() => onChange(value + 1)} className="grid h-full w-7 place-items-center text-muted hover:text-ink"><Plus className="size-3" /></button>
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)}
      className={clsx("relative h-5 w-9 rounded-full transition-colors", on ? "bg-ink" : "bg-[#d5d9e0]")}>
      <span className={clsx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", on ? "left-[18px]" : "left-0.5")} />
    </button>
  );
}

export function Workbench({ rfp, open, onClose }: { rfp: RfpDetail; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const base = rfp.pricing?.strategy?.base_currency ?? getBaseCurrency();
  const original = useMemo(() => buildRows(rfp), [rfp]);
  const [rows, setRows] = useState<Row[]>(original);
  const [tab, setTab] = useState<"lines" | "add" | "client">("lines");
  const [bulk, setBulk] = useState(0);
  const [adds, setAdds] = useState<{ product: Product; qty: number }[]>([]);
  const [q, setQ] = useState("");
  const deferred = useDeferredValue(q.trim());
  const [note, setNote] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);

  const parsed = rfp.parsed!;
  const loc = rfp.pricing?.localisation;
  const [client, setClient] = useState({
    name: parsed.client.name ?? "", country: parsed.client.country ?? "", region: parsed.client.region ?? "",
    tax_id: parsed.client.tax_id ?? "", segment: parsed.client.segment,
  });
  const [incoterm, setIncoterm] = useState(parsed.terms.incoterm ?? "");
  const [currency, setCurrency] = useState(loc?.currency ?? base);
  const [buffer, setBuffer] = useState(loc?.fx_buffer_pct ?? 1.5);

  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries, enabled: open });
  const products = useQuery({ queryKey: ["products", deferred, ""], queryFn: () => api.products({ q: deferred || undefined }), enabled: open && tab === "add" });

  const update = (lineNo: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.lineNo === lineNo ? { ...r, ...patch } : r)));
  const applyBulk = (pct: number) => {
    setBulk(pct);
    setRows(original.map((o) => {
      const cur = rows.find((r) => r.lineNo === o.lineNo)!;
      return o.price === null ? cur : { ...cur, price: Math.round(o.price * (1 + pct / 100)) };
    }));
  };
  const liftToFloor = () => setRows((rs) => rs.map((r) => {
    const bc = r.bundles.find((b) => b.code === r.bundle)?.unit_cost ?? 0;
    const min = r.floor !== null ? Math.ceil(r.floor + bc) : null;
    return r.price !== null && min !== null && r.price < min ? { ...r, price: min } : r;
  }));

  // ---- live economics
  const econ = useMemo(() => {
    let revenue = 0, cost = 0, below = 0;
    for (const r of rows) {
      if (!r.included || r.price === null || r.unitCost === null) continue;
      const bc = r.bundles.find((b) => b.code === r.bundle)?.unit_cost ?? 0;
      revenue += r.price * r.qty;
      cost += (r.unitCost + bc) * r.qty;
      if (r.floor !== null && r.price - bc < r.floor - 0.01) below++;
    }
    for (const a of adds) { revenue += a.product.list_price * a.qty; cost += a.product.unit_cost * a.qty; }
    return { revenue, cost, margin: revenue ? (100 * (revenue - cost)) / revenue : 0, below };
  }, [rows, adds]);
  const before = rfp.pricing?.strategy;

  // ---- diff into a reprice request
  const body = useMemo<RepriceBody>(() => {
    const lines: Record<string, LineOverride> = {};
    const removeAdded: number[] = [];
    for (const r of rows) {
      const o = original.find((x) => x.lineNo === r.lineNo)!;
      if (r.added && !r.included) { removeAdded.push(r.lineNo); continue; }
      const ov: LineOverride = {};
      if (r.included !== o.included) ov.exclude = !r.included;
      if (r.included) {
        if (r.qty !== o.qty) ov.quantity = r.qty;
        if (r.sku && r.sku !== o.sku) ov.sku = r.sku;
        const priceChanged = r.price !== null && o.price !== null && Math.abs(r.price - o.price) > 0.005;
        const bundleChanged = r.bundle !== o.bundle;
        if (priceChanged || bundleChanged) ov.unit_price = r.price ?? undefined;
        if (bundleChanged) { if (r.bundle) ov.bundle = r.bundle; else ov.clear_bundle = true; }
      }
      if (Object.keys(ov).length) lines[String(r.lineNo)] = ov;
    }
    const b: RepriceBody = { lines, actor: user?.name, note: note || undefined };
    if (removeAdded.length) b.remove_added = removeAdded;
    if (adds.length) b.add_lines = adds.map((a) => ({ sku: a.product.sku, quantity: a.qty }));
    const c = parsed.client;
    const edits: RepriceBody["client"] = {};
    if (client.name !== (c.name ?? "")) edits.name = client.name || null;
    if (client.country && client.country !== c.country) edits.country = client.country;
    if (client.region !== (c.region ?? "")) edits.region = client.region || null;
    if (client.tax_id !== (c.tax_id ?? "")) edits.tax_id = client.tax_id || null;
    if (client.segment !== c.segment) edits.segment = client.segment;
    if (Object.keys(edits).length) b.client = edits;
    if (incoterm !== (parsed.terms.incoterm ?? "")) b.incoterm = incoterm;
    if (loc && currency !== loc.currency) b.currency = currency;
    if (loc && buffer !== loc.fx_buffer_pct) b.fx_buffer_pct = buffer;
    return b;
  }, [rows, original, adds, client, incoterm, currency, buffer, note, parsed, loc, user]);

  const changeCount = Object.keys(body.lines ?? {}).length + (body.remove_added?.length ?? 0) + (body.add_lines?.length ?? 0)
    + Object.keys(body.client ?? {}).length + (body.incoterm !== undefined ? 1 : 0) + (body.currency ? 1 : 0) + (body.fx_buffer_pct !== undefined ? 1 : 0);

  const apply = useMutation({
    mutationFn: () => api.reprice(rfp.id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rfp", rfp.id] }); qc.invalidateQueries({ queryKey: ["rfps"] }); onClose(); },
  });
  const reset = useMutation({
    mutationFn: () => api.reprice(rfp.id, { reset: true, actor: user?.name, note: "All manual adjustments cleared" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rfp", rfp.id] }); onClose(); },
  });
  const discard = () => {
    setRows(original); setAdds([]); setBulk(0); setNote("");
    setClient({ name: parsed.client.name ?? "", country: parsed.client.country ?? "", region: parsed.client.region ?? "", tax_id: parsed.client.tax_id ?? "", segment: parsed.client.segment });
    setIncoterm(parsed.terms.incoterm ?? ""); setCurrency(loc?.currency ?? base); setBuffer(loc?.fx_buffer_pct ?? 1.5);
  };

  if (!open) return null;
  const selectedCountry = countries.data?.find((c) => c.code === client.country);
  const currencies = Array.from(new Set([base, ...(countries.data ?? []).map((c) => c.currency)])).sort();
  const hasOverrides = Object.keys(rfp.overrides ?? {}).some((k) => k !== "_version");

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-[#0b1220]/30 animate-fade-in" onClick={onClose} />
      <aside className="animate-slide-in absolute inset-y-0 right-0 flex w-[1080px] max-w-full flex-col bg-canvas shadow-[var(--shadow-pop)]">
        {/* header */}
        <header className="flex items-start justify-between gap-4 border-b border-line bg-white px-7 pb-0 pt-5">
          <div className="min-w-0">
            <div className="label">Adjustment workbench</div>
            <h2 className="mt-1 truncate text-[17px] font-semibold tracking-[-0.01em]">{rfp.parsed?.title}</h2>
            <div className="mt-4 flex items-center gap-1">
              {([["lines", "Line items", rows.length], ["add", "Add items", adds.length || undefined], ["client", "Client & terms", undefined]] as const).map(([v, l, n]) => (
                <button key={v} onClick={() => setTab(v)}
                  className={clsx("relative -mb-px inline-flex h-10 items-center gap-2 px-3 text-[13px] font-medium transition-colors",
                    tab === v ? "text-ink after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:rounded-full after:bg-ink" : "text-muted hover:text-ink")}>
                  {l}{n !== undefined && <span className={clsx("rounded-full px-1.5 text-[11px] tnum", tab === v ? "bg-ink text-white" : "bg-[#eef0f3] text-muted")}>{n}</span>}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasOverrides && (confirmReset ? (
              <span className="flex items-center gap-2 text-[12px] text-muted">Clear every manual change?
                <Button size="sm" variant="danger" loading={reset.isPending} onClick={() => reset.mutate()}>Clear all</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmReset(false)}>Keep</Button></span>
            ) : <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => setConfirmReset(true)}>Reset to recommendations</Button>)}
            <button onClick={onClose} className="rounded-md p-1.5 text-muted hover:bg-black/5 hover:text-ink" aria-label="Close"><X className="size-4" /></button>
          </div>
        </header>

        {/* body */}
        <div className="flex-1 overflow-y-auto px-7 py-6">
          {tab === "lines" && (
            <div className="space-y-4">
              <div className="card flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4">
                <div className="min-w-[280px] flex-1">
                  <div className="flex items-center justify-between text-[12.5px]"><span className="font-medium">Adjust all prices</span>
                    <span className={clsx("tnum font-semibold", bulk > 0 ? "text-emerald-700" : bulk < 0 ? "text-rose-700" : "text-muted")}>{bulk > 0 ? "+" : ""}{bulk.toFixed(1)}%</span></div>
                  <input type="range" min={-10} max={10} step={0.5} value={bulk} onChange={(e) => applyBulk(Number(e.target.value))} className="mt-2 w-full accent-[#0b1220]" />
                  <div className="flex justify-between text-[10.5px] text-subtle"><span>−10%</span><span>recommended</span><span>+10%</span></div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={liftToFloor} disabled={!econ.below}>Lift to margin floor</Button>
                  <Button size="sm" variant="ghost" icon={<Undo2 className="size-3.5" />} onClick={() => { setRows(original); setBulk(0); }}>Restore lines</Button>
                </div>
              </div>

              <div className="card overflow-hidden">
                <table className="table-base">
                  <thead><tr><th className="w-10">#</th><th>Product</th><th className="w-[120px]">Quantity</th><th className="w-[150px] !text-right">Unit price ({base})</th><th className="w-[90px] !text-right">Margin</th><th className="w-[200px]">Included service</th><th className="w-[70px] !text-center">Quote</th></tr></thead>
                  <tbody>
                    {rows.map((r) => {
                      const o = original.find((x) => x.lineNo === r.lineNo)!;
                      const bc = r.bundles.find((b) => b.code === r.bundle)?.unit_cost ?? 0;
                      const margin = r.price && r.unitCost !== null ? (100 * (r.price - r.unitCost - bc)) / r.price : null;
                      const below = r.floor !== null && r.price !== null && r.price - bc < r.floor - 0.01;
                      const changed = JSON.stringify({ ...r, strategy: 0 }) !== JSON.stringify({ ...o, strategy: 0 });
                      return (
                        <tr key={r.lineNo} className={clsx("transition-colors", !r.included && "bg-[#fafbfc] text-muted", changed && r.included && "bg-[#fffcf5]")}>
                          <td className="tnum text-muted">{r.lineNo}</td>
                          <td className="max-w-[300px]">
                            {r.unmatched && r.included === false && r.candidates.length ? (
                              <>
                                <div className="text-[12px] text-muted">“{r.requested}”</div>
                                <select className="input mt-1 h-8" value={r.sku ?? ""} onChange={(e) => update(r.lineNo, { sku: e.target.value || null, included: !!e.target.value, name: r.candidates.find((c) => c.sku === e.target.value)?.name ?? r.name })}>
                                  <option value="">No product — not quoted</option>
                                  {r.candidates.map((c) => <option key={c.sku} value={c.sku}>{c.name} ({Math.round(c.score * 100)}%)</option>)}
                                </select>
                              </>
                            ) : (
                              <>
                                <div className={clsx("truncate font-medium", !r.included && "line-through decoration-subtle")}>{r.name}</div>
                                <div className="flex items-center gap-1.5 text-[11.5px] text-muted">
                                  <span className="font-mono">{r.sku ?? "—"}</span>
                                  {r.added && <Badge tone="blue">Added</Badge>}
                                  {changed && r.included && <Badge tone="gold">Edited</Badge>}
                                  {!r.included && r.strategy && <span>· {r.strategy}</span>}
                                </div>
                              </>
                            )}
                          </td>
                          <td><Stepper value={r.qty} disabled={!r.included} onChange={(v) => update(r.lineNo, { qty: v })} /></td>
                          <td className="text-right">
                            {r.price !== null ? (
                              <>
                                <input type="number" min={0} step="1" value={Math.round(r.price * 100) / 100} disabled={!r.included}
                                  onChange={(e) => update(r.lineNo, { price: Number(e.target.value) || 0 })}
                                  className={clsx("input h-8 w-[130px] text-right tnum", below && "!border-rose-300 bg-rose-50/50")} />
                                {o.price !== null && Math.abs((r.price ?? 0) - o.price) > 0.005 && (
                                  <div className="mt-0.5 text-[11px] text-muted tnum">was {money(o.price, base)}</div>
                                )}
                              </>
                            ) : <span className="text-[12px] text-muted">Priced on apply</span>}
                          </td>
                          <td className="text-right">
                            {margin !== null ? (
                              <span className={clsx("tnum font-medium", below ? "text-rose-700" : margin < 10 ? "text-amber-700" : "text-emerald-700")}>
                                {below && <AlertTriangle className="mr-1 inline size-3.5 -translate-y-px" />}{margin.toFixed(1)}%
                              </span>
                            ) : <span className="text-muted">—</span>}
                          </td>
                          <td>
                            {r.bundles.length ? (
                              <select className="input h-8" value={r.bundle} disabled={!r.included} onChange={(e) => update(r.lineNo, { bundle: e.target.value })}>
                                <option value="">None</option>
                                {r.bundles.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
                              </select>
                            ) : <span className="text-[12px] text-subtle">Not available</span>}
                          </td>
                          <td className="text-center">
                            {r.added ? (
                              <button onClick={() => update(r.lineNo, { included: !r.included })} className={clsx("rounded-md p-1.5 transition", r.included ? "text-muted hover:bg-rose-50 hover:text-rose-700" : "text-rose-700")} title={r.included ? "Remove added item" : "Keep added item"}>
                                {r.included ? <Trash2 className="size-4" /> : <Undo2 className="size-4" />}
                              </button>
                            ) : (r.unmatched && !r.sku) ? <span className="text-[11px] text-subtle">—</span>
                              : <Toggle on={r.included} onChange={(v) => update(r.lineNo, { included: v })} />}
                          </td>
                        </tr>
                      );
                    })}
                    {adds.map((a, i) => (
                      <tr key={`new-${i}`} className="bg-[#f5f8ff]">
                        <td className="text-muted">new</td>
                        <td><div className="font-medium">{a.product.name}</div><div className="flex items-center gap-1.5 text-[11.5px] text-muted"><span className="font-mono">{a.product.sku}</span><Badge tone="blue">To add</Badge></div></td>
                        <td><Stepper value={a.qty} onChange={(v) => setAdds(adds.map((x, j) => (j === i ? { ...x, qty: v } : x)))} /></td>
                        <td className="text-right text-[12px] text-muted">Priced on apply</td>
                        <td className="text-right text-muted">—</td>
                        <td className="text-[12px] text-subtle">Chosen by strategy</td>
                        <td className="text-center"><button onClick={() => setAdds(adds.filter((_, j) => j !== i))} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-700"><Trash2 className="size-4" /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[12px] text-muted">Prices you type are kept as reviewer overrides. Quantities, products and additions are re-costed and re-priced by the strategy engine; win probability and taxes are recalculated when you apply.</p>
            </div>
          )}

          {tab === "add" && (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="card overflow-hidden">
                <div className="border-b border-line px-4 py-3">
                  <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-subtle" />
                    <input autoFocus className="input pl-8" placeholder="Search the catalogue, e.g. “docking station” or “1500VA UPS”" value={q} onChange={(e) => setQ(e.target.value)} /></div>
                </div>
                <div className="max-h-[calc(100vh-330px)] overflow-y-auto">
                  {products.isLoading ? <div className="grid place-items-center py-12"><Spinner /></div> : (
                    <ul className="divide-y divide-line">
                      {products.data?.filter((p) => p.active).map((p) => {
                        const inQuote = rows.some((r) => r.sku === p.sku && r.included) || adds.some((a) => a.product.sku === p.sku);
                        return (
                          <li key={p.sku} className="group flex items-center gap-4 px-4 py-3 transition hover:bg-[#fafbfc]">
                            <div className="min-w-0 flex-1">
                              <div className="truncate font-medium">{p.name}</div>
                              <div className="flex items-center gap-2 text-[11.5px] text-muted"><span className="font-mono">{p.sku}</span><span>· {CATEGORY_LABEL[p.category] ?? p.category}</span>
                                <span>· {p.stock_qty >= 99999 ? "licensed" : `${p.stock_qty.toLocaleString()} in stock`}</span></div>
                            </div>
                            <div className="text-right"><div className="tnum text-[13px] font-medium">{money(p.list_price)}</div><div className="text-[11px] text-muted">list</div></div>
                            <Button size="sm" variant={inQuote ? "ghost" : "secondary"} icon={<Plus className="size-3.5" />}
                              onClick={() => setAdds([...adds, { product: p, qty: 1 }])}>{inQuote ? "Add again" : "Add"}</Button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>
              <div className="card h-fit p-5">
                <div className="label">To be added</div>
                {adds.length === 0 ? <p className="mt-3 text-[12.5px] text-muted">Items the client didn't list but should be quoted — accessories, services or licences.</p> : (
                  <ul className="mt-3 space-y-3">
                    {adds.map((a, i) => (
                      <li key={i} className="flex items-center gap-3">
                        <div className="min-w-0 flex-1"><div className="truncate text-[12.5px] font-medium">{a.product.name}</div><div className="text-[11px] text-muted tnum">{money(a.product.list_price * a.qty)} at list</div></div>
                        <Stepper value={a.qty} onChange={(v) => setAdds(adds.map((x, j) => (j === i ? { ...x, qty: v } : x)))} />
                        <button onClick={() => setAdds(adds.filter((_, j) => j !== i))} className="text-muted hover:text-rose-700"><X className="size-4" /></button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {tab === "client" && (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <div className="card p-5">
                <div className="text-[13.5px] font-semibold">Client</div>
                <p className="mb-4 mt-0.5 text-[12px] text-muted">The client region decides the quote currency, the tax treatment and competitor coverage.</p>
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2"><Field label="Organisation"><input className="input" value={client.name} onChange={(e) => setClient({ ...client, name: e.target.value })} /></Field></div>
                  <Field label="Region"><select className="input" value={client.country} onChange={(e) => {
                    // A new region brings its own currency; the reviewer can still pick another below.
                    const next = countries.data?.find((c) => c.code === e.target.value);
                    setClient({ ...client, country: e.target.value, region: "" });
                    if (next) setCurrency(next.currency);
                  }}>
                    {countries.data?.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></Field>
                  <Field label="State / province"><select className="input" value={client.region} onChange={(e) => setClient({ ...client, region: e.target.value })} disabled={!selectedCountry?.regions.length}>
                    <option value="">{selectedCountry?.regions.length ? "Not specified" : "Not applicable"}</option>
                    {selectedCountry?.regions.map((r) => <option key={r}>{r}</option>)}</select></Field>
                  <div className="col-span-2"><Field label="Tax registration" hint="A registration number enables reverse charge on cross-border services."><input className="input" value={client.tax_id} onChange={(e) => setClient({ ...client, tax_id: e.target.value })} placeholder="e.g. VAT number, GSTIN, ABN or TRN" /></Field></div>
                </div>
                <div className="mt-5">
                  <div className="mb-1.5 text-[12px] font-medium text-ink-soft">Buyer segment</div>
                  <Segmented value={client.segment as (typeof SEGMENTS)[number]} onChange={(v) => setClient({ ...client, segment: v })} items={SEGMENTS.map((s) => ({ value: s, label: s === "smb" ? "SMB" : titleCase(s) }))} />
                  <p className="mt-2 text-[11.5px] text-muted">Segment sets how price-sensitive the win-probability model treats the buyer.</p>
                </div>
              </div>
              <div className="card p-5">
                <div className="text-[13.5px] font-semibold">Commercial terms</div>
                <p className="mb-4 mt-0.5 text-[12px] text-muted">Delivery terms decide whether destination tax is charged or the supply is zero-rated.</p>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Delivery terms (Incoterm)"><select className="input" value={incoterm} onChange={(e) => setIncoterm(e.target.value)}>
                    {INCOTERMS.map((i) => <option key={i} value={i}>{i || "Delivered to site (domestic)"}</option>)}</select></Field>
                  <Field label="Quote currency"><select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>{currencies.map((c) => <option key={c}>{c}</option>)}</select></Field>
                </div>
                <div className="mt-5">
                  <div className="flex items-center justify-between text-[12.5px]"><span className="font-medium text-ink-soft">Exchange-rate buffer</span><span className="tnum font-semibold">{buffer.toFixed(1)}%</span></div>
                  <input type="range" min={0} max={5} step={0.5} value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} disabled={currency === base} className="mt-2 w-full accent-[#0b1220] disabled:opacity-40" />
                  <p className="mt-1 text-[11.5px] text-muted">{currency === base ? `Not applied when quoting in ${base}, the catalogue currency.` : "Protects margin against currency movement during the validity period."}</p>
                </div>
                {loc && <div className="mt-5 rounded-xl bg-[#f6f7f9] px-4 py-3 text-[12px] text-muted">Currently <span className="font-medium text-ink">{loc.tax_summary}</span> for {loc.jurisdiction}.</div>}
              </div>
            </div>
          )}
        </div>

        {/* live footer */}
        <footer className="border-t border-line bg-white px-7 py-4">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
            <div><div className="label">Net revenue</div><div className="mt-0.5 text-[16px] font-semibold tnum">{money(econ.revenue, base)}</div>
              {before && <div className="text-[11px] text-muted tnum">was {money(before.revenue, base)}</div>}</div>
            <div><div className="label">Gross margin</div><div className={clsx("mt-0.5 text-[16px] font-semibold tnum", econ.margin < 8 ? "text-rose-700" : "text-ink")}>{econ.margin.toFixed(1)}%</div>
              {before && <div className="text-[11px] text-muted tnum">was {before.margin_pct.toFixed(1)}%</div>}</div>
            <div><div className="label">Below floor</div><div className={clsx("mt-0.5 text-[16px] font-semibold tnum", econ.below ? "text-rose-700" : "text-ink")}>{econ.below}</div>
              <div className="text-[11px] text-muted">line(s)</div></div>
            <div className="min-w-[220px] flex-1"><input className="input" placeholder="Note for the record (optional)" value={note} onChange={(e) => setNote(e.target.value)} /></div>
            <div className="flex gap-2">
              <Button onClick={discard} disabled={!changeCount}>Discard</Button>
              <Button variant="primary" disabled={!changeCount} loading={apply.isPending} onClick={() => apply.mutate()}>
                {changeCount ? `Apply ${changeCount} change${changeCount > 1 ? "s" : ""} and re-price` : "No changes yet"}
              </Button>
            </div>
          </div>
          {(apply.isError || reset.isError) && <div className="mt-2 text-[12.5px] text-rose-700">{((apply.error ?? reset.error) as Error).message}</div>}
        </footer>
      </aside>
    </div>,
    document.body,
  );
}
