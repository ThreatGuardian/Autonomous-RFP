import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check } from "lucide-react";
import { CountryTag, WarningList } from "../../components/domain";
import { Badge, Card, KeyValue } from "../../components/ui";
import { api } from "../../lib/api";
import type { Requirement, RfpDetail } from "../../lib/types";
import { date, titleCase } from "../../lib/format";
import { MotionRow, rowMotion } from "../../components/motion";

const TYPE_LABEL: Record<string, string> = {
  delivery: "Delivery", payment: "Commercial", warranty_support: "Warranty & support", compliance: "Compliance",
  evaluation: "Evaluation", submission: "Submission", scope: "Context", technical: "Technical", eligibility: "Eligibility",
  line_item: "Line item",
};
// Types the clause model can learn; a reviewer's correction becomes a training label.
const LEARNABLE = ["scope", "line_item", "delivery", "payment", "warranty_support", "compliance", "evaluation", "submission"];

function TypeCell({ rfpId, r }: { rfpId: number; r: Requirement }) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (type: string) => api.labelRequirement(rfpId, r.id, type),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rfp", rfpId] }),
  });
  if (!LEARNABLE.includes(r.type)) return <span className="text-[12.5px]">{TYPE_LABEL[r.type] ?? r.type}</span>;
  return (
    <div>
      <select value={r.type} disabled={save.isPending} onChange={(e) => save.mutate(e.target.value)}
        title="Correct the type — the model learns from it"
        className={clsx("-ml-1 max-w-full cursor-pointer rounded-md border border-transparent bg-transparent px-1 py-0.5 text-[12.5px] outline-none transition-colors hover:border-line hover:bg-white focus:border-line",
          r.type === "scope" ? "text-muted" : "text-ink")}>
        {LEARNABLE.map((t) => <option key={t} value={t}>{TYPE_LABEL[t] ?? "Line item"}</option>)}
      </select>
      <div className="text-[11px] text-muted tnum">
        {r.reviewed ? <span className="inline-flex items-center gap-1 text-emerald-700"><Check className="size-3" /> Corrected by reviewer</span>
          : `${Math.round(r.confidence * 100)}% confidence`}
      </div>
    </div>
  );
}

const STATUS_TONE: Record<string, "green" | "amber" | "red" | "neutral" | "blue"> = {
  Complies: "green", "Complies with note": "amber", "Clarification required": "blue", Deviation: "red", Noted: "neutral",
};

export function RequirementsTab({ rfp }: { rfp: RfpDetail }) {
  const p = rfp.parsed;
  if (!p) return null;
  const c = p.client;
  const t = p.terms;
  const compliance = new Map((rfp.proposal?.compliance ?? []).map((r) => [r.req_id ?? r.ref, r]));

  return (
    <div className="space-y-5">
      <WarningList items={p.warnings} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card title="Client">
          <KeyValue items={[
            { label: "Organisation", value: c.name, hint: c.repeat_customer ? "Existing customer" : c.customer_id ? "Known customer" : "New customer" },
            { label: "Contact", value: c.contact_name, hint: c.email },
            { label: "Delivery location", value: <CountryTag code={c.country} name={[c.city, c.region, c.country_name].filter(Boolean).join(", ")} /> },
            { label: "Buyer segment", value: titleCase(c.segment), hint: `From ${c.segment_source}` },
            { label: "Tax registration", value: c.tax_id },
            { label: "Client reference", value: p.client_reference },
          ]} />
        </Card>
        <Card title="Commercial terms">
          <KeyValue items={[
            { label: "Quote currency", value: p.currency.code, hint: p.currency.source === "explicit" ? "Stated in the request" : p.currency.source === "country_default" ? "Default for delivery country" : "Company default" },
            { label: "Delivery terms", value: t.incoterm ?? "Delivered to site", hint: t.incoterm_source === "default" ? undefined : titleCase(t.incoterm_source) },
            { label: "Required delivery", value: t.delivery_days ? `${t.delivery_days} days from order` : null },
            { label: "Payment", value: t.payment_days ? `${t.payment_days} days from invoice` : null, hint: t.advance_pct !== null ? `${t.advance_pct}% advance` : undefined },
            { label: "Warranty required", value: t.warranty_months_required ? `${t.warranty_months_required} months` : null },
            { label: "Award basis", value: t.lowest_price_award ? "Lowest compliant bid" : t.price_weight_pct ? `Price weighted ${t.price_weight_pct}%` : "Not stated" },
            { label: "Submission deadline", value: date(p.due_date) },
            { label: "Issued", value: date(p.issued_on) },
          ]} />
        </Card>
      </div>

      <Card title="Requested items" subtitle="Each request line resolved to a catalogue product by text retrieval and specification fit" bodyClassName="p-0">
        <table className="table-base">
          <thead><tr><th className="w-10">#</th><th>As requested</th><th className="!text-right">Qty</th><th>Extracted specification</th><th>Matched product</th><th className="!text-right">Confidence</th></tr></thead>
          <tbody>
            {p.line_items.map((it, rowIndex) => {
              const match = it.candidates.find((c2) => c2.sku === it.selected_sku);
              return (
                <MotionRow {...rowMotion(rowIndex)} key={it.line_no}>
                  <td className="text-muted tnum">{it.line_no}</td>
                  <td className="max-w-[320px]"><div className="font-medium">{it.description}</div><div className="text-[11.5px] text-muted">Quantity from {it.quantity_source}</div></td>
                  <td className="text-right tnum">{it.quantity.toLocaleString()}</td>
                  <td className="max-w-[240px]">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(it.specs).map(([k, v]) => <Badge key={k}>{titleCase(k)}: {String(v)}</Badge>)}
                      {it.brand && <Badge tone="blue">Brand: {it.brand}</Badge>}
                      {!Object.keys(it.specs).length && !it.brand && <span className="text-muted">—</span>}
                    </div>
                  </td>
                  <td className="max-w-[260px]">
                    {match ? <><div className="truncate">{match.name}</div><div className="font-mono text-[11.5px] text-muted">{match.sku}</div></> : <span className="text-rose-700">No suitable product</span>}
                  </td>
                  <td className="text-right">
                    <Badge tone={it.status === "matched" ? "green" : it.status === "ambiguous" ? "amber" : "red"}>{Math.round(it.match_confidence * 100)}%</Badge>
                  </td>
                </MotionRow>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card title="Requirements and our response" subtitle="Every clause classified by type and answered in the quotation's compliance section. Correct a type and the classifier learns from it." bodyClassName="p-0">
        <table className="table-base">
          <thead><tr><th className="w-12">Ref</th><th>Requirement</th><th className="w-[150px]">Type</th><th className="w-[170px]">Status</th><th>Response</th></tr></thead>
          <tbody>
            {p.requirements.map((r, rowIndex) => {
              const row = compliance.get(r.id);
              return (
                <MotionRow {...rowMotion(rowIndex)} key={r.id}>
                  <td className="font-mono text-[11.5px] text-muted">{r.clause ?? r.id}{r.page && p.document?.long_form ? <div className="font-sans text-[11px] text-subtle">p. {r.page}</div> : null}</td>
                  <td className="max-w-[380px] text-ink-soft">{r.text}</td>
                  <td><TypeCell rfpId={rfp.id} r={r} /></td>
                  <td>{row ? <Badge tone={STATUS_TONE[row.status]}>{row.status}</Badge> : <span className="text-muted">—</span>}</td>
                  <td className="max-w-[360px]">
                    {row ? <><div>{row.response}</div>{row.evidence[0] && <div className="mt-1 text-[11.5px] text-muted">“{row.evidence[0].text}” <span className="text-subtle">— {row.evidence[0].section}</span></div>}</> : <span className="text-muted">Background</span>}
                  </td>
                </MotionRow>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
