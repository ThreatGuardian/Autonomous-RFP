# Architecture and methods

This document describes how each part of Tenderdesk works, in enough detail to
reproduce or extend it.

## 1. Pipeline and agents

```
RFP text ─▶ RFP Parser ─▶ Internal Pricing ─▶ Competitive Strategy ─▶ Currency & Tax ─▶ Proposal Drafting
             (parsed)       (costing)            (strategy)              (localisation)     (proposal + PDFs)
```

* **Contract.** Every agent implements `run(ctx, log) -> message`
  (`app/agents/base.py`). It declares the message keys it `consumes` and the one
  key it `produces`. Agents never call each other.
* **Messages** are Pydantic models (`app/agents/messages.py`), so every
  hand-off is typed, validated and serialisable.
* **Stage log.** Each agent appends ordered `info`, `decision` and `warning`
  entries with structured data. The UI's Activity tab renders them as the
  decision trail.
* **Orchestrator** (`app/agents/orchestrator.py`)
  * runs requests on a `ThreadPoolExecutor`, so several RFPs proceed in
    parallel;
  * persists each stage run (status, timings, summary, log) and each message on
    the `rfps` row;
  * re-runs from any stage: reviewer overrides re-run costing → drafting, while
    intake is reused;
  * increments the proposal version on every re-draft, and re-queues
    interrupted work after a restart;
  * on approval, re-renders the documents without the draft watermark and
    stamps the approval into the memo.

Status lifecycle: `queued → processing → review → approved | rejected`,
with `failed` on error, and `reopen` / `retry` to go back.

## 2. Language processing

`app/nlp/text.py`

* NFKC normalisation and punctuation unification. Wide gaps (3+ spaces) are kept
  as tab column separators so layout-extracted PDF tables survive.
* Accent folding (`Präzision → prazision`).
* Tokeniser that keeps model numbers intact, splits number+unit tokens
  (`16gb → 16 gb`), and emits compound parts (`wi-fi → wi-fi, wi, fi`).
* Suffix stemmer (Porter step-1 style) with double-consonant repair
  (`shipping → ship`).
* Number words (`one hundred and twenty-five`, `a dozen`, `2 lakh`).
* Sentence splitting that respects bullets and numbered lists.

`app/nlp/extractors.py` — rule-based extraction:

| Entity | Method |
|--------|--------|
| Client | Labelled fields (`Issued by:`, `Client:` …), else the first header line carrying an organisation suffix (Ltd, GmbH, LLC, University, Hospital, District …); reconciled against the customer master by token Jaccard ≥ 0.6 |
| Location | Gazetteer of 30 countries with states and cities. A delivery-address field wins; otherwise country votes by mention count (region mentions vote for their country), ties broken by first mention; city = first sub-regional mention |
| Currency | ISO codes, symbols and names, weighted ×2 inside pricing sentences (`quote`, `price`, `currency`, `invoice`). `$` is resolved by country (USD/SGD/AUD/CAD/NZD). Otherwise the delivery country's currency, then the company's |
| Dates | ISO, `15 November 2026`, `November 15, 2026`, numeric (day-first unless the client is in the US), assigned a role (due / delivery / issued) by the preceding context |
| Terms | Incoterms, delivery window (days/weeks/months), payment days (`net 30`, `within 45 days of invoice`), advance %, minimum warranty, price weight %, lowest-price award |
| Segment | Client-name cues, then document cues (education, healthcare, public, enterprise), else SMB |

`app/nlp/line_items.py` — item extraction:

* **Tables.** Pipe, tab or wide-gap tables are detected by a header row
  containing quantity and description columns. Empty cells are preserved so
  columns stay aligned. Specification columns are appended to the description.
* **Quantities** in priority order: labelled (`Qty: 4`), `N x item`,
  `N units of`, `N units`, leading count, trailing count after a separator, then
  number words. Numbers attached to specification units (`GB`, `inch`, `"`,
  `port`, `VA`, `years` …) are never quantities.
* **Specification** extraction: RAM, storage (with SSD/HDD), screen size, port
  count, PoE, VA rating, CPU tier, Xeon family, resolution, Wi-Fi generation,
  UPS topology, drive bays. Brand is also extracted.

## 3. Trained models

All three live in `app/ml/`. They are trained on first start and persisted with
joblib in `var/models`. The **Retrain models** button (Models & data page)
rebuilds them.

### 3.1 Clause classifier

* Features: TF-IDF over stemmed unigrams+bigrams ∪ TF-IDF over character 2–5-grams.
* Model: multinomial logistic regression (C = 8).
* Labels: `line_item, delivery, payment, warranty_support, compliance, evaluation, submission, scope`.
* Corpus (`corpus.py`): a template grammar with slot fillers (quantities, items,
  specs, places, dates, currencies, certifications, …), random prefixes and
  casing noise.
* Evaluation: each label's templates are split into **training** and
  **held-out** families. The reported accuracy (~0.85) therefore measures
  generalisation to new phrasings, not memorisation.
* In the parser, a quantity-bearing sentence becomes a line item only if the
  classifier agrees (or the category model is confident). This is how "within
  30 days" is kept from becoming 30 units. Clauses below 0.45 confidence are
  kept as context rather than mislabelled.

### 3.2 Category classifier

The same architecture, trained on catalogue-derived phrases plus a curated
phrase bank per category (19 categories, ~98% held-out accuracy). Its output
distribution is used twice:

* as a ranking prior during retrieval (`boost = 1 + 0.35 · p(category)`);
* as a coherence factor on the match score:
  `score × (0.55 + 0.45 · min(1, p(product category) / p(top category)))`.

### 3.3 Win-probability model

* Data: a 2,400-row bid ledger (`deal_history`). It was synthesised once from a
  latent market model that the learner never sees, exactly as a CRM export
  would be.
* Features (`featurize`): price gap `r − 1`, where `r` = our price ÷ best
  competitor price; gap × buyer-segment interactions (segment-specific
  elasticity); warranty difference in years and lead-time difference in weeks,
  both clipped to the training support; bundled value-add; repeat customer;
  segment dummies.
* Model: standardised logistic regression. Held-out AUC ≈ 0.75, Brier ≈ 0.19.
* The learned coefficients match the latent market. Public-sector buyers are
  the most price-sensitive and healthcare the least; a bundle raises the odds
  by ≈1.75×.

## 4. Retrieval (the "R" in RAG)

`app/rag/index.py` — `HybridIndex` fuses three signals, each bounded to [0, 1]:

```
bm25_sat = BM25 / (BM25 + 6)                     (k1 = 1.4, b = 0.72)
semantic = cos( SVD(TF-IDF(query)), SVD(TF-IDF(doc)) )   (latent semantic analysis)
lexical  = cos( char3-5gram(query), char3-5gram(doc) )
score    = 0.40·bm25_sat + 0.35·semantic + 0.25·lexical
```

Because the fused score is absolute, callers can apply thresholds. Maximal
marginal relevance (`λ·relevance − (1−λ)·max similarity to selected`)
diversifies the passages it returns.

**Catalogue store.** Products are indexed with name, brand, category, MPN,
description, specs and keywords. Candidates are re-ranked by:

```
match = 0.6·retrieval + 0.4·spec_fit   (spec_fit ∈ [0,1], when specs were requested)
      ± brand adjustment (+0.08 / −0.10)
      × category coherence
matched ≥ 0.42,  ambiguous ≥ 0.30,  otherwise unmatched (excluded from pricing, flagged)
```

**Knowledge store.** Ten markdown documents are chunked by section. Sentences
are indexed with their document and section titles as context. `evidence()` is
two-stage: rank sections first, then sentences within the top sections,
combining `0.55·section + 0.45·sentence`. This stops a stray number match
("30 minutes" vs "30 days") from pulling in an off-topic sentence. For
certification requirements, each named standard (ISO 27001, GDPR, DPDP …) is
retrieved and verified separately.

## 5. Pricing strategy engine

`app/pricing/strategy.py`

For each costed line with market offers (normalised to INR through the FX
service, with unreliable sources filtered out):

1. **Grid.** 90 prices from the margin floor to list price.
2. **Configurations.** No bundle, plus each eligible value-add. If the best
   competitor is below landed cost, only bundled configurations are allowed:
   this is the value-differentiation pivot.
3. **Hard constraints.** `price ≥ floor`; `price − bundle cost ≥ floor`;
   `bundle cost ≤ 6% × price`.
4. **Win probability.** The model receives an award-adjusted price ratio,
   `r' = 1 + (r − 1)·(price weight / 50)`, clamped to [0.6, 2.0]× sensitivity.
   L1 tenders therefore count price twice as heavily.
5. **Objective.** `E = (price − cost − bundle cost) · qty · P(win)`. Maximise
   among configurations with `P(win) ≥ 0.20`. If none qualify, choose the
   highest-P(win) compliant offer and say so.
6. **Classification.** Value differentiation · Floor defence · Competitive
   undercut · Competitive match (within 2%) · Margin capture · Value premium ·
   Standard pricing (no market) · Reviewer override.
7. **Explanation.**
   * Market facts and our cost basis.
   * Why matching was rejected, including the per-unit and per-line loss.
   * What was bundled, and whether it beats the best unbundled price (or, if
     not, that the pivot is policy).
   * The recommendation with its margin, P(win) and expected profit.
   * The feasible matching alternative.
   * The buyer's price elasticity.
   * A scenario table and a 30-point win/profit curve.

Reviewer overrides (price, bundle, SKU, quantity, exclusion) are evaluated
with the same model. They are flagged, for example "Below margin floor" or
"Loss-making price".

## 6. Currency and tax

`app/finance/currency.py`

* Provider chain: ECB rates via Frankfurter → open.er-api.com → database cache
  (TTL 12 h) → reference table. A fallback source is marked **stale**, and the
  UI and memo show a warning.
* Every rate is stored against INR; cross rates are derived.
* Non-INR quotations add a configurable FX buffer (default 1.5%).

`app/finance/tax.py` — rules by jurisdiction and product tax category
(`goods_standard`, `software`, `services`):

| Situation | Treatment |
|-----------|-----------|
| India, same state as supplier (Maharashtra) | CGST + SGST (rate split in half) |
| India, other state / unknown | IGST |
| Export on EXW, FCA, FOB, CIF, CPT, CIP, DAP, DPU | Zero-rated under LUT; destination rate shown as payable by the importer |
| Export on DDP | Destination VAT/GST/sales tax with regional and category brackets (e.g. California exempts software and services; Quebec GST + QST) |
| Cross-border B2B services and licences with a client tax ID (non-US) | Reverse charge (0%, noted) |

## 7. Drafting and documents

`app/agents/drafting_agent.py` plans each section from structured facts.

* **Cover letter**: acknowledgement, scope sentence, retrieved company profile,
  the closest case study by segment and scope, total and validity, included
  value.
* **Executive summary** and grouped highlights.
* **Compliance matrix**: status rules for warranty (required months vs quoted,
  including bundled extensions), delivery (lead time + transit vs required),
  payment and certifications (per-standard evidence).
* **Delivery plan**: milestones computed from the longest lead time plus transit
  and installation, and retrieved delivery/deployment passages.
* **Terms**: validity, incoterm, payment, tax notes, exchange basis.

`app/services/pdf_renderer.py` (ReportLab, Inter font)

* **Quotation**: branded first page, summary strip, cover letter, commercial
  schedule (per-line tax), totals, inclusions, client-safe pricing basis,
  compliance matrix, delivery milestones, terms, acceptance block, bank
  details. A DRAFT watermark stays until approval. Costs never appear; a test
  enforces this.
* **Pricing memo** (landscape, confidential): KPIs, line economics, rationale and
  scenario table per line, FX/tax basis, approval stamp.

### Bid analysis report

`app/services/report_renderer.py` produces an executive document in a
presentation style: a serif display face (Source Serif 4), letter-spaced
section labels, rounded gradient score bars, soft cards and a milestone
timeline. It contains:

* the verdict and headline economics;
* KPI tiles;
* win probability by line;
* margin structure (cost, services, margin);
* how the price was set;
* the strategy mix;
* key pricing decision cards;
* the delivery roadmap;
* requirement coverage;
* risks to weigh and next steps.

## 8. Reviewer adjustments and sign-in

* **Overrides** are stored on the request, and the approval events record them.
  Line overrides cover price, service, quantity, SKU and exclusion.
  `apply_review_edits` in the orchestrator merges the client and terms
  corrections and the added catalogue items into the parsed request. It is
  idempotent: added lines are rebuilt from the override list on every run, and
  each keeps a stable line number. Costing, strategy, tax and drafting then
  re-run.
* **Authentication** (`app/api/auth.py`, `app/services/auth.py`):
  * PBKDF2-SHA256 password hashes;
  * HMAC-SHA256-signed, expiring, HTTP-only session cookies;
  * middleware protecting `/api/*`;
  * federated sign-in for Google and SSO, which accepts the identity returned
    by the provider step.

## 9. Data model

`users`, `products`, `price_tiers`, `value_adds`, `customers`, `deal_history`,
`tax_rules`, `fx_rates`, `rfps` (with JSON columns for each message),
`stage_runs`, `approval_events`. The seeder is idempotent, so edits made
through the Catalogue screen survive restarts.

## 10. Mock competitor market

`app/market/service.py` is a separate FastAPI app with `X-Api-Key`
authentication and its own data file.

* Seven competitors, with regions served, category positioning, warranty, lead
  time, reliability and typical bundles.
* The price for a competitor/product on day *d* is:
  `street price × category factor (or promotion) × exp(weekly mean-reverting walk) × (1 − volume discount)`.
* Promotions deliberately undercut reseller landed cost on several SKUs, so the
  value-differentiation path is exercised.

It is mounted at `/market-api`, and can also run standalone on its own port
(`TD_MARKET_API_URL`).
