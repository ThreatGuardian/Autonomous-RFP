# Build Roadmap

The system is delivered in nine phases. Each phase ends in a working, tested
increment and is committed separately so the history reads as the build log.

| # | Phase | Outcome |
|---|-------|---------|
| 0 | Foundation | Repository layout, configuration, roadmap |
| 1 | Data layer | Relational schema (SQLAlchemy/SQLite), seeded catalogue, customers, deal history, knowledge base |
| 2 | Language & learning core | Tokenisation, feature extraction, synthetic corpus generation, trained clause classifier and win-probability model, hybrid retrieval index (BM25 + LSA vectors) |
| 3 | RFP Parser Agent | Document ingestion (PDF/DOCX/TXT), entity extraction, line-item extraction, clause classification, retrieval-based product matching |
| 4 | Pricing & Competitor Analysis Agent | Mock competitor market API, internal price lookup, market normalisation, expected-profit price optimisation, strategy engine with value-differentiation pivot |
| 5 | Currency & tax engine | Live FX provider with cached/reference fallback, jurisdiction rules (GST/IGST, EU VAT reverse charge, US sales tax, export zero-rating) |
| 6 | Proposal Drafting Agent | Retrieval-augmented proposal composition (extractive, MMR-selected evidence), client quotation PDF and internal pricing memo PDF |
| 7 | Orchestrator & API | Parallel pipeline execution, stage trace persistence, approval workflow (override, approve, reject, regenerate) |
| 8 | Web application | React + TypeScript review console: intake, pipeline board, pricing review, competitor landscape, catalogue |
| 9 | Hardening | End-to-end tests, sample RFPs, documentation, one-command run |

## Design principles

* **No large language model.** Every decision is made by explicit rules,
  classical information retrieval, or models trained in this repository
  (scikit-learn). All reasoning is inspectable.
* **Separated responsibilities.** Each agent owns one concern and communicates
  only through typed messages on the shared pipeline context.
* **Explainability first.** Every price carries a machine-produced rationale:
  the facts observed, the rule that fired and the alternatives rejected.
