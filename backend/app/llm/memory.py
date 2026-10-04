"""What the language-model agents learn from: reviewer corrections, bid outcomes and approved work.

Claude models are not fine-tuned per customer. They learn this company's way of working
from examples placed in the request (in-context learning), drawn from the same data
the learning loop records:

* **clause corrections** — sentences whose requirement type a reviewer changed;
* **product corrections** — request lines whose product a reviewer swapped;
* **bid outcomes** — won and lost bids with the price gap to the winner;
* **approved quotations** — the cover letters of quotations a reviewer approved,
  used as the house style for new ones.

The examples are retrieved fresh for every request, so a correction made today shapes
tomorrow's output with no retraining step.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.models import DealHistory, Rfp, TrainingLabel
from app.db.session import session_scope
from app.nlp.text import analyze


def _similar(query: str, rows: list[tuple[str, str]], k: int) -> list[tuple[str, str]]:
    """The ``k`` rows whose text shares the most stemmed words with ``query`` (most recent first on ties)."""
    want = set(analyze(query))
    if not want:
        return rows[:k]
    scored = sorted(enumerate(rows), key=lambda ir: (-len(want & set(analyze(ir[1][0]))) / (len(want) or 1), ir[0]))
    return [r for _, r in scored[:k]]


def clause_examples(query: str = "", k: int = 40) -> list[tuple[str, str]]:
    """Reviewer-corrected (sentence, requirement type) pairs, most relevant to ``query`` first."""
    with session_scope() as s:
        rows = [(r.text, r.label) for r in s.scalars(
            select(TrainingLabel).where(TrainingLabel.model == "clause").order_by(TrainingLabel.id.desc()).limit(500))]
    return _similar(query, rows, k)


def product_examples(query: str = "", k: int = 20) -> list[tuple[str, str]]:
    """Reviewer product swaps as (request line, category of the product chosen)."""
    with session_scope() as s:
        rows = [(r.text, r.label) for r in s.scalars(
            select(TrainingLabel).where(TrainingLabel.model == "category").order_by(TrainingLabel.id.desc()).limit(500))]
    return _similar(query, rows, k)


def bid_history(category: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """Recorded outcomes of real bids (not the synthetic training ledger)."""
    with session_scope() as s:
        stmt = select(DealHistory).where(DealHistory.source == "outcome")
        if category:
            stmt = stmt.where(DealHistory.category == category)
        rows = s.scalars(stmt.order_by(DealHistory.closed_on.desc()).limit(limit))
        return [{"closed_on": r.closed_on.date().isoformat(), "segment": r.customer_segment, "category": r.category,
                 "quantity": r.quantity, "our_price_vs_winner": round(r.price_ratio, 3), "margin_pct": round(r.margin_pct, 1),
                 "bundled_service": r.bundled_value_add, "won": r.won} for r in rows]


def approved_letters(limit: int = 2) -> list[list[str]]:
    """Cover letters of the most recently approved quotations (the company's house style)."""
    with session_scope() as s:
        rows = s.scalars(select(Rfp).where(Rfp.status == "approved").order_by(Rfp.updated_at.desc()).limit(limit))
        return [list((r.proposal or {}).get("cover_letter") or []) for r in rows if (r.proposal or {}).get("cover_letter")]
