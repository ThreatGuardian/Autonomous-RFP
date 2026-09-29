import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { Page, PageHeader } from "../components/layout/Shell";
import { Badge, Button, Card, Skeleton, Stat, StatGrid } from "../components/ui";
import { api } from "../lib/api";
import { date } from "../lib/format";

export default function Models() {
  const qc = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: api.models });
  const retrain = useMutation({ mutationFn: api.retrain, onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }) });
  const [q, setQ] = useState("ISO 27001 certification");
  const [query, setQuery] = useState(q);
  const search = useQuery({ queryKey: ["knowledge", query], queryFn: () => api.knowledge(query), enabled: query.length > 1 });
  const m = models.data;
  const coef = Object.entries((m?.win_model?.coefficients ?? {}) as Record<string, number>);
  const maxCoef = Math.max(1, ...coef.map(([, v]) => Math.abs(v)));

  return (
    <>
      <PageHeader title="Models & data" description="The statistical models and indexes behind parsing, product matching, pricing and proposal writing — all trained and run in-house."
        actions={<Button loading={retrain.isPending} onClick={() => retrain.mutate()}>Retrain models</Button>} />
      <Page className="space-y-6">
        {!m ? <Skeleton className="h-28" /> : (
          <StatGrid cols={4}>
            <Stat label="Clause classifier" value={`${(m.clause_classifier.metrics.holdout_accuracy * 100).toFixed(1)}%`} hint="Accuracy on unseen phrasings" />
            <Stat label="Category classifier" value={`${(m.category_classifier.metrics.holdout_accuracy * 100).toFixed(1)}%`} hint="Held-out accuracy" />
            <Stat label="Win-probability model" value={m.win_model.metrics.holdout_auc.toFixed(3)} hint="ROC AUC on held-out bids" />
            <Stat label="Knowledge base" value={`${m.knowledge_base.sections} sections`} hint={`${m.knowledge_base.sentences} indexed sentences`} />
          </StatGrid>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <Card title="Win-probability model" subtitle={m ? `Logistic regression on ${m.deal_history.deals.toLocaleString()} historical bids · base win rate ${(m.deal_history.win_rate * 100).toFixed(0)}%` : undefined}>
            <p className="mb-4 text-[12.5px] text-muted">Effect of each factor on the log-odds of winning. Price effects are per unit of price ratio to the best competitor; negative values reduce the chance of winning.</p>
            <ul className="space-y-2">
              {coef.map(([k, v]) => (
                <li key={k} className="grid grid-cols-[170px_1fr_60px] items-center gap-3 text-[12px]">
                  <span className="truncate text-ink-soft">{k.replace(/_/g, " ").replace("×", " × ")}</span>
                  <div className="relative h-2 rounded-full bg-[#f1f2f4]">
                    <div className={`absolute top-0 h-2 rounded-full ${v < 0 ? "bg-rose-500" : "bg-emerald-600"}`}
                      style={{ left: v < 0 ? `${50 - (50 * Math.abs(v)) / maxCoef}%` : "50%", width: `${(50 * Math.abs(v)) / maxCoef}%` }} />
                    <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-line-strong" />
                  </div>
                  <span className="text-right tnum">{v.toFixed(2)}</span>
                </li>
              ))}
            </ul>
            {m && <p className="mt-4 border-t border-line pt-3 text-[12px] text-muted">Including a value-added service multiplies the odds of winning by {m.win_model.odds_ratio_bundled}. Brier score {m.win_model.metrics.holdout_brier}. Trained {date(m.win_model.trained_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}.</p>}
          </Card>

          <Card title="Text models" subtitle="TF-IDF word and character n-gram features with multinomial logistic regression">
            {m && (
              <div className="space-y-5 text-[12.5px]">
                <div>
                  <div className="flex items-center justify-between"><span className="font-medium">Clause classifier</span><span className="text-muted">{m.clause_classifier.metrics.train_samples.toLocaleString()} training sentences</span></div>
                  <p className="mt-1 text-muted">Labels every sentence of a request as a line item or a delivery, commercial, warranty, compliance, evaluation, submission or context clause. Evaluated on template families never seen in training (macro F1 {m.clause_classifier.metrics.holdout_macro_f1}).</p>
                  <div className="mt-2 flex flex-wrap gap-1">{m.clause_classifier.labels.map((l: string) => <Badge key={l}>{l.replace(/_/g, " ")}</Badge>)}</div>
                </div>
                <div className="border-t border-line pt-4">
                  <div className="flex items-center justify-between"><span className="font-medium">Category classifier</span><span className="text-muted">{m.category_classifier.labels.length} categories</span></div>
                  <p className="mt-1 text-muted">Predicts the product category of a requested item. Its probabilities steer catalogue retrieval and penalise implausible matches.</p>
                </div>
                <div className="border-t border-line pt-4">
                  <div className="font-medium">Hybrid retrieval</div>
                  <p className="mt-1 text-muted">Okapi BM25, latent semantic vectors and character n-grams fused into one relevance score; used for catalogue matching ({m.catalogue_index.documents} products) and for grounding proposal text in the knowledge base.</p>
                </div>
              </div>
            )}
          </Card>
        </div>

        <Card title="Knowledge base search" subtitle="Test what evidence the drafting stage would retrieve for a requirement">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
            <div className="relative flex-1"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-subtle" />
              <input className="input pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. next business day on-site support" /></div>
            <Button type="submit" variant="primary">Search</Button>
          </form>
          {search.data && (
            <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <div className="label mb-2">Best supporting sentences</div>
                <ul className="space-y-2">
                  {search.data.evidence.map((e, i) => (
                    <li key={i} className="rounded-lg border border-line px-3 py-2.5 text-[12.5px]">
                      <div>“{e.text}”</div><div className="mt-1 flex justify-between text-[11.5px] text-muted"><span>{e.section}</span><span className="tnum">{e.score.toFixed(3)}</span></div>
                    </li>
                  ))}
                  {search.data.evidence.length === 0 && <li className="text-[12.5px] text-muted">No passage is relevant enough.</li>}
                </ul>
              </div>
              <div>
                <div className="label mb-2">Ranked sections</div>
                <table className="table-base rounded-lg border border-line">
                  <thead><tr><th>Section</th><th className="!text-right">BM25</th><th className="!text-right">Semantic</th><th className="!text-right">Lexical</th><th className="!text-right">Score</th></tr></thead>
                  <tbody>
                    {search.data.sections.map((s) => (
                      <tr key={s.id}><td><div className="font-medium">{s.meta.section}</div><div className="text-[11.5px] text-muted">{s.meta.title}</div></td>
                        <td className="text-right tnum text-muted">{s.signals.bm25.toFixed(2)}</td><td className="text-right tnum text-muted">{s.signals.semantic.toFixed(2)}</td>
                        <td className="text-right tnum text-muted">{s.signals.lexical.toFixed(2)}</td><td className="text-right tnum font-medium">{s.score.toFixed(3)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
      </Page>
    </>
  );
}
