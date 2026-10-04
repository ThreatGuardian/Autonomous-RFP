# Software Requirements Specification

**Product:** Tenderdesk — Autonomous RFP Response & Competitive Quotation
**Document type:** Software Requirements Specification (structured after IEEE 29148 / IEEE 830)
**Repository:** `threatguardian/autonomous-rfp`
**Status:** Describes the system as built (phases 0–20 complete, 100 automated tests passing)

---

## How to read this document

This document is written for two kinds of reader: people (new developers, reviewers, evaluators, the
business owner) and language models that are given the repository and need to understand it quickly.

* **Section 1–2** say what the product is, who uses it and what it must not do.
* **Section 3** is the functional specification, one feature at a time, with numbered requirements
  (`FR-…`). Each requirement says what the system does and where in the code it lives.
* **Section 4** lists every interface: screens, REST API, files, external services.
* **Section 5** is the data specification: tables, message types, data files.
* **Section 6** specifies the algorithms and models in enough detail to re-implement them.
* **Section 7** lists the non-functional requirements (performance, security, explainability, …).
* **Section 8** gives configuration, deployment and testing.
* **Section 9** lists known limitations and open issues, honestly.
* **Appendices** hold the glossary, a repository map, a requirement-to-code traceability table, and the
  worked trial (Data Care Corp × DES Pune University).

If you only have time for one section, read **1.2 (the problem), 2.2 (the pipeline) and Appendix B
(repository map)**.

Companion documents: `README.md` (usage), `docs/ARCHITECTURE.md` (methods in depth),
`docs/ROADMAP.md` (build phases).

---

## 1. Introduction

### 1.1 Purpose

Tenderdesk is a web application that helps a small or mid-sized supplier answer a customer's request for
proposal (RFP, tender, RFQ). Given the customer's document, it:

1. reads and structures the document,
2. decides which of the supplier's products meet each requested item,
3. prices every line using the supplier's costs and competitors' prices,
4. checks the supplier's eligibility and compliance against every clause,
5. recommends whether to bid,
6. produces the documents a bidder must submit, and
7. lets a human reviewer inspect every decision, change it and approve the result.

The purpose of this SRS is to define precisely what the system does, so that it can be built, verified,
extended or re-implemented by someone who has not seen the code.

### 1.2 The problem being solved

A supplier (for example a wholesale electronics dealer) receives tenders from universities, municipal
bodies and companies. Answering one well means:

* reading 10–100 pages to find the item schedule, technical specifications, eligibility criteria,
  deadlines, deposits, penalties and the award rule;
* matching each requested item to a product the company can actually supply;
* choosing a price that wins without selling below cost. This depends on competitors' prices and on
  the **award rule**: under "lowest price wins" (L1) only price matters, while under quality-and-cost
  based selection (QCBS) technical score counts too;
* checking, clause by clause, that the company can truthfully say "complied";
* assembling a technical proposal, compliance statement, financial bid and supporting letters.

Doing this by hand takes days and is error-prone. Tenderdesk does it in seconds and shows its reasoning.

### 1.3 Scope

**In scope**

* Ingesting RFPs as pasted text, TXT, PDF (text layer, optional OCR) and DOCX, with the client region selected by the user.
* Language-model agents (Claude) for parsing, pricing & competitor analysis and drafting, with deterministic guard-rails and a rule-based fallback.
* Layout-aware parsing of long tenders (section tree, tables, key dates, eligibility, evaluation method).
* Catalogue matching by hybrid retrieval and specification fit.
* Cost lookup, margin floors, volume tiers, stock, lead times, warranty and bundle services.
* Competitor price intelligence from four sources (market feed, collected quotes, public award results,
  saved web pages).
* Expected-profit price optimisation using a trained win-probability model, with a "value
  differentiation" pivot when a competitor is below the supplier's landed cost.
* Whole-bid award analysis (L1, QCBS, MSE purchase preference, reverse-auction floor).
* Currency conversion and jurisdictional tax for a user-selected region (VAT, GST, US sales tax, Canadian
  GST/HST/PST/QST, Indian CGST/SGST/IGST, export zero-rating, reverse charge).
* Compliance analysis and bid/no-bid recommendation.
* Document generation: client quotation, internal pricing memo, bid analysis report (editable), compliance
  statement, technical proposal, OEM authorisation request letters, submission index, ZIP pack.
* A reviewer console (React) with approval workflow, overrides and an activity trail.
* A learning loop: reviewer corrections and bid outcomes retrain the models.
* Company data import (CSV, Excel, Tally XML) with price history.
* Multiple company data sets selected by configuration.

**Out of scope**

* Fine-tuning language models. The agents learn from corrections in context (see 6.11), not by retraining Claude.
* Electronic submission to a government procurement portal, digital signatures, e-stamping.
* Live scraping of competitor websites. Web observations come only from pages a user saves and pastes.
* Order management, invoicing, inventory management and accounting after the bid.
* Multi-tenant hosting: one installation serves one company's data set.
* Mobile-native apps. The console is a responsive web app.

### 1.4 Definitions (short form; full glossary in Appendix A)

| Term | Meaning |
|---|---|
| RFP / tender | A buyer's document asking suppliers to bid |
| BOQ | Bill of quantities: the schedule of items and quantities |
| L1 | "Lowest 1": the award goes to the lowest-priced compliant bid |
| QCBS | Quality-and-cost-based selection: combined technical and financial score |
| EMD | Earnest money deposit |
| MSE / MSME | Micro and small enterprise; entitled to purchase preferences in Indian public procurement |
| OEM / MAF | Original equipment manufacturer / manufacturer authorisation form |
| SKU / MPN | Supplier's stock code / manufacturer part number |
| Landed cost | What a unit costs the supplier delivered to its warehouse |
| Floor price | Landed cost plus the minimum margin; never priced below without a flag |
| Value differentiation | Not matching a below-cost competitor; bundling warranty or service instead |

### 1.5 Intended audience and uses

| Reader | Uses this document to |
|---|---|
| Product owner / business user | Confirm the system does what the business needs |
| Developer | Locate and change behaviour safely; understand invariants |
| Tester | Derive test cases (each `FR-` is testable) |
| Evaluator / examiner | See that the brief's deliverables are met (Section 1.6) |
| Language model | Build an accurate mental model before reading or editing code |

### 1.6 Origin and deliverables

The original brief asked for a multi-agent system that automates RFP response and competitive quotation:
agents with separate roles, a mocked competitor database/API queried dynamically, a professional PDF
quotation with line items and margins, an approval UI that shows pricing logic and strategy reasoning,
multi-currency and regional tax support, a relational pricing database and a currency conversion API.
Section 10 maps each deliverable to its implementation. The system was then extended (phases 10–15) for
real Indian MSME tenders.

### 1.7 References

* `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
* Interactive API reference at `/docs` (OpenAPI) when the server runs
* `docs/trial/` — generated outputs from the worked trial

---

## 2. Overall description

### 2.1 Product perspective

Tenderdesk is a self-contained web application: one Python process (FastAPI) serves the REST API, a
background worker pool, and the built React front end. State is in SQLite by default (any SQLAlchemy URL
works). A second, logically separate service — the **mock market API** — simulates competitor pricing; it is
mounted in the same process at `/market-api` or can run standalone.

```
Browser (React)  ──REST/JSON──▶  FastAPI app ──▶ Orchestrator (thread pool)
                                      │              │
                                      │              ├─ RFP Parser Agent        (stage "intake")
                                      │              ├─ Internal Pricing Agent  (stage "costing")
                                      │              ├─ Tender Compliance Agent (stage "compliance")
                                      │              ├─ Pricing & Competitor Analysis Agent (stage "strategy") ──HTTP──▶ Market API
                                      │              ├─ Currency & Tax Agent    (stage "localisation") ──▶ FX providers
                                      │              └─ Proposal Drafting Agent (stage "drafting")
                                      ├─ SQLite / SQLAlchemy  (catalogue, rfps, history, observations, labels)
                                      ├─ Model files (joblib)  var/<company>/models
                                      ├─ Document files        var/<company>/documents/<reference>/
                                      └─ Anthropic Messages API (Claude) — parser, pricing and drafting agents, when a key is set
```

### 2.2 The processing pipeline (central concept)

An RFP becomes a **request** (a row in `rfps`) and passes through six stages in a fixed order. Each stage is
one **agent**. Agents never call each other: each reads typed messages from a shared context and writes
exactly one message.

| # | Stage key | Agent | Consumes | Produces (message) | Purpose |
|---|---|---|---|---|---|
| 1 | `intake` | RFP Parser Agent | raw text, source file | `parsed` | Structure the document; extract entities, items, requirements; match items to SKUs |
| 2 | `costing` | Internal Pricing Agent | `parsed` | `costing` | Cost, floor, tier discount, stock, lead time, warranty, bundle options per line |
| 3 | `compliance` | Tender Compliance Agent | `parsed`, `costing` | `compliance` | Eligibility, clause matrix, risks, bid/no-bid |
| 4 | `strategy` | Pricing & Competitor Analysis Agent | `parsed`, `costing` | `strategy` | Competitor offers, price/bundle optimisation, review by the pricing agent (Claude), award analysis |
| 5 | `localisation` | Currency & Tax Agent | `parsed`, `costing`, `strategy` | `localisation` | FX conversion, tax by jurisdiction |
| 6 | `drafting` | Proposal Drafting Agent | `parsed`, `strategy`, `localisation` | `proposal` | Compose text, render PDFs |

Status lifecycle of a request: `queued → processing → review → approved | rejected`; `failed` on error;
`reopen` and `retry` return it to work. A reviewer's change re-runs the pipeline **from the stage that the
change affects** (usually `costing`), reusing earlier results.

### 2.3 Users and roles

There is one operational role, **reviewer / bid manager** (default title "Bid manager"). All signed-in users
can do everything; there is no role-based access control (see 9.2). Other people appear only as recipients of
generated documents: the **client** (the issuing organisation) and **OEMs**.

### 2.4 Operating environment

* Server: Python 3.10+, Linux/macOS/Windows. Dependencies in `backend/requirements.txt`
  (FastAPI, SQLAlchemy 2, Pydantic 2, scikit-learn, NumPy, joblib, ReportLab, PyMuPDF, pypdf, python-docx,
  openpyxl, httpx, anthropic, google-auth).
* Client: a current evergreen browser. Front end: React 19, TypeScript, Vite, Tailwind CSS 4,
  TanStack Query, motion, lucide-react, recharts.
* Optional: Tesseract OCR for scanned PDF pages. Outbound internet for live FX rates (falls back offline).
* Start-up: one command (`./run.sh` or `.\run.ps1`) installs, builds and serves on port 8000.

### 2.5 Design constraints (rules the product must obey)

| ID | Constraint |
|---|---|
| DC-1 | **The model proposes, code decides.** Language-model output (Claude) is always schema-validated and checked by deterministic code before use: prices against the margin floor and policy, products against the retrieved catalogue candidates, client text against leaks. Rules, classical retrieval (BM25, LSA, character n-grams) and scikit-learn models trained here remain the fallback, so the system works without an API key. Every decision is logged. |
| DC-2 | **Separated responsibilities.** One agent, one concern, typed messages only. |
| DC-3 | **Explainability first.** Every price carries a machine-produced rationale: facts observed, rule applied, alternatives rejected. |
| DC-4 | **Costs never reach the client.** Client-facing documents must not show landed cost, floor, margin or win probability. A test enforces this. |
| DC-5 | **Human in the loop.** No document is final until a reviewer approves; drafts carry a DRAFT watermark. |
| DC-6 | **Additive data migrations.** New columns are nullable and added automatically at start-up; the seeder is idempotent so user edits survive restarts. |
| DC-7 | **Company data is data, not code.** Everything specific to the bidding company lives under `backend/app/data/companies/<name>/`. |
| DC-9 | **Region-neutral core.** Currency, tax and procurement conventions follow the operating region and the client region the user selects; market-specific rules apply only inside their market. |
| DC-8 | **Fictitious data.** The shipped companies, customers and all competitor prices are mock. Named retailers appear only as illustrative market participants. |

### 2.6 Assumptions and dependencies

* The tender is in English, in a supported format, with extractable text (or Tesseract is installed).
* The company's catalogue, costs and profile are accurate; the system trusts them.
* Competitor prices are estimates; their quality depends on the sources the user supplies.
* Currency conversion needs internet for live rates; otherwise cached or reference rates are used and
  flagged **stale**.
* The Claude agents need an Anthropic API key and internet access; without them the rule-based agents run.
* Reviewer corrections are honest and consistent (the learning loop trusts them).

---

## 3. Functional requirements

Priority: **M** = must (implemented and tested), **S** = should. Every item below is implemented unless
Section 9 says otherwise.

### 3.1 Authentication and sessions

| ID | Requirement | P |
|---|---|---|
| FR-AUTH-1 | The system shall let a user register (username, name, optional email, password of at least 10 characters) when sign-up is allowed, and sign in with username or email and password. Passwords are stored as PBKDF2-SHA256 hashes. | M |
| FR-AUTH-2 | The system shall issue an HMAC-SHA256-signed, expiring (default 12 h), HTTP-only, SameSite=Lax session cookie on sign-in (Secure in production) and clear it on sign-out. | M |
| FR-AUTH-3 | The system shall protect every `/api/*` endpoint except `/api/auth/*` and `/api/health` by a middleware that requires a valid session (when `TD_REQUIRE_AUTH` is on). | M |
| FR-AUTH-4 | The system shall refuse further login attempts for 15 minutes after 8 failures from one address or for one account (HTTP 429). | M |
| FR-AUTH-5 | The system shall accept a Firebase ID token at `/api/auth/firebase` only after verifying its RS256 signature against Google's keys, its audience (the configured project), issuer and expiry; it shall never accept an unverified token. An existing account may be linked only through a verified email. | M |
| FR-AUTH-6 | `GET /api/auth/config` shall report which methods are available (sign-up, Firebase, demo). The demo account (`priya` / `tenderdesk`) is created only when `TD_DEMO_USER=1` and never in production. | M |

Code: `backend/app/api/auth.py`, `backend/app/services/auth.py`. Configuration: `docs/SETUP.md`.

### 3.2 Request intake

| ID | Requirement | P |
|---|---|---|
| FR-IN-1 | The system shall accept an RFP as pasted text (`POST /api/rfps`), as one or more uploaded files (`POST /api/rfps/upload`; PDF, DOCX, TXT; up to 10 MB each) or from the bundled samples (`POST /api/rfps/samples/{file}`). | M |
| FR-IN-2 | The system shall keep the original uploaded file (`documents/<ref>/source.*`) and make it downloadable (`GET /api/rfps/{id}/original`). | M |
| FR-IN-3 | The system shall assign each request a unique reference and queue it for background processing on a worker pool (`TD_PIPELINE_WORKERS`, default 4) so several requests run in parallel. | M |
| FR-IN-4 | The system shall re-queue work interrupted by a server restart. | M |
| FR-IN-5 | The system shall list requests with status, client, totals, margin and strategy summary (`GET /api/rfps`). | M |
| FR-IN-6 | Every intake (paste, upload, sample) shall carry the **client region** selected by the user (country and, where tax depends on it, state or province). It is stored as a reviewer override with that region's currency, outranks the region detected in the document and can be changed later on the request. | M |

### 3.3 RFP Parser Agent (stage `intake`)

#### 3.3.1 Text and layout

| ID | Requirement | P |
|---|---|---|
| FR-PA-1 | Text shall be normalised (NFKC, punctuation unification, accent folding); wide gaps shall be kept as tab separators so layout-extracted tables survive. | M |
| FR-PA-2 | For PDFs the system shall read fonts, weights and ruled tables (PyMuPDF) and emit table cell rows. For DOCX it shall use heading styles and page breaks. | M |
| FR-PA-3 | Running headers and footers (repeated lines in the top/bottom 7.5% of ≥ 40% of pages, "Page x of y") shall be removed. A table that continues across pages with a repeated header shall be merged. | M |
| FR-PA-4 | Pages with no text layer shall be OCR'd when Tesseract is available, otherwise listed in the parse warnings. | S |

#### 3.3.2 Section tree

| ID | Requirement | P |
|---|---|---|
| FR-PA-5 | The system shall detect headings (`Section/Part N`, `Annexure/Appendix N`, numbered titles, typographic headings, all-caps lines) and distinguish them from numbered **clauses** (sentences with modal verbs, > 12 words, terminal punctuation). | M |
| FR-PA-6 | Each section shall be typed: notice, instructions, eligibility, scope, technical specification, bill of quantities, commercial, evaluation, conditions or forms — from a weighted title lexicon, then body, then the parent section. | M |

#### 3.3.3 Tender facts

| ID | Requirement | P |
|---|---|---|
| FR-PA-7 | The system shall extract: client (labelled fields, organisation suffixes, reconciliation with the customer master at token Jaccard ≥ 0.6), delivery location (gazetteer of 30 countries), currency (codes, symbols, names, `$` resolved by country), buyer segment, contact details. | M |
| FR-PA-8 | The system shall extract dated events with roles and times (queries, pre-bid meeting, submission, opening, publication) and commercial terms (incoterm, delivery window, payment days, advance %, minimum warranty, price weight %, lowest-price award). | M |
| FR-PA-9 | The system shall extract money in Indian notation (`Rs. 4,50,000`, `2.25 crore`, `2 lakh`) and key amounts: estimated value, EMD and MSE exemption, bid validity, performance security %, liquidated damages. | M |
| FR-PA-10 | The system shall extract the **evaluation method**: L1, or QCBS with weights (`70:30`), minimum technical score and marking scheme. | M |
| FR-PA-11 | The system shall extract each **eligibility criterion** with a type (turnover, net worth, similar works, supply volume, certification, OEM authorisation, manpower, local presence, blacklisting, years in business, registration, local content) and parsed parameters (e.g. "three works of 40% / two of 50% / one of 80% of estimated cost in seven years"). | M |

#### 3.3.4 Requirements and items

| ID | Requirement | P |
|---|---|---|
| FR-PA-12 | Every sentence, list item and table row shall become a unit with section, page and clause reference. Specification rows become `Parameter: value` requirements. | M |
| FR-PA-13 | Each requirement shall have modality (mandatory / desirable / information), actor (bidder / buyer), category and a type with confidence from the clause classifier. Clauses below confidence 0.45 are kept as context, not mislabelled. | M |
| FR-PA-14 | In long documents, line items shall be taken **only from bill-of-quantities sections**, so "must have supplied 500 laptops" in an eligibility clause is never priced. In short requests, a quantity-bearing sentence becomes a line only if the clause classifier (or category model) agrees — "within 30 days" is not 30 units. | M |
| FR-PA-15 | Quantities shall be extracted in priority order (labelled, `N x item`, `N units of`, `N units`, leading count, trailing count, number words). Numbers attached to specification units (GB, inch, port, VA, years) are never quantities. | M |
| FR-PA-16 | Item specifications shall be extracted: RAM, storage (SSD/HDD), screen size, port count, PoE, VA rating, CPU tier, resolution, Wi-Fi generation, UPS topology, drive bays, DPI, GPU memory (`vram_gb`), brand. Graphics-card text maps memory to `vram_gb` and not to RAM or form factor. | M |
| FR-PA-17 | Each BOQ line shall be linked to its technical-specification section ("as per specification 5.1", or title overlap plus category agreement) and inherit its specifications. | M |

#### 3.3.5 Catalogue matching

| ID | Requirement | P |
|---|---|---|
| FR-PA-18 | Each item shall be matched to catalogue products by hybrid retrieval (6.4) re-ranked by specification fit, brand adjustment and category coherence. Status: **matched** (score ≥ 0.42), **ambiguous** (≥ 0.30), **unmatched** (otherwise; excluded from pricing and flagged). | M |
| FR-PA-19 | A requested measurable limit (e.g. ≥ 1000 DPI) shall steer matching to a product that meets it. | M |
| FR-PA-20 | With the language model enabled, Claude shall read the whole document (passed as untrusted data) and return the client, terms, items with specifications and ambiguities as schema-validated structured output; missing client and term fields are filled from it. | M |
| FR-PA-21 | The model's items shall be reconciled with the rule-based items: the model's list and quantities are used, enriched with the matching rule item's linked specification; quantity differences, items only the rules found and the model's ambiguities become reviewer warnings and are logged. | M |
| FR-PA-22 | The model shall type the requirement sentences with the reviewer's most similar past corrections as examples. | M |
| FR-PA-23 | The model shall choose each line's product from the retrieved candidates or none; an SKU that was not offered is discarded, and the choice must still pass the specification check to count as matched. | M |

### 3.4 Internal Pricing Agent (stage `costing`)

| ID | Requirement | P |
|---|---|---|
| FR-PR-1 | For each matched line the agent shall read landed cost, list price, margin floor (`min_margin_pct`), volume-tier discount (by category and quantity), stock, lead time and warranty from the pricing database. | M |
| FR-PR-2 | Floor price shall be `unit_cost × (1 + min_margin_pct/100)`. | M |
| FR-PR-3 | A **warranty mandated by the tender** longer than the product's own shall be priced into the line (extension cost folded into cost and price), not given away. Where a clause names several groups ("graphics cards three years and UPS two years") months shall be resolved per category. | M |
| FR-PR-4 | Eligible bundle services (warranty, service, support, training) shall be listed with cost, market value and warranty extension. | M |

### 3.5 Tender Compliance Agent (stage `compliance`)

| ID | Requirement | P |
|---|---|---|
| FR-CO-1 | Each **eligibility criterion** shall be assessed against the company profile (`company.json`): turnover by financial year and segment share, incorporation date, net worth, completed credentials (value, sector, date, quantity), certifications, OEM authorisations, offices, engineers, Udyam registration. Verdict per criterion: met, subject to documents, review required, not met. | M |
| FR-CO-2 | Each **specification row** shall be assessed against the offered SKU by the same specification-fit function used for matching, then by the attribute checker (6.6). A failure shall name the parameter and look for a compliant catalogue alternative. Unknown parameters shall be marked "verify against datasheet". | M |
| FR-CO-3 | **Warranty, delivery, support-level, payment, liquidated-damages and security** clauses shall be assessed against the warranty actually quoted, lead time + transit + installation, offices and service hours, the MSMED Act 45-day rule, the LD cap and bank-guarantee exposure on the estimated contract value. The performance-security rate shall be read from the guarantee clause only. | M |
| FR-CO-4 | Liability, indemnity and termination clauses shall be assessed against policy (liability capped at contract value). Other clauses shall be answered from knowledge-base evidence accepted only with real topical overlap; otherwise an undertaking. | M |
| FR-CO-5 | The agent shall output: the clause-by-clause matrix, eligibility verdict (*Eligible*, *subject to documents*, *review required*, *not eligible*), risk flags, a bid-documents checklist, MSE benefits, and a recommendation: **Do not bid** (any criterion fails), **Bid with clarifications** (mandatory deviations, high risks or criteria needing review), else **Bid**. | M |
| FR-CO-6 | Reviewer decisions per clause or criterion (`POST /api/rfps/{id}/compliance`) shall be stored in overrides, applied last, and shall re-run from `compliance`. | M |
| FR-CO-7 | The MSMED Act payment check and the EMD exemption shall apply only when the company and the buyer are both in India; amounts are formatted in the catalogue currency. | M |

### 3.6 Pricing & Competitor Analysis Agent (stage `strategy`)

| ID | Requirement | P |
|---|---|---|
| FR-ST-1 | The agent shall query the market API for competitor offers per product and normalise them to INR through the FX service, filtering sources below the minimum reliability (0.6). | M |
| FR-ST-2 | It shall merge stored **price observations** (4.4/6.9) with feed offers: the freshest observation per competitor and product wins; observations older than `observation_max_age_days` (180) are dropped; reliability is scaled by source and age. The stage log shall state how many offers each source contributed. | M |
| FR-ST-3 | For each line it shall search a 90-point price grid between floor and list, over configurations "no bundle" and each eligible bundle, subject to: `price ≥ floor`; `price − bundle cost ≥ floor`; `bundle cost ≤ 6%` of price. | M |
| FR-ST-4 | If the best competitor is **below landed cost**, only bundled configurations are allowed (value-differentiation pivot): the system holds a compliant price and competes on warranty or service. | M |
| FR-ST-5 | It shall choose the configuration maximising expected profit `E = (price − cost − bundle cost) × qty × P(win)` among those with `P(win) ≥ 0.20`; if none qualifies, the highest-P(win) compliant offer, stated as such. | M |
| FR-ST-6 | Each line shall be classified: Value differentiation · Floor defence · Competitive undercut · Competitive match (within 2%) · Margin capture · Value premium · Standard pricing (no market) · Reviewer override. | M |
| FR-ST-7 | Each line shall carry a numbered plain-language **rationale**: market facts, cost basis, why matching was rejected (with per-unit and per-line loss), what was bundled, recommendation with margin / P(win) / expected profit, a feasible matching alternative, buyer elasticity, a scenario table and a 30-point win/profit curve. | M |
| FR-ST-8 | Under an L1 award, the win model shall see an award-adjusted price ratio, evaluation shall ignore warranty, lead-time and bundle effects, and **no free bundle shall be offered** (it earns no evaluation credit). | M |
| FR-ST-9 | **Whole-bid award analysis** (6.7): rival totals, our rank, gap to L1, the smallest uniform reduction that undercuts L1 by 0.5% within every line's floor, the MSE purchase-preference option, QCBS combined-score analysis, and reverse-auction opening and walk-away totals. | M |
| FR-ST-10 | When we are already L1, the award card shall offer "Submit as priced" and "Highest price that stays L1" (with headroom), and no MSE option. When not L1: "Price to become L1" and the MSE option. | M |
| FR-ST-11 | With the language model enabled, the pricing agent (Claude) shall review every line through tools — `get_line`, `get_competitor_offers`, `evaluate_price`, `get_bid_history`, `set_price` — and `set_price` shall reject a price below the floor, a service the margin cannot fund or above the cost cap, a free service under L1, and any change to a reviewer-locked line. Accepted decisions are re-priced by the engine; the agent's rationale and bid summary are shown to the reviewer. | M |
| FR-ST-12 | The MSE purchase preference shall be offered only when the company and the buyer are both in India. | M |

### 3.7 Currency & Tax Agent (stage `localisation`)

| ID | Requirement | P |
|---|---|---|
| FR-FX-1 | FX shall come from a provider chain: ECB rates via Frankfurter → open.er-api.com → database cache (TTL 12 h) → reference table. A fallback source shall be marked **stale** and a warning shown in the UI and memo. | M |
| FR-FX-2 | Rates shall be stored against INR with cross rates derived. Non-INR quotations add a configurable FX buffer (default 1.5%). Currency decimals respect ISO exceptions (JPY 0, KWD 3 …). | M |
| FR-TX-1 | Tax shall follow the operating region, the client region and the product tax category: domestic supply → the country's VAT/GST/sales tax for the client's state or province (in India, CGST+SGST within the supplier's state, IGST otherwise); export on EXW/FCA/FOB/CIF/CPT/CIP/DAP/DPU → zero-rated (under LUT from India); DDP → destination VAT/GST/sales tax with regional and category brackets (e.g. California exempts software and services; Quebec GST+QST); cross-border B2B services/licences with a client tax ID (non-US) → reverse charge. A product's own `gst_rate_pct` overrides its category rate. | M |
| FR-TX-2 | `POST /api/finance/tax-preview` shall compute tax for arbitrary inputs. | S |

### 3.8 Proposal Drafting Agent (stage `drafting`)

| ID | Requirement | P |
|---|---|---|
| FR-DR-1 | The agent shall compose, from structured facts and retrieved knowledge-base evidence: cover letter (acknowledgement, scope, company profile, closest case study by segment and scope, total, validity, included value), executive summary, highlights, compliance matrix, delivery plan (milestones from longest lead time + transit + installation), terms (validity, incoterm, payment, tax notes, exchange basis). | M |
| FR-DR-2 | Authorised signatory, company name, bank details and quote-number prefix shall come from the active company profile (`quote_prefix`, else the initials of the short name). Quote numbers have the form `<prefix>-Q-…`. | M |
| FR-DR-3 | It shall render a **ready-to-send client quotation PDF**: letterhead with tax registration, quotation number, date and validity, buyer and reference, subject and salutation, an itemised schedule (description with make, model and warranty; tax code; quantity; unit; unit price; tax rate; amount), totals with the tax breakdown, the amount in words, inclusions, numbered terms and conditions, bank details and the authorised signatory. A DRAFT watermark and footer notice remain until approval, and **no cost, margin or analysis** appears (DC-4). | M |
| FR-DR-4 | It shall render a confidential **pricing memo PDF** (landscape): KPIs, line economics, rationale, scenario tables, FX/tax basis, approval stamp. | M |
| FR-DR-5 | It shall render a **bid analysis report** (executive design) and a **compliance statement** (eligibility with documents, matrix grouped by tender section with page references, statement of deviations, declaration). | M |
| FR-DR-6 | The report verdict shall read "Competitive bid · Recommend submitting as priced" when rank is L1 #1; "value-led" language appears only if something is bundled. | M |
| FR-DR-7 | Proposal version shall increment on every re-draft. | M |
| FR-DR-8 | With the language model enabled, Claude shall write the cover letter, executive summary and highlights from client-safe facts and retrieved passages (approved letters as house style). Text mentioning internal terms or competitors, or quoting an amount not in the quotation, shall be discarded in favour of the template. | M |

### 3.9 Review, override and approval workflow

| ID | Requirement | P |
|---|---|---|
| FR-RV-1 | A reviewer shall be able to change per line: price, bundle/service, quantity, product (SKU), exclusion; add catalogue items; correct client and terms; change quotation currency (`POST /api/rfps/{id}/reprice`). The system re-runs from `costing` and flags the result ("Below margin floor", "Loss-making price"). | M |
| FR-RV-2 | Overrides shall be idempotent: added lines are rebuilt from the override list on every run and keep stable line numbers. | M |
| FR-RV-3 | `approve`, `reject`, `reopen`, `retry` and `delete` actions shall exist; each is recorded as an `ApprovalEvent` with actor, note and payload. | M |
| FR-RV-4 | On approval the documents shall be re-rendered without the draft watermark and the approval stamped into the memo. | M |
| FR-RV-5 | Each stage shall be persisted as a `StageRun` with status, timing, summary and ordered log entries (`info`, `decision`, `warning`) for the Activity tab. | M |

### 3.10 Editable bid report

| ID | Requirement | P |
|---|---|---|
| FR-RP-1 | A report is a document of sections and typed blocks (lead, paragraph, bullets, KPIs, bars, table, callout, note) generated from the pipeline messages, stored on the request, with a 40-step undo/redo history and a chat log (`/api/rfps/{id}/report`, `PUT`, `undo`, `redo`, `reset`). | M |
| FR-RP-2 | Untouched reports follow each re-draft; edited ones are flagged stale when prices change; any generated section can be refreshed. | M |
| FR-RP-3 | An **editing assistant** shall interpret instructions with an ordered grammar of patterns (rename, set title, hide/show, delete, move, add section, replace text, delete matching bullets, add paragraph/bullet, shorten, refresh, insert figure or knowledge fact, undo/redo, help, list). Unmatched input goes to a trained intent classifier whose reply shows the exact phrasing that will work. Shortening is extractive. **No LLM.** | M |
| FR-RP-4 | The report shall export to PDF and Word (`GET /api/rfps/{id}/report/export?format=pdf|docx`). | M |

### 3.11 Company data import (phase 12)

| ID | Requirement | P |
|---|---|---|
| FR-IM-1 | The Catalogue screen shall import CSV, Excel and Tally stock-item XML. Delimiters are sniffed, BOMs tolerated; the header row is the one with most text cells in the first ten (skipping title lines of accounting exports). | M |
| FR-IM-2 | Headers shall be mapped by exact synonym, then all-words match ("Purchase Rate" → landed cost; "Closing Qty" → stock; "HSN/SAC" → HSN). The mapping shall be shown and adjustable in the preview. | M |
| FR-IM-3 | Values shall be parsed with Indian conventions (`₹1,23,456.50`, `45,000/Nos`, `2.5 lakh`, `18%`, `3 years`). | M |
| FR-IM-4 | The preview (`POST /api/catalog/import/preview`) shall plan create / update / unchanged / skip per row (match by SKU, then MPN, then exact name) with **row-level issues**: price below cost, change ≥ 25%, HSN not 4/6/8 digits, non-standard GST slab, missing name or cost. Nothing changes until the user commits (`/commit`, plan token valid 30 min). | M |
| FR-IM-5 | New products shall receive a category (group rules, then the trained category classifier), inferred specifications and keywords. Updates shall never overwrite name or description (accounting names are abbreviated). | M |
| FR-IM-6 | Every cost, price or stock change shall write a `PriceVersion`; every upload an `ImportBatch`. Product price history is available at `GET /api/catalog/products/{sku}/history`. A CSV template is downloadable. | M |
| FR-IM-7 | After commit, catalogue retrieval shall be rebuilt and, when products were added, the category model retrained. | M |

### 3.12 Competitor intelligence (phase 13)

| ID | Requirement | P |
|---|---|---|
| FR-CI-1 | Every competitor price shall be a `PriceObservation` with competitor, MPN, unit price, currency, quantity, observation date, **adapter** and source reference. | M |
| FR-CI-2 | Four adapters: **feed** (market API, per bid; brand stores offer their nearest same-category model within 40% of the price, flagged *equivalent*), **quotes** (CSV/Excel of collected quotes), **awards** (public award results; the winner becomes a competitor; the company's own awards skipped), **web** (user-pasted product page HTML; schema.org `Offer`, then price meta tags, then visible `₹ 12,345` text; nothing is fetched). | M |
| FR-CI-3 | The Market screen shall show, per adapter, observation count, latest date and competitor count; allow uploads (`quotes`, `awards`, optional replace), a web-page paste sheet, an observations table with delete, and a price check showing source and date and flagged equivalents. | M |
| FR-CI-4 | Competitor cards shall show brands, channel and notes. | S |

### 3.13 Learning loop (phase 14)

| ID | Requirement | P |
|---|---|---|
| FR-LL-1 | Correcting a requirement's type in the Requirements tab shall store a `TrainingLabel` (model `clause`) and mark the requirement "Corrected by reviewer" (confidence 1.0). Only labels the classifier knows are accepted. | M |
| FR-LL-2 | Swapping a line's product via reprice shall store a `TrainingLabel` (model `category`). | M |
| FR-LL-3 | `POST /api/rfps/{id}/outcome` (won / lost / cancelled, winning total, winner, note) shall store a `BidOutcome` and, for won/lost, a `DealHistory` row with `source="outcome"` and `rfp_id`. The price ratio is our total ÷ winning price (or ÷ best rival total when we won). Warranty and lead-time deltas are medians over lines. | M |
| FR-LL-4 | Real labels shall weigh 5× and real outcomes 10× a synthetic example. A model shall be retrained when ≥ 5 new labels/outcomes have arrived since its last training, or when labels were removed. | M |
| FR-LL-5 | `GET /api/learning/status` shall report counts of real labels and outcomes; `GET /api/learning/evaluate` shall report leave-one-document-out accuracy of the clause/category models against the synthetic-only baseline, expected calibration error (ECE) with a reliability table, and the win model's Brier score and calibration on recorded outcomes. It needs at least 8 real labels or outcomes. | M |

### 3.14 Submission pack (phase 15)

| ID | Requirement | P |
|---|---|---|
| FR-PK-1 | `GET /api/rfps/{id}/pack` shall return a ZIP once the quotation is drafted (409 otherwise) containing: `00_Submission_index.pdf`, `01_Technical_proposal.pdf` and `.docx`, `02_Compliance_statement.pdf`, `03_Financial_bid.pdf`, `04_OEM_authorisation_requests.docx`. | M |
| FR-PK-2 | The **technical proposal** shall contain: covering letter, bidder information form (legal, statutory, MSME, turnover, net worth, certifications, bank), eligibility statement with evidence, make/model per item, parameter-by-parameter compliance table per item, commercial and general conditions, statement of deviations (or "Nil"), delivery plan, warranty and support grounded in retrieved knowledge-base passages, declarations (non-blacklisting, MSE, local content, integrity), and a checklist of documents. | M |
| FR-PK-3 | One **OEM authorisation request letter** shall be written per manufacturer offered. | M |
| FR-PK-4 | The **submission index** shall separate the technical and financial envelopes. | M |

### 3.15 Catalogue, market, finance and dashboard screens

| ID | Requirement | P |
|---|---|---|
| FR-UI-1 | **Dashboard** (`/app`): KPIs and recent requests (`GET /api/dashboard`), decluttered with motion. | M |
| FR-UI-2 | **Requests** list and **New request** (paste, upload, sample). **Request detail** with a stage tracker and tabs: Requirements, Pricing, Compliance, Quotation, Activity; documents menu; outcome control. | M |
| FR-UI-3 | **Catalogue**: browse and edit products (price, cost, stock, lead time, warranty, margin floor, active), HSN shown, price history, Import sheet. | M |
| FR-UI-4 | **Market**: price check, intelligence card, competitor cards (3.12). | M |
| FR-UI-5 | **Finance**: FX rates with refresh, tax rules, tax preview. | M |
| FR-UI-6 | **Landing, Login, Sign-up, provider sign-in** pages. The company name shown in the shell comes from the API. | M |
| FR-UI-7 | The legacy `/app/models` route redirects to `/app`; the former Models & data screen is removed. (Backend `GET /api/models`, `POST /api/models/retrain` remain as administrative endpoints.) | M |
| FR-UI-8 | The visual design shall be professional and restrained; no generic "AI" badges or labels. | M |
| FR-UI-9 | Interface motion (Motion library): page and tab transitions, spring sheets and dialogs with exit animations, animated stage tracker, staggered table rows, animated counters; all honour the operating system's reduced-motion setting. Pages load on first use. | S |
| FR-UI-10 | **Tax & currency** shall show and set the operating region; **New request** shall require the client region; the request's client tab shall change it (with its currency). | M |

### 3.16 Mock market service

| ID | Requirement | P |
|---|---|---|
| FR-MK-1 | A separate FastAPI service shall expose `/v1/health`, `/v1/competitors`, `/v1/offers`, `/v1/offers/batch` with `X-Api-Key` authentication, mounted at `/market-api` or runnable standalone (`TD_MARKET_API_URL`, `TD_MARKET_API_KEY`). | M |
| FR-MK-2 | Price for a competitor/product on day *d* = `street price × category factor (or promotion) × exp(weekly mean-reverting walk) × (1 − volume discount)`. Some promotions deliberately undercut reseller landed cost. | M |
| FR-MK-3 | Competitors carry region served, category positioning, warranty, lead time, reliability, typical bundles, and (for brand stores) the brands they sell. | M |

### 3.17 Regions

| ID | Requirement | P |
|---|---|---|
| FR-RG-1 | `GET /api/regions` shall list every selectable country with its area, currency, states/provinces, tax name and regional conventions. | M |
| FR-RG-2 | `GET/PUT /api/workspace` shall read and set the operating region (validated country and state), defaulting to the company profile; it applies to requests processed afterwards. | M |
| FR-RG-3 | Unknown countries or states shall be rejected with 422. | M |

### 3.18 Multi-company data sets

| ID | Requirement | P |
|---|---|---|
| FR-CD-1 | `TD_COMPANY` shall select a folder under `data/companies/` holding `company.json`, `catalog.json`, `customers.json`, `market.json`, `value_adds.json`, `price_tiers.json`, `knowledge/*.md` and optionally `competitor_quotes.csv`, `award_history.csv`. Default `datacare`. | M |
| FR-CD-2 | Each company shall have its own database, models and documents under `backend/var/<company>/`. Shared reference data (tax rules, countries, FX, pricing policy) stays in `data/`. | M |

---

## 4. External interface requirements

### 4.1 User interface

Routes (React Router): `/` landing, `/login`, `/signup`, `/login/:provider`, `/app` (dashboard),
`/app/requests`, `/app/requests/new`, `/app/requests/:id`, `/app/requests/:id/report` (report editor),
`/app/catalogue`, `/app/market`, `/app/finance`. Authenticated routes redirect to sign-in when there is no
session. Accessibility: tabs expose `role="tablist"`/`tab` and `aria-selected`.

Request detail tabs:

| Tab | Shows |
|---|---|
| Requirements | Every clause with section/page, modality, type (editable for learnable types), items and their matched SKU |
| Pricing | Lines, price-position scale, win/profit curve, alternatives, competitor offers, overrides, award card |
| Compliance | Eligibility criteria, clause matrix, risks, checklist, reviewer decisions |
| Quotation | Preview, approve / decline |
| Activity | Stage log (decision trail) and approval events |

### 4.2 REST API

All JSON unless stated; cookie-authenticated; OpenAPI at `/docs`. Summary:

| Group | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `register`, `firebase`, `logout`; `GET /api/auth/me`, `config` |
| Requests | `GET/POST /api/rfps`; `POST /api/rfps/upload`; `GET /api/rfps/samples`; `POST /api/rfps/samples/{file}`; `GET /api/rfps/{id}`; `DELETE /api/rfps/{id}` |
| Workflow | `POST /api/rfps/{id}/reprice`, `compliance`, `approve`, `reject`, `reopen`, `retry` |
| Documents | `GET /api/rfps/{id}/documents/{quotation\|memo\|report\|compliance}`, `/original`, `/pack` |
| Report | `GET/PUT /api/rfps/{id}/report`; `POST …/report/assistant`, `undo`, `redo`, `reset`; `GET …/report/export` |
| Learning | `GET/POST /api/rfps/{id}/outcome`; `POST /api/rfps/{id}/labels`; `GET /api/learning/status`, `evaluate` |
| Catalogue | `GET /api/catalog/products`; `PATCH /api/catalog/products/{sku}`; `GET …/{sku}/history`; `GET /api/catalog/value-adds`, `tiers`; import: `POST /api/catalog/import/preview`, `commit`; `GET /api/catalog/imports`, `/import/template` |
| Market | `GET /api/market/competitors`, `offers`, `sources`, `observations`, `observations/template`; `POST /api/market/observations/upload`, `web`; `DELETE /api/market/observations/{id}` |
| Finance | `GET /api/finance/fx`, `tax-rules`, `countries`; `POST /api/finance/fx/refresh`, `tax-preview` |
| Regions | `GET /api/regions`; `GET`/`PUT /api/workspace` |
| Other | `GET /api/dashboard`, `/api/company`, `/api/models`, `/api/knowledge/search`, `/api/llm/status`; `POST /api/models/retrain`; `GET /api/health` |
| Market service | `GET /market-api/v1/health`, `competitors`, `offers`; `POST …/offers/batch` (header `X-Api-Key`) |

Error conventions: 403 cross-origin write, disabled sign-up or unverified account link; 429 too many failed logins; 503 Firebase not configured; 404 not found; 409 wrong state (e.g. pack before drafting; reprice before pricing);
410 expired import preview; 413 file too large (RFP upload > 10 MB, data import > 8 MB); 422 validation or unreadable file; 401 unauthenticated.

### 4.3 File interfaces

| File | Direction | Format |
|---|---|---|
| RFP | in | PDF, DOCX, TXT, pasted text |
| Catalogue import | in | CSV, XLSX, Tally stock-item XML; template at `/api/catalog/import/template` |
| Quotes / awards | in | CSV or XLSX; templates at `/api/market/observations/template?adapter=…` |
| Web page | in | HTML pasted (≤ 3 MB) |
| Documents | out | PDF (ReportLab, Inter font), DOCX, ZIP |

### 4.4 External services

| Service | Use | Failure behaviour |
|---|---|---|
| Frankfurter (ECB), open.er-api.com | live FX | falls back to cache then reference table; marked stale |
| Anthropic Messages API (Claude) | parser, pricing and drafting agents | agents fall back to rules; warning logged |
| Firebase Authentication / Google public keys | optional Google and SSO sign-in | sign-in refused (503/401); passwords still work |
| Tesseract | OCR of scanned pages | pages listed in warnings |

No other network calls are made. In particular the system never fetches competitor web pages, and the
language-model API is called only when a key is configured.

---

## 5. Data requirements

### 5.1 Relational schema (`backend/app/db/models.py`)

| Table | Key columns | Purpose |
|---|---|---|
| `users` | username, name, email, title, provider (`password`/`firebase`), password_hash, external_id (Firebase user id) | Accounts |
| `products` | sku, mpn, name, brand, category, description, specs (JSON), keywords (JSON), unit_cost, list_price, min_margin_pct, stock_qty, lead_time_days, warranty_months, tax_category, active, hsn, gst_rate_pct, price_updated_at | Catalogue and pricing; `floor_price` is derived |
| `price_tiers` | category, min_qty, discount_pct | Volume discounts |
| `value_adds` | code, name, kind, categories, basis (`percent`/`flat`), cost_rate, value_rate, warranty_extension_months | Bundle services |
| `customers` | name, country, region, segment, tax_id, deals_won | Customer master |
| `deal_history` | closed_on, customer_segment, category, quantity, price_ratio, margin_pct, warranty_delta_months, lead_time_delta_days, bundled_value_add, repeat_customer, won, source, rfp_id | Win-model training data (synthetic + real outcomes) |
| `tax_rules` | country, region, tax_category, name, rate_pct, components | Tax engine |
| `fx_rates` | base, quote, rate, source, fetched_at | FX cache |
| `rfps` | reference, title, status, source_filename, raw_text, client_name, client_country, currency, due_date, parsed, pricing, compliance, proposal, report_doc, overrides (JSON), total_base, total_client, margin_pct, strategy_summary, error | The request and its stage messages |
| `stage_runs` | rfp_id, stage, agent, status, started/finished, duration_ms, summary, log (JSON) | Decision trail |
| `approval_events` | rfp_id, action, actor, note, payload | Audit trail |
| `import_batches` | filename, format, rows, created, updated, unchanged, skipped, mapping, issues, actor | Import history |
| `price_versions` | sku, unit_cost, list_price, stock_qty, effective_from, source, batch_id | Price history |
| `price_observations` | competitor_id, competitor, mpn, product, unit_price, currency, quantity, warranty_months, observed_on, adapter, source, reference, collected_by | Competitor intelligence |
| `training_labels` | model (`clause`/`category`), text, label, predicted, rfp_id, source | Reviewer corrections |
| `bid_outcomes` | rfp_id (unique), result, our_total, winning_total, winner, note, recorded_at | Bid results |
| `workspace_settings` | key, value (JSON), updated_at | Workspace preferences (operating region) |

New nullable columns are added to existing databases automatically at start-up (DC-6).

### 5.2 Typed pipeline messages (`backend/app/agents/messages.py`)

Pydantic models: `parsed` (client, currency, requested items with candidates and selected SKU,
requirements, commercial terms, tender facts), `costing` (per-line cost, floor, tier, stock, bundle
options), `compliance` (matrix, eligibility, risks, checklist, recommendation), `strategy` (per-line price,
bundle, classification, rationale, scenarios, curve, market offers, award analysis), `localisation`
(currency, FX rate/source/stale flag, per-line tax, totals), `proposal` (sections, documents, version).
`MarketOffer` carries `equivalent`, `source` and `observed_on`. `CompetitiveAnalysis.agent_summary` holds the pricing
agent's assessment; `ParsedRfp.stats.engine` records whether Claude took part.

### 5.3 Data files per company (`backend/app/data/companies/<name>/`)

| File | Content |
|---|---|
| `company.json` | Legal name, short name, GSTIN, Udyam class, ISO certificates, signatory, `quote_prefix`, bank, turnover by year, credentials, offices, engineers, OEM authorisations |
| `catalog.json` | Products with specs, cost, list price, stock, lead time, warranty, HSN, GST |
| `customers.json`, `value_adds.json`, `price_tiers.json` | As the table names |
| `market.json` | Competitors (regions, brands, positioning, reliability), street prices, promotions |
| `competitor_quotes.csv`, `award_history.csv` | Seed observations |
| `knowledge/*.md` | Ten documents (company profile, warranty, support, deployment, delivery, commercial terms, certifications, security, case studies, sustainability) used for retrieval-based drafting |

Shared: `data/tax_rules.json`, `countries.json`, `fx_reference.json`, `pricing_policy.json` (all guard-rail
numbers: FX buffer 1.5%, grid 90, max bundle share 6%, min reliability 0.6, match band 2%, min win
probability 0.20, MSE band 15% / share 25%, L1 undercut 0.5%, assumed rival technical score 75,
observation max age 180 days, source reliability quotes 0.90 / awards 0.88 / web 0.75).

### 5.4 Shipped data sets

* **`datacare` (default)** — Data Care Corp Pvt. Ltd., a Pune wholesale dealer of laptops, desktops,
  workstations, monitors, peripherals, headsets, components, storage, power, printers, AV, network switches,
  software and services: 77 products. Mock competitors: Amazon Business, Flipkart Wholesale, HP World
  (HP factory outlet), an Apple authorised store, the Dell Exclusive Store; 244 collected quotes; 80
  past awards. Generated by `scripts/make_datacare.py`.
* **`meridian`** — the original IT-infrastructure integrator, kept for the earlier samples and used by the
  automated tests (`TD_COMPANY=meridian` in `tests/conftest.py`).

---

## 6. Algorithms and models

### 6.1 Language processing (`backend/app/nlp/`)

NFKC normalisation; accent folding; tokeniser keeping model numbers and splitting number+unit (`16gb → 16 gb`);
Porter-style stemmer; number words; sentence splitting respecting bullets. Rule-based extractors for entities
(`extractors.py`), items (`line_items.py`), layout (`layout.py`), section tree (`sections.py`), tender facts
and eligibility (`tender.py`), and attribute checks (`attributes.py`).

### 6.2 Trained models (`backend/app/ml/`)

| Model | Type | Features | Labels / target | Data | Quality |
|---|---|---|---|---|---|
| Clause classifier | Multinomial logistic regression (C = 8) | TF-IDF stemmed uni+bigrams ∪ TF-IDF char 2–5-grams | `line_item, delivery, payment, warranty_support, compliance, evaluation, submission, scope` | Template-grammar synthetic corpus + reviewer labels (weight 5) | ≈ 0.85 accuracy on **held-out template families** |
| Category classifier | Same architecture | Same | Product categories present in the catalogue | Catalogue-derived phrases + curated phrase bank + labels | ≈ 0.98 held-out |
| Win-probability | Standardised logistic regression | Price gap `r−1`, gap × segment, warranty and lead-time deltas (clipped), bundle, repeat customer, segment dummies | `won` | ~2,400-row synthetic ledger + real outcomes (weight 10) | AUC ≈ 0.75, Brier ≈ 0.19 on held-out synthetic |
| Report-intent classifier | Char n-gram TF-IDF + logistic regression | — | Editing intents | Generated phrasings | Used only when no grammar pattern matches |

Models are trained on first start, persisted with joblib in `var/<company>/models`, versioned
(`MODEL_VERSION`), and retrained per FR-LL-4. The synthetic ledger is generated from a latent market model
the learner never sees.

### 6.3 Clause-to-item rule

A quantity-bearing sentence becomes a line item only if the clause classifier says `line_item` or the
category model is confident (FR-PA-14). In long documents only BOQ sections yield items.

### 6.4 Hybrid retrieval (`backend/app/rag/index.py`)

```
bm25_sat = BM25 / (BM25 + 6)           (k1 = 1.4, b = 0.72)
semantic = cos( SVD(TF-IDF(query)), SVD(TF-IDF(doc)) )     latent semantic analysis
lexical  = cos( char 3–5-gram(query), char 3–5-gram(doc) )
score    = 0.40·bm25_sat + 0.35·semantic + 0.25·lexical        ∈ [0,1], absolute so thresholds apply
```

Maximal marginal relevance diversifies returned passages.
Catalogue match: `0.6·retrieval + 0.4·spec_fit`, ± brand adjustment (+0.08 / −0.10), × category coherence
`(0.55 + 0.45·min(1, p(product category)/p(top category)))`; category prior boosts retrieval by
`1 + 0.35·p(category)`.
Knowledge store: two-stage (section then sentence, `0.55·section + 0.45·sentence`); each named standard
(ISO 27001, GDPR, …) retrieved and verified separately.

### 6.5 Price optimisation (`backend/app/pricing/strategy.py`)

As FR-ST-3 … FR-ST-8. Award-adjusted ratio `r' = 1 + (r − 1)·(price weight / 50)`, clamped to
[0.6, 2.0] × sensitivity.

### 6.6 Attribute checker (`backend/app/nlp/attributes.py`)

`check(param, want, product) → (True | False | None, explanation)`.

* **Measurable limits** (DPI, fps, mm drivers, m cable, battery hours, backup minutes, outlets, USB ports)
  are parsed into value, unit and direction (minimum by default; "maximum/up to/at most" reverses) and
  compared with the product attribute. A missing attribute gives `None` ("not recorded in the catalogue").
* **Descriptive requirements** drop filler words and purpose phrases ("for the language laboratory"), split
  into conjuncts (`,` `;` `and` `&`) and alternatives (`or` `/`); a conjunct is met when every significant
  stemmed word of one alternative appears in the product's name, brand, description, keywords or specs.
* The explanation quotes the matching attribute values as evidence.

### 6.7 Award analysis (`backend/app/pricing/award.py`)

* **Rival totals:** each competitor's offers summed over the schedule; missing items use the market median;
  rivals quoting under half the schedule by value are dropped.
* **L1:** rank, gap, and the smallest uniform reduction (bisection, bounded by every floor) undercutting L1
  by 0.5%. MSE option: within 15% of L1 → match L1 for 25% of quantities.
* **QCBS:** combined = `w_t × T + w_f × 100 × (lowest ÷ ours)`; our technical score
  `T = 55 + 40 × (mandatory met ratio) − 3 × deviations`, clamped 40–95; rivals assumed 75; the highest
  winning total found by bisection.
* **Reverse auction:** opening at the recommended total, walk-away at the floor total.

### 6.8 Warranty (`backend/app/pricing/warranty.py`)

`months_by_category(text)` parses per-category months from a single clause; `required_months` uses the
per-category map; a mandated extension is costed into the line.

### 6.9 Observation merge (`backend/app/intel/sources.py::market_view`)

Per competitor and MPN: freshest observation; drop if older than 180 days; reliability =
`source reliability × (1 − 0.35 · age / max_age)`; merged with feed offers for the bid's lines; marks
strategy `available` if any observations exist.

### 6.10 Currency and tax

As FR-FX-* and FR-TX-*; rules are data in `tax_rules.json`.

### 6.11 Language-model agents (`backend/app/llm/`)

| Step | Call | Validation | Fallback |
|---|---|---|---|
| Parser extraction | Structured output (`RfpExtraction`), effort medium | Pydantic schema; reconciliation with rules; warnings for disagreements | Rule-based items and terms |
| Clause typing | Structured output, effort low, reviewer corrections as examples | Only known labels; `line_item` ignored | Trained clause classifier |
| Product choice | Structured output over retrieved candidates | SKU must be a listed candidate; specification check | Retrieval ranking |
| Pricing review | Tool loop, effort high, history cached | `set_price` enforces floor, service funding and cap, L1 rule, reviewer locks | Engine optimum |
| Drafting | Structured output from client-safe facts and passages | Leak check (internal terms, competitors, unknown amounts), structure | Template text |

Learning is in context: reviewer clause and product corrections (most similar first), recorded bid outcomes and the
last approved letters are included in each request. Requests stream, use `fallbacks: "default"` (server-side refusal
fallback) and raise `LLMError` on refusal, truncation, schema mismatch or API errors. `python -m app.llm.evaluate
[--llm]` scores the parser against `evals/parser_gold.json`.

---

## 7. Non-functional requirements

### 7.1 Performance

| ID | Requirement |
|---|---|
| NFR-P-1 | A typical short request shall complete the pipeline in a few seconds; a 12-page tender in well under a minute on a developer laptop. |
| NFR-P-2 | First start (seeding and model training) shall take about ten seconds and happen once per company. |
| NFR-P-3 | Several requests shall process concurrently without blocking the UI. |

### 7.2 Explainability and auditability

| ID | Requirement |
|---|---|
| NFR-E-1 | Every price, match, compliance verdict and recommendation shall be traceable to a stage-log entry or a rationale paragraph. |
| NFR-E-2 | Every reviewer action shall be recorded with actor and time. Every price change shall be versioned. |
| NFR-E-3 | Matching scores, confidences and thresholds shall be visible in the UI. |

### 7.3 Security and privacy

| ID | Requirement |
|---|---|
| NFR-S-1 | Authentication per FR-AUTH-*; secrets configurable (`TD_SECRET_KEY`); cookies HTTP-only. |
| NFR-S-2 | Uploads shall be size-limited and parsed defensively; unreadable files return 422, not 500. |
| NFR-S-3 | Client documents shall not leak cost or margin (DC-4). |
| NFR-S-4 | No data leaves the installation except FX lookups, Google signing-key fetches for Firebase sign-in, and — when a key is configured — requests to the Anthropic API (tender text, catalogue candidates and client-safe facts; never credentials). |
| NFR-S-6 | Login throttling, same-origin check on state-changing calls, security headers, size-capped and validated uploads, DTD-free XML, and no internal error text in responses. |
| NFR-S-7 | `TD_ENV=production` refuses to start with a weak or missing secret, a demo market key or authentication disabled; it enables secure cookies and HSTS and disables open sign-up, the demo account and the API docs. |
| NFR-S-8 | Language-model output is untrusted: schema-validated and checked by code before use (DC-1). |
| NFR-S-5 | Document paths shall be resolved without traversal (`document_path`). |

### 7.4 Reliability and recoverability

State is durable in the database and document folder. Interrupted work is re-queued. A model file that is
stale or corrupt is retrained. FX failures degrade to cache/reference with a visible stale warning.

### 7.5 Usability

Professional, calm visual design; plain-language rationales; the same vocabulary in UI and documents
(L1, QCBS, EMD, MSE, GST); inline help via the editing assistant; responsive layout.

### 7.6 Maintainability and portability

Typed messages and one-agent-one-concern; data-driven company configuration; additive migrations; SQLite by
default and any SQLAlchemy URL; ≥ 77 automated tests; TypeScript strictness (`npm run typecheck`).

### 7.7 Honesty of output

Where the catalogue is silent the system says "verify against datasheet" instead of claiming compliance;
competitor figures are labelled estimates with source and date; stale FX is flagged.

---

## 8. Configuration, deployment and verification

### 8.1 Environment variables (`backend/app/config.py`)

| Variable | Default | Meaning |
|---|---|---|
| `TD_COMPANY` | `datacare` | Company data set |
| `TD_VAR_DIR` | `backend/var/<company>` | Database, models, documents |
| `TD_DATABASE_URL` | SQLite in var dir | Any SQLAlchemy URL |
| `TD_MARKET_API_URL` / `TD_MARKET_API_KEY` | empty / `demo-market-key` | External market service (else in-process mock) |
| `TD_FX_MODE` | `live` | `live` tries public APIs; otherwise reference |
| `TD_FX_CACHE_TTL_HOURS` / `TD_FX_TIMEOUT` | 12 / 4 | FX cache and timeout |
| `TD_PIPELINE_WORKERS` | 4 | Parallel requests |
| `TD_REQUIRE_AUTH` | on | Session enforcement |
| `TD_SESSION_HOURS` / `TD_SECRET_KEY` | 12 / generated | Session lifetime and signing key |
| `TD_FRONTEND_DIST` | `frontend/dist` | Built web app served by FastAPI |
| `TD_ENV` | `development` | `production` enforces safe settings (NFR-S-7) |
| `TD_COOKIE_SECURE` / `TD_ALLOW_SIGNUP` / `TD_DEMO_USER` | by environment | Cookie flag, open sign-up, demo account |
| `TD_FIREBASE_PROJECT_ID` | empty | Firebase project whose tokens are accepted |
| `TD_ALLOWED_ORIGINS` | localhost:5173 | Extra browser origins allowed to call the API |
| `ANTHROPIC_API_KEY` | empty | Enables the Claude agents |
| `TD_LLM` / `TD_LLM_MODEL` / `TD_LLM_TIMEOUT` | `auto` / `claude-opus-5-5` / 300 s | Agent mode, model, request timeout |

Keys and setup steps: `docs/SETUP.md`. `run.sh` / `run.ps1` load `.env`; the web build reads `frontend/.env.local`.

### 8.2 Run

`./run.sh` (macOS/Linux) or `.\run.ps1` (Windows): create venv, install, build front end, serve on
`http://127.0.0.1:8000`. Development: `uvicorn app.main:app --reload` in `backend/`, `npm run dev` in
`frontend/` (CORS allows `localhost:5173`).

### 8.3 Test strategy

`cd backend && python -m pytest` — 100 tests:

| File | Covers |
|---|---|
| `test_core.py` | language core, retrieval, models |
| `test_parser.py` | short-request parsing and matching |
| `test_tender.py` | long-tender layout, sections, eligibility, compliance |
| `test_pricing.py` | strategy engine, bundles, pivot |
| `test_award_and_report.py` | L1/QCBS/MSE, report model, assistant, export |
| `test_finance.py` | FX chain, tax rules |
| `test_drafting.py`, `test_api.py` | document generation, end-to-end API workflow |
| `test_auth_and_edits.py` | sign-in, reviewer edits |
| `test_phases_12_15.py` | parsing helpers, warranty, attributes, CSV/Tally import, observations, web extraction, labels/retrain/outcomes, pack, and the Data Care × DES Pune University trial in a subprocess |
| `test_security.py` | forged tokens rejected, verified-email linking, login throttling, cross-origin refusal, headers, sign-up switch, production checks, hostile uploads |
| `test_regions.py` | region catalogue, client region → currency and tax, operating region → domestic supply, India-only rules |
| `test_llm_agents.py` | Claude steps with a scripted client: request shape, refusals, tool loop, parser reconciliation and fallback, pricing guard-rails, drafting leak check |

Front end: `npm run typecheck`. Tests run against `TD_COMPANY=meridian` with `TD_LLM=off`; the language-model steps are
tested with a scripted client and never call the API.

### 8.4 Acceptance criteria (trial)

See Appendix D. In short: all 10 items matched at quantity 50; 94/94 mandatory clauses met; recommendation
Bid; whole bid L1 with positive margin; quote number `DCC-Q-…`; pack contains the five files.

---

## 9. Known limitations and open issues

### 9.1 Functional limits

* English only; no multi-language tenders.
* Scanned PDFs need Tesseract; handwriting is not supported.
* Competitor intelligence is only as good as the data supplied; the shipped data is mock.
* Compliance judges against the company profile and catalogue attributes; unrecorded attributes yield
  "verify against datasheet".
* The win model is trained on a synthetic ledger until real outcomes accumulate (roughly 30–50 outcomes
  and a few hundred clause labels before real data clearly dominates). It models price gap, margin, segment,
  warranty/lead-time deltas, bundle and repeat customer; it does not learn buyer-specific behaviour.
* Reviewer labelling is one item at a time; there is no bulk import of labelled data yet.
* Technical-score estimation under QCBS is a heuristic, and rivals are assumed at a fixed score.
* Model retraining runs in-process; at thousands of tenders it should move to a scheduled job.
* Quotations are generated for human review; they are not legal advice or a submission-ready legal
  document without review of the buyer's own formats.

### 9.2 Security items (honest list)

* **Resolved:** the Firebase endpoint no longer falls back to decoding unverified tokens; the simulated
  federated sign-in that trusted any email has been removed; an unverified provider email can no longer claim
  an existing account.
* **No role-based access control**; all users can approve and edit.
* **Sessions are stateless**: signing out clears the cookie, but a stolen cookie stays valid until it
  expires (12 h by default). Rotating `TD_SECRET_KEY` invalidates all sessions.
* Login throttling and import previews are held in process memory, so they reset on restart and are not
  shared between several server processes.
* With the language model enabled, tender text and catalogue data are sent to the Anthropic API. Prompt
  injection inside a tender can at most influence proposals that the code then validates; it cannot move a
  price below the floor, choose a product that was not offered or put internal figures into client text.

### 9.3 Possible future work

Bulk labelled-data import; scheduled retraining service; role-based access; server-side session revocation; e-procurement
portal integrations; additional document languages; richer competitor adapters (with permission to
scrape); a PostgreSQL deployment profile.

---

## 10. Traceability to the original brief

| Brief deliverable | Implementation |
|---|---|
| Multi-agent framework with separated roles | `backend/app/agents/` — six agents, one contract (`base.py`), typed messages (`messages.py`), orchestrator |
| Mocked competitor database/API queried dynamically | `backend/app/market/service.py` (separate FastAPI service, API key, drifting prices, below-cost promotions) queried by `services/market_client.py`; plus observation adapters in `intel/sources.py` |
| Professional PDF quotation with line items and margins | `services/pdf_renderer.py` — client quotation and internal memo (client copy hides costs) |
| Approval UI showing pricing logic and strategy reasoning | `frontend/src/pages/request/` — pricing tab, line sheet with numbered rationale, award card, overrides, approve/decline |
| Multi-currency and regional tax | `finance/` — FX chain and tax engine |
| Relational database for pricing data | `db/models.py` (SQLAlchemy/SQLite) |
| Currency conversion API | Frankfurter → open.er-api.com → DB cache → reference table |
| Agentic LLM pipeline (recommended approach) | `backend/app/llm/` — Claude in the parser, pricing & competitor analysis and drafting agents with guard-rails (DC-1, 6.11) |
| Own logic and trained models; RAG | Sections 6.2, 6.4 |
| Region-neutral operation | Section 3.17, `app/regions.py` |
| Professional front end without typical AI tags | `frontend/` (FR-UI-8) |

---

## Appendix A. Glossary

| Term | Meaning |
|---|---|
| Agent | A component with one concern that reads typed messages and writes one message |
| Award rule | How the buyer picks a winner: L1 or QCBS |
| BOQ | Bill of quantities |
| Bundle / value-add | A warranty or service added to a line to differentiate on value |
| Clause | A numbered sentence of a tender that imposes an obligation |
| Compliance matrix | Table of every requirement with our response and evidence |
| ECE | Expected calibration error: gap between predicted probability and observed frequency |
| EMD | Earnest money deposit paid with a bid |
| FX buffer | Margin added to foreign-currency quotes for rate movement |
| GST / IGST / CGST / SGST | Indian goods and services tax; integrated / central / state components |
| GSTIN, HSN | Tax registration number; goods classification code |
| L1 | Lowest bidder |
| LD | Liquidated damages (penalty for late delivery) |
| LUT | Letter of undertaking for zero-rated exports |
| MAF | Manufacturer authorisation form |
| MMR | Maximal marginal relevance (diverse retrieval) |
| MSE / MSME / Udyam | Micro-small enterprise classes and registration |
| MSMED Act | Indian law requiring payment to MSEs within 45 days |
| Observation | A dated, sourced competitor price |
| OEM | Original equipment manufacturer |
| P(win) | Predicted probability the bid wins |
| QCBS | Quality and cost based selection |
| RAG | Retrieval-augmented generation: passages retrieved from the knowledge base and catalogue ground the text the agents write |
| LLM | Large language model; here Claude (Anthropic), used by three agents |
| In-context learning | Teaching a model by including examples (here, reviewer corrections and outcomes) in the request instead of retraining it |
| Operating region / client region | Where the supplier is registered / where the buyer is; together they decide tax and conventions |
| Rationale | Machine-produced explanation attached to a price |
| Request | One RFP being processed (row in `rfps`) |
| SKU / MPN | Supplier stock code / manufacturer part number |
| Stale (FX) | Rate from cache or reference table rather than a live provider |
| Value differentiation | Not following a below-cost competitor; competing on bundled value |

## Appendix B. Repository map

```
backend/
  app/
    main.py                  FastAPI app, middleware, router mounting, static front end
    config.py                Settings (TD_* env), company data resolution (data_file)
    agents/                  base.py (contract, StageLog, PipelineContext), messages.py, orchestrator.py,
                             parser_agent.py, pricing_agent.py, compliance_agent.py, strategy_agent.py,
                             localisation_agent.py, drafting_agent.py
    api/                     auth.py, rfps.py, reference.py (dashboard, catalogue, market, finance, models),
                             report.py, data.py (import, intelligence, learning, pack)
    db/                      models.py, session.py (engine, additive migration), seed.py (idempotent seeding)
    nlp/                     text, gazetteer, extractors, line_items, layout, sections, tender, attributes
    ml/                      corpus.py (synthetic corpora), models.py (classifiers, win model), registry.py
    rag/                     index.py (hybrid index), stores.py (catalogue and knowledge stores)
    pricing/                 strategy.py, award.py, warranty.py
    finance/                 currency.py, tax.py, money.py
    imports/                 tabular.py (CSV/XLSX), catalogue.py (mapping, preview, commit, Tally)
    intel/                   sources.py (adapters, market_view, web extraction)
    learning/                loop.py (labels, outcomes, evaluation, status)
    llm/                     client.py (Claude client, tool loop), parser.py, pricing.py, drafting.py,
                             memory.py (corrections, outcomes, approved letters), evaluate.py
    regions.py               selectable regions, operating region, conventions
    pack/                    builder.py (technical proposal, MAF letters, index, ZIP)
    report/                  builder.py, assistant.py, export.py (PDF/DOCX)
    services/                documents, market_client, pdf_renderer, report_renderer,
                             compliance_renderer, auth
    market/service.py        Mock competitor API
    data/                    shared JSON + companies/<name>/ data sets
  tests/                     100 tests
  evals/parser_gold.json     reference answers for the parser evaluation
frontend/src/
    main.tsx                 Routes
    lib/                     api.ts (typed client), types.ts, format.ts
    components/              layout/Shell.tsx, ui/index.tsx, domain.tsx, motion.tsx
    pages/                   Overview, Requests, NewRequest, Catalogue, Market, Finance,
                             public/{Landing,Login,ProviderSignIn}, report/ReportEditor,
                             request/{RequestDetail, RequirementsTab, PricingTab, ComplianceTab,
                                      QuotationTab, ActivityTab, AwardCard, LineSheet, Workbench, charts}
samples/                     Seven short requests and three full tenders (incl. DES Pune University)
scripts/                     make_samples.py, make_tenders.py, tender_content.py, des_rfp.py, make_datacare.py
docs/                        SETUP.md (keys), ARCHITECTURE.md, ROADMAP.md, SRS.md, screenshots/, trial/
run.sh, run.ps1              One-command start
```

## Appendix C. Requirement-to-code traceability

| Requirements | Primary code |
|---|---|
| FR-AUTH-* | `api/auth.py`, `services/auth.py` |
| FR-IN-*, FR-RV-*, FR-UI-2 | `api/rfps.py`, `agents/orchestrator.py`, `services/documents.py` |
| FR-PA-1 … 4 | `nlp/text.py`, `nlp/layout.py` |
| FR-PA-5 … 6 | `nlp/sections.py` |
| FR-PA-7 … 17 | `nlp/extractors.py`, `nlp/tender.py`, `nlp/line_items.py`, `agents/parser_agent.py` |
| FR-PA-18 … 19 | `rag/stores.py`, `rag/index.py`, `agents/parser_agent.py` |
| FR-PR-* | `agents/pricing_agent.py`, `pricing/warranty.py` |
| FR-CO-* | `agents/compliance_agent.py`, `nlp/attributes.py`, `services/compliance_renderer.py` |
| FR-ST-* | `agents/strategy_agent.py`, `pricing/strategy.py`, `pricing/award.py`, `market/service.py` |
| FR-FX-*, FR-TX-* | `finance/currency.py`, `finance/tax.py`, `agents/localisation_agent.py` |
| FR-DR-* | `agents/drafting_agent.py`, `services/pdf_renderer.py`, `services/report_renderer.py` |
| FR-RP-* | `report/builder.py`, `report/assistant.py`, `report/export.py`, `api/report.py` |
| FR-IM-* | `imports/tabular.py`, `imports/catalogue.py`, `api/data.py` |
| FR-CI-* | `intel/sources.py`, `api/data.py`, `frontend/src/pages/Market.tsx` |
| FR-LL-* | `learning/loop.py`, `ml/registry.py`, `ml/models.py`, `api/data.py` |
| FR-PK-* | `pack/builder.py`, `api/data.py` |
| FR-CD-* | `config.py`, `db/seed.py`, `scripts/make_datacare.py` |
| FR-RG-*, FR-IN-6 | `regions.py`, `api/reference.py`, `api/rfps.py`, `components/RegionPicker.tsx` |
| FR-PA-20…23, FR-ST-11, FR-DR-8 | `llm/parser.py`, `llm/pricing.py`, `llm/drafting.py`, `llm/client.py` |
| FR-AUTH-4…6 | `api/auth.py`, `main.py` (middleware) |

## Appendix D. Worked trial: Data Care Corp × DES Pune University

**Setting.** Data Care Corp Pvt. Ltd. (Pune wholesale electronics dealer, Udyam Small, ISO 9001/14001,
GSTIN 27AAFCD4417M1Z3, quote prefix `DCC`) answers `samples/10_des_pune_university_rfp.pdf`, a 12-page RFP
(reference `DESPU/PUR/ICT-LAB/2026-27/14`, award L1, estimated cost ₹1.05 crore, EMD ₹2 lakh) for 50 units
each of ten laboratory products: desktops, monitors, keyboards, mice, USB headsets, headphones, webcams,
faculty laptops, RTX 4060 graphics cards and 600 VA UPS units.

**Result.**

| Check | Outcome |
|---|---|
| Items matched | 10 of 10, quantity 50 each; the 1000 DPI requirement moves the mouse from an 800 DPI Logitech to the Dell MS116 (`DCC-PR-512`) |
| Mandatory clauses | 94 of 94 met; all nine eligibility criteria checked against the profile |
| Recommendation | **Bid** |
| Per-category warranty | Graphics cards 36 months, UPS 24 months (not 36 for both) |
| Performance security | 3% (read from the guarantee clause, not the payment clause) |
| Award position | L1 at ₹70.77 lakh before GST (₹83.51 lakh with GST) vs HP World's estimated ₹72.49 lakh; gross margin 7.3% |
| Quote number | `DCC-Q-…` |
| Pack | `00_Submission_index.pdf`, `01_Technical_proposal.pdf`/`.docx` (12 pages), `02_Compliance_statement.pdf`, `03_Financial_bid.pdf`, `04_OEM_authorisation_requests.docx` |

Generated documents are in `docs/trial/`. The trial runs as an automated test
(`tests/test_phases_12_15.py`).

## Appendix E. Guide for language models working on this repository

1. **Language-model output is a proposal.** Any new Claude step must validate the answer (schema plus a code check
   of what matters), log what it changed, and fall back to the rules on `LLMError` (DC-1). Keep tender text marked
   as untrusted data. Test it with the scripted client in `tests/test_llm_agents.py`.
2. **Where to change what.** Parsing → `nlp/`, `agents/parser_agent.py`. Pricing/strategy →
   `pricing/`, `agents/strategy_agent.py`. Compliance → `agents/compliance_agent.py`, `nlp/attributes.py`.
   Documents → `services/`, `report/`, `pack/`. Company facts → `data/companies/<name>/*.json`, not code.
3. **Messages are the contract.** If you add a field, add it to the Pydantic model in `messages.py` with a
   default so stored requests still load, and to `frontend/src/lib/types.ts`.
4. **Keep costs out of client documents** (DC-4); there is a test for it.
5. **Tests use `TD_COMPANY=meridian`.** Data Care behaviour is exercised by the subprocess trial test. Tests
   that train models must clean up labels, deals and model files they create (see `test_phases_12_15.py`).
6. **Schema changes** must be additive and nullable (DC-6).
7. **Do not touch backend logic unnecessarily and do not change the established UI/UX** — standing owner
   instructions.
8. **Do not put model identifiers in code, comments or commits.**
9. **Run** `cd backend && python -m pytest` and `cd frontend && npm run typecheck` before committing.
10. **Mock data caveat.** Names of real retailers in the shipped data are illustrative; never present the
    prices as real offers.
