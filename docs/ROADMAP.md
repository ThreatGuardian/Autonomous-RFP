# Build Roadmap

The system is delivered in ten phases (0–9). Each phase ends in a working, tested
increment and is committed separately so the history reads as the build log.

| # | Phase | Outcome |
|---|-------|---------|
| 0 | Foundation | Repository layout, configuration, roadmap |
| 1 | Data layer | Relational schema (SQLAlchemy/SQLite), seeded catalogue, customers, deal history, knowledge base |
| 2 | Language & learning core | Tokenisation, feature extraction, synthetic corpus generation, trained clause classifier and win-probability model, hybrid retrieval index (BM25 + LSA vectors) |
| 3 | RFP Parser Agent | Document ingestion (PDF/DOCX/TXT), entity extraction, line-item extraction, clause classification, retrieval-based product matching |
| 4 | Currency & tax engine | Live FX provider with cached/reference fallback, jurisdiction rules (GST/IGST, reverse charge, US state sales tax, export zero-rating) |
| 5 | Pricing & Competitor Analysis | Mock competitor market API, Internal Pricing Agent, Competitive Strategy Agent (market normalisation, expected-profit optimisation, value-differentiation pivot), Localisation Agent (currency + tax) |
| 6 | Proposal Drafting Agent | Retrieval-augmented proposal composition (extractive, MMR-selected evidence), client quotation PDF and internal pricing memo PDF |
| 7 | Orchestrator & API | Parallel pipeline execution, stage trace persistence, approval workflow (override, approve, reject, regenerate) |
| 8 | Web application | React + TypeScript review console: intake, pipeline board, pricing review, competitor landscape, catalogue |
| 9 | Hardening | End-to-end tests, sample RFPs, documentation, one-command run |

## Stage 2 — real-world tenders for Indian MSMEs

| # | Phase | Outcome |
|---|-------|---------|
| 10 | Long-tender understanding | Layout-aware PDF/DOCX parsing, section tree, key dates and data, evaluation method, eligibility criteria, items only from the schedule with linked specifications, Tender Compliance Agent, compliance statement PDF, Compliance tab with reviewer decisions |
| 11 | Award-rule strategy *(done)* | Whole-bid L1 / QCBS analysis, MSE purchase preference, reverse-auction floor, no bundle credit under L1; editable bid report with an editing assistant and PDF/Word export; decluttered dashboard with motion |
| 12 | Company data import *(done)* | CSV / Excel / Tally XML import of catalogue, prices, stock, HSN and GST with header recognition, preview and commit, row-level issues, and a price version for every change |
| 13 | Competitor intelligence adapters *(done)* | Market feed, collected-quote sheets, public award results and saved web pages become dated, sourced price observations; the freshest per competitor is merged into every bid, older ones weigh less; brand stores offer their own equivalent model |
| 14 | Learning loop *(done)* | Reviewer corrections (requirement type, product swaps) become labels and bid outcomes become real deals; models retrain automatically; leave-one-document-out evaluation and calibration (ECE) on real labels |
| 15 | Full response pack *(done)* | Technical proposal (PDF + Word) with covering letter, bidder form, eligibility statement, item-by-item technical compliance, conditions, deviations, declarations and checklist; OEM authorisation request letters; submission index; bundled with the compliance statement and financial bid as one ZIP |

### Trial: Data Care Corp answers DES Pune University

Data Care Corp (a Pune wholesale dealer of computers, components and electronics) is the default
company data set, with Amazon Business, Flipkart Wholesale, HP World, an Apple authorised store and
a Dell Exclusive Store as mock competitors. `samples/10_des_pune_university_rfp.pdf` is a 12-page RFP
for 50 units each of ten laboratory products. The system matches all ten items, meets 94 of 94
mandatory clauses, recommends *Bid*, ranks the whole bid L1 and produces the full submission pack
(`docs/trial/`). The trial runs as an automated test.

## Design principles

* **No large language model.** Every decision is made by explicit rules,
  classical information retrieval, or models trained in this repository
  (scikit-learn). All reasoning is inspectable.
* **Separated responsibilities.** Each agent owns one concern and communicates
  only through typed messages on the shared pipeline context.
* **Explainability first.** Every price carries a machine-produced rationale:
  the facts observed, the rule that fired and the alternatives rejected.
