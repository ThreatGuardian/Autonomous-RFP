# Tenderdesk — Autonomous RFP Response & Competitive Quotation

Tenderdesk turns a client's request for proposal into a priced, tax-correct,
branded quotation in seconds. A reviewer then approves it. The system reads the
request, checks internal cost and stock, looks up competitor prices, and
chooses a price for every line. When a competitor is priced **below our own
landed cost**, it does not follow them down. It holds a compliant price and
competes on value instead, by bundling warranty or services. Every decision
comes with a plain-language rationale.

**No large language model is used anywhere.** Parsing, matching, pricing and
writing all use explicit rules, classical information retrieval, and models
trained in this repository with scikit-learn.

![Landing page](docs/screenshots/00-landing.png)

---

## Contents

1. [What it does](#what-it-does)
2. [Deliverables mapped to features](#deliverables-mapped-to-features)
3. [Architecture](#architecture)
4. [Quick start](#quick-start)
5. [Using the application](#using-the-application)
6. [How the intelligence works](#how-the-intelligence-works)
7. [Project structure](#project-structure)
8. [API](#api)
9. [Testing](#testing)
10. [Build phases](#build-phases)

---

## What it does

| Step | Stage (agent) | Result |
|------|---------------|--------|
| 1 | **RFP Parser Agent** | Extracts the client, contact, delivery location, currency, deadlines, commercial terms, every requested item with its specification, and every requirement clause. Matches each item to a catalogue SKU. |
| 2 | **Internal Pricing Agent** | Reads landed cost, list price, margin floor, volume tier, stock, lead time and eligible bundle services from the internal pricing database. A warranty the tender mandates is priced into the line rather than given away. |
| 3 | **Tender Compliance Agent** | For long tenders: checks every eligibility criterion against the company profile, every specification row against the offered product, and every commercial and contractual clause against policy. Produces a clause-by-clause compliance matrix, risk flags, a bid-documents checklist and a **bid / no-bid recommendation**. |
| 4 | **Competitive Strategy Agent** | Queries the competitor market API and normalises offers to rupees. Picks the price and bundle that maximise expected profit within policy, and applies the value-differentiation pivot when a competitor is below cost. |
| 5 | **Currency & Tax Agent** | Converts to the client's currency (live FX with fallbacks and a hedging buffer) and applies jurisdiction tax: GST/IGST, destination VAT/GST/sales tax, export zero-rating and reverse charge. |
| 6 | **Proposal Drafting Agent** | Writes the proposal from retrieved knowledge-base evidence: cover letter, executive summary, compliance matrix, delivery plan and terms. Renders a **client quotation**, a **compliance statement**, a **bid report** and a **confidential pricing memo** as PDFs. |

### Long tenders (10–15 pages)

A real tender is not a list of items. The parser reads the document's structure
first:

* **Layout.** Pages, fonts and ruled tables from PDF (PyMuPDF), Word heading
  styles and page breaks from DOCX. Running headers and footers ("Tender No. …
  Page 3 of 14") are removed, and tables split across pages are stitched back
  together. Scanned pages are reported, and OCR'd when Tesseract is installed.
* **Section tree.** Numbered sections, "Section III", "Annexure-2" and styled
  headings are recognised; numbered *clauses* ("2.3.1 The bid shall …") are
  told apart from headings. Each section is typed as notice, instructions,
  eligibility, scope, technical specification, bill of quantities, commercial,
  evaluation, conditions or forms.
* **What it extracts.** Key dates with times (queries, pre-bid meeting,
  submission, opening), EMD and MSE exemption, estimated value, bid validity,
  performance security, liquidated damages, payment milestones, the evaluation
  method (L1 or QCBS with its weights, minimum technical score and marking
  scheme) and every pre-qualification criterion with its parameters.
* **Items only from the schedule.** Line items are taken from the bill of
  quantities, so "must have supplied 500 laptops" in the eligibility section is
  never priced. Each schedule line is linked to its technical-specification
  section ("as per specification 5.1") and inherits those specs for matching.
* **Obligations.** Every clause gets its clause number, page, obligation
  strength (mandatory / desirable / information), who it binds (bidder or
  buyer) and a category.

Two full sample tenders are included and can be processed from the New request
page in one click: an 11-page municipal PDF (L1, EMD with MSE exemption, 10
eligibility criteria, 10 specification tables) and an 11-page university RFP in
Word (QCBS 70:30, which the system correctly recommends **not** bidding for,
because ISO/IEC 20000-1 is not held and the offered server brand is not
authorised).

The reviewer works in the web console. They inspect each line's rationale,
adjust price, bundle, product match or currency, re-price, and approve. Approval
issues the final PDF without the draft watermark.

## Deliverables mapped to features

| Required deliverable | Where it lives |
|----------------------|----------------|
| Multi-agent framework with separated roles | `backend/app/agents/` — five agents behind one `Agent` contract, communicating only through typed messages (`messages.py`), coordinated by `orchestrator.py` |
| Mocked competitor database/API queried dynamically | `backend/app/market/service.py` — a separate FastAPI service (API-key auth, own data) queried over HTTP by `services/market_client.py`. Prices drift daily and include below-cost promotions |
| Professional PDF quotation with line items and margins | `backend/app/services/pdf_renderer.py` — client quotation (schedule, taxes, totals, inclusions, compliance, delivery plan, terms, acceptance) and internal memo (cost, floor, margin, win probability, scenarios, rationale) |
| Approval UI showing pricing logic and strategy reasoning | `frontend/src/pages/request/` — pricing table, line sheet with numbered rationale, price-position scale, win/profit curve, alternatives, competitor offers, overrides, approve/decline |
| Multi-currency and regional tax | `backend/app/finance/` — FX provider chain and tax engine (Indian GST split, US state sales tax with category brackets, Canadian GST/HST/PST/QST, EU/UK/Gulf/APAC VAT/GST, export zero-rating, reverse charge) |
| Relational database for pricing data | SQLAlchemy models in `backend/app/db/models.py` (SQLite by default; any SQLAlchemy URL works) |
| Currency conversion API | ECB rates via Frankfurter, then open.er-api.com, then a cached copy in the database, then a reference table |

## Architecture

```mermaid
flowchart LR
    UI[Review console<br/>React + TypeScript] -->|REST| API[FastAPI]
    API --> ORCH[Orchestrator<br/>worker pool]
    ORCH --> P[RFP Parser Agent]
    P --> C[Internal Pricing Agent]
    C --> S[Competitive Strategy Agent]
    S --> L[Currency & Tax Agent]
    L --> D[Proposal Drafting Agent]
    P -.-> ML1[(Clause classifier<br/>Category classifier)]
    P -.-> IDX1[(Catalogue index<br/>BM25 + LSA + n-grams)]
    C -.-> DB[(Pricing database)]
    S -->|HTTP| MKT[Market API<br/>mock service]
    S -.-> ML2[(Win-probability model)]
    L -.-> FX[FX providers]
    D -.-> KB[(Knowledge base index)]
    D --> PDF[Quotation PDF<br/>Pricing memo PDF]
```

Each agent reads the messages it depends on from the pipeline context and
writes exactly one message of its own. Every execution is stored as a stage
run: status, timing, summary and an ordered decision log. When a reviewer
changes a line, only the downstream stages re-run, and the proposal version
increments. Several requests are processed in parallel on a worker pool.

## Quick start

Requirements: **Python 3.10+** and **Node.js 18+**.

**macOS / Linux**

```bash
./run.sh
```

**Windows (PowerShell)**

```powershell
.\run.ps1
```

Then open **http://127.0.0.1:8000**. On first start the database is seeded and
the models are trained. This takes about ten seconds and happens once.

The product website opens first; **Sign in** or **Get started** leads to the
console at `/app`. Three sign-in methods are available:

* **Username and password.** Use the demo workspace (`priya` / `tenderdesk`) or
  create an account.
* **Continue with Google** and **Continue with SSO.** Federated sign-in; the
  provider step is simulated locally and would be replaced by Google OAuth /
  OpenID Connect or a SAML identity provider in production (see
  `backend/app/api/auth.py`).

Sessions are HMAC-signed, HTTP-only cookies. Passwords are stored as
PBKDF2-SHA256 hashes.

### Development mode

```bash
# terminal 1 — API with auto-reload
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# terminal 2 — web app with hot reload (proxies /api to :8000)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

To run the competitor market as a genuinely separate service:

```bash
cd backend
python -m uvicorn app.market.service:market_app --port 8100
export TD_MARKET_API_URL=http://127.0.0.1:8100   # then start the main API
```

Configuration options are listed in [`.env.example`](.env.example).

## Using the application

1. **New request** — drag in PDF, DOCX or TXT files (several at once are
   processed in parallel), or paste text. Seven sample requests are included in
   [`samples/`](samples/), covering domestic India (intra- and inter-state), UAE,
   United States, Germany, United Kingdom (PDF) and Singapore (DOCX). The text
   samples can also be loaded from the New request page.
2. **Request → Pricing** — every line shows cost, best competitor, our price,
   margin, win probability and strategy. Open a line to see the full rationale,
   the price-position scale, the win/profit curve, alternatives considered and
   competitor offers. You can override price, bundle, product or quantity, or
   exclude the line.
3. **Compliance** — the bid recommendation and its reasons, key dates with
   countdowns, tender data, the evaluation method, eligibility checked against
   the company profile, and the clause-by-clause matrix with a document outline,
   filters (deviations, clarifications, items to verify) and search. Open any
   clause to see the offered product, evidence and assessment basis, and record
   your own decision; the statement and report are regenerated. Risks to price
   in and the bid-documents checklist (ready / to prepare / to obtain) follow.
4. **Requirements** — extracted terms, item-to-product matching with confidence,
   and each clause with its location, type and compliance response.
5. **Quotation** — commercial schedule in the client's currency with taxes, cover
   letter, delivery plan, inclusions and an embedded PDF preview. You can change
   the quote currency or FX buffer here.
6. **Adjustment workbench** (Pricing → *Adjust quotation*) — one panel for
   every manual change, with a live revenue, margin and below-floor preview:
   * **Line items:** inline price, quantity and service editing; include or
     exclude lines; pick a product for unmatched lines; adjust all prices by a
     percentage; lift everything to the margin floor.
   * **Add items:** catalogue search, for items the client didn't list.
   * **Client & terms:** correct the organisation, country, state, tax
     registration, buyer segment, incoterm, currency and FX buffer.

   *Apply* sends everything as one re-price and records a note.
   *Reset to recommendations* clears all overrides.
7. **Approve** — issues the final quotation and records the approval in the memo
   and the bid report.

Every request produces these PDFs (under *Documents* in the request header):

* a **client quotation**;
* a **compliance statement** for long tenders: eligibility with documents,
  the clause-by-clause matrix grouped by the tender's own sections, the
  statement of deviations and the declaration;
* a confidential **pricing memo**;
* a **bid analysis report** for leadership, covering the recommendation, win
  probability by line, margin structure, key pricing decisions, delivery
  roadmap, requirement coverage, risks and next steps.

| | |
|---|---|
| ![Pricing](docs/screenshots/03-pricing.png) | ![Rationale](docs/screenshots/04-line-rationale.png) |
| ![Curve](docs/screenshots/05-price-position.png) | ![Requirements](docs/screenshots/06-requirements.png) |
| ![Quotation](docs/screenshots/07-quotation.png) | ![Activity](docs/screenshots/08-activity.png) |
| ![Market](docs/screenshots/09-market.png) | ![Models](docs/screenshots/10-models.png) |
| ![Sign in](docs/screenshots/00-sign-in.png) | ![Overview](docs/screenshots/01-overview.png) |
| ![Workbench — lines](docs/screenshots/11-workbench-lines.png) | ![Workbench — terms](docs/screenshots/12-workbench-terms.png) |
| ![Bid report page 1](docs/screenshots/13-bid-report-p1.png) | ![Bid report page 2](docs/screenshots/13-bid-report-p2.png) |
| ![Compliance review](docs/screenshots/14-compliance-review.png) | ![Compliance matrix](docs/screenshots/15-compliance-matrix.png) |
| ![Clause decision](docs/screenshots/16-clause-decision.png) | ![No-bid recommendation](docs/screenshots/17-no-bid.png) |
| ![Compliance statement](docs/screenshots/18-compliance-statement.png) | |

## How the intelligence works

A condensed version follows. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) has
the full detail and formulas.

**Language processing (no LLM).** A deterministic analyser handles accent
folding, unit-aware tokenisation (`16GB` → `16 gb`), compound splitting
(`ISO/IEC` → `iso`, `iec`), light stemming and English number words
("twenty-five", "a dozen", "2 lakh"). Header fields, addresses and headings are
recognised by rules. Locations are resolved with a gazetteer of 30 countries and
their states and cities.

**Trained models (scikit-learn), trained in this repository.**

* *Clause classifier* — TF-IDF word/bigram + character n-grams → logistic
  regression. Assigns eight clause types. Trained on a template-grammar corpus
  and evaluated on **template families never seen in training** (~85% accuracy).
* *Category classifier* — predicts the product category of a requested item
  (~98% held-out accuracy). Its probabilities act as a prior during catalogue
  retrieval and penalise implausible matches.
* *Win-probability model* — logistic regression on 2,400 historical bids, with
  segment-specific price elasticity, warranty and lead-time differences,
  bundled value-add and repeat-customer effects (AUC ≈ 0.75). The learned
  coefficients recover the market's true behaviour. For example, bundling
  multiplies the odds of winning by ≈1.75.

**Retrieval-augmented generation without an LLM.** A hybrid index fuses Okapi
BM25, latent semantic vectors (TF-IDF + truncated SVD) and character n-grams
into an absolute relevance score, with MMR for diversity. It is used twice:

* resolving free-text line items to SKUs, re-ranked by specification fit (RAM,
  storage, screen size, ports, PoE, VA rating, CPU tier and more), brand and
  category coherence;
* grounding the proposal. A two-stage search (sections, then sentences) pulls
  evidence from the company knowledge base into the cover letter, compliance
  matrix and delivery plan, with every source logged. Text is composed by
  sentence planning and templates, never free generation.

**Pricing strategy.** For each line the engine searches price × bundle to
maximise

```
E[profit] = (price − landed cost − bundle cost) × quantity × P(win | offer)
```

subject to hard guard-rails: price ≥ margin floor, bundle funded from margin
above the floor, and bundle cost ≤ 6% of price. P(win) is adjusted for the
buyer's award rule (L1 tenders double price sensitivity). Offers below a 20%
target win probability are dropped in favour of the most competitive compliant
offer.

When the best competitor is **below our landed cost**, price-matching is
rejected outright. The engine restricts itself to bundled configurations and
picks the value-add that buys the most win probability. The rationale states the
loss that matching would have caused. The strategy labels are *Value
differentiation, Floor defence, Competitive undercut, Competitive match, Margin
capture, Value premium, Standard pricing* and *Reviewer override*.

## Project structure

```
backend/
  app/
    agents/        base contract, typed messages, six agents, orchestrator
    api/           REST endpoints (requests, reference data)
    db/            SQLAlchemy models, session, seeder
    data/          catalogue, tax rules, FX reference, gazetteer, market data,
                   pricing policy, knowledge base (markdown)
    finance/       currency provider chain, tax engine, money formatting
    market/        mock competitor market API (separate FastAPI app)
    ml/            corpora, models, registry
    nlp/           analyser, gazetteer, extractors, line-item extraction,
                   layout analysis, section tree, tender facts and eligibility
    pricing/       strategy engine, mandated-warranty rules
    rag/           hybrid index, knowledge and catalogue stores
    services/      document ingestion, market client, PDF renderers (quotation,
                   memo, bid report, compliance statement)
    assets/fonts/  Inter (OFL) for PDFs
  tests/           unit, agent, API and end-to-end tests
frontend/          React + TypeScript + Tailwind review console
samples/           seven short requests (TXT, PDF, DOCX) and two full tenders
scripts/           sample and tender document generators
docs/              roadmap, architecture notes, screenshots
```

## API

Interactive documentation is served at **/docs** (Swagger UI) while the server
is running. The main endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth/login` · `register` · `federated` · `logout`, `GET /api/auth/me` | Sign-in and session |
| `POST` | `/api/rfps` | Submit pasted text |
| `POST` | `/api/rfps/upload` | Submit one or more PDF/DOCX/TXT files (originals are kept) |
| `GET` · `POST` | `/api/rfps/samples`, `/api/rfps/samples/{file}` | List sample requests; process a sample tender file |
| `GET` | `/api/rfps`, `/api/rfps/{id}` | List, and full detail (parsed data, pricing, proposal, stage logs, events) |
| `POST` | `/api/rfps/{id}/reprice` | Apply reviewer overrides (line prices, services, quantities, products, exclusions, added items, client and terms corrections, currency) and re-run from costing |
| `POST` | `/api/rfps/{id}/approve` · `reject` · `reopen` · `retry` | Workflow actions |
| `POST` | `/api/rfps/{id}/compliance` | Reviewer decisions on clauses and eligibility criteria; re-runs from compliance |
| `GET` | `/api/rfps/{id}/documents/{quotation\|memo\|report\|compliance}`, `/api/rfps/{id}/original` | PDFs, and the original upload |
| `GET` | `/api/dashboard` | KPIs |
| `GET` | `/api/catalog/products` · `PATCH /api/catalog/products/{sku}` | Pricing database |
| `GET` | `/api/market/offers` · `/api/market/competitors` | Market intelligence |
| `GET` | `/api/finance/fx` · `POST /api/finance/tax-preview` | Currency and tax |
| `GET` | `/api/models` · `POST /api/models/retrain` · `GET /api/knowledge/search` | Models and retrieval |
| `GET` | `/market-api/v1/...` | The mock market service (requires `X-Api-Key`) |

## Testing

```bash
cd backend
python -m pytest            # 57 tests: language core, parser, long tenders, compliance, finance, pricing, drafting, API workflow, sign-in, reviewer edits
cd ../frontend
npm run typecheck
```

## Build phases

The project was built in phases, each committed separately. See
[`docs/ROADMAP.md`](docs/ROADMAP.md).

---

*Academic project. Company names, customers, competitors and prices are
fictitious; product names are used descriptively. Inter font © The Inter
Project Authors and Source Serif 4 © The Source Serif 4 Project Authors, both
under the SIL Open Font License 1.1.*
