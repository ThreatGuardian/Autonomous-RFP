"""Learning loop: reviewer corrections and bid outcomes become training data.

Three signals are captured while people use the system:

* **Clause labels** – a reviewer changes the type of a requirement (for example
  "delivery" -> "warranty"). The sentence and its corrected type are stored.
* **Category labels** – a reviewer swaps the product on a line for one from a
  different category; the line description is stored with the new category.
* **Bid outcomes** – won or lost, with the winning price when known. Each outcome
  becomes a real row in the deal ledger the win-probability model learns from.

Models retrain automatically once a handful of new labels have arrived
(``registry.RETRAIN_EVERY``). ``evaluate`` reports how the models do on the
*real* labels only, using leave-one-document-out evaluation so a sentence is
never scored by a model that trained on its own document, and measures
calibration (expected calibration error and a reliability table).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BidOutcome, DealHistory, Rfp, TrainingLabel
from app.db.session import session_scope

MIN_REAL_FOR_EVAL = 8


def record_label(db: Session, model: str, text: str, label: str, predicted: str | None, rfp_id: int | None,
                 source: str = "reviewer") -> TrainingLabel | None:
    text = " ".join(text.split())[:2000]
    if not text or label == predicted:
        return None
    existing = db.scalar(select(TrainingLabel).where(TrainingLabel.model == model, TrainingLabel.text == text))
    if existing is not None:
        existing.label, existing.predicted, existing.rfp_id = label, predicted, rfp_id
        return existing
    row = TrainingLabel(model=model, text=text, label=label, predicted=predicted, rfp_id=rfp_id, source=source)
    db.add(row)
    return row


def record_line_correction(db: Session, rfp: Rfp, line_no: str, sku: str) -> None:
    """A reviewer chose a product from another category than the parser predicted."""
    from app.db.models import Product

    product = db.scalar(select(Product).where(Product.sku == sku))
    line = next((li for li in (rfp.parsed or {}).get("line_items", []) if str(li.get("line_no")) == str(line_no)), None)
    if product is None or line is None:
        return
    record_label(db, "category", line.get("description") or line.get("text", ""), product.category, line.get("category"),
                 rfp.id)


def record_outcome(db: Session, rfp: Rfp, result: str, winning_total: float | None, winner: str | None,
                   note: str | None) -> BidOutcome:
    """Store a bid outcome and add it to the deal ledger as a real observation."""
    pricing = rfp.pricing or {}
    strategy = pricing.get("strategy") or {}
    award = strategy.get("award") or {}
    parsed = rfp.parsed or {}
    our_total = strategy.get("revenue") or rfp.total_base
    outcome = db.scalar(select(BidOutcome).where(BidOutcome.rfp_id == rfp.id))
    if outcome is None:
        outcome = BidOutcome(rfp_id=rfp.id, result=result)
        db.add(outcome)
    outcome.result, outcome.our_total, outcome.winning_total, outcome.winner, outcome.note = (
        result, our_total, winning_total, winner, note)

    # Replace the ledger row for this bid (outcomes can be corrected).
    for old in db.scalars(select(DealHistory).where(DealHistory.rfp_id == rfp.id)):
        db.delete(old)
    if result in ("won", "lost") and our_total:
        # Price position against the best rival: the actual winner if we lost, the
        # best competitor seen by the strategy agent otherwise.
        rival = winning_total if (result == "lost" and winning_total) else award.get("lowest_total")
        ratio = float(our_total) / float(rival) if rival else 1.0
        lines = strategy.get("lines", [])
        best = [(li, (li.get("market") or {}).get("best")) for li in lines]
        warranty = [li["warranty_months"] - b["warranty_months"] for li, b in best if b]
        lead = [li["lead_time_days"] - b["lead_time_days"] for li, b in best if b]
        from datetime import datetime, timezone

        client = parsed.get("client", {})
        db.add(DealHistory(
            closed_on=datetime.now(timezone.utc), customer_segment=client.get("segment") or "smb",
            category=(parsed.get("line_items") or [{}])[0].get("category") or "mixed",
            quantity=sum(li.get("quantity", 0) for li in parsed.get("line_items", [])) or 1,
            price_ratio=round(max(0.6, min(1.6, ratio)), 4), margin_pct=float(strategy.get("margin_pct") or 0),
            warranty_delta_months=int(np.median(warranty)) if warranty else 0,
            lead_time_delta_days=int(np.median(lead)) if lead else 0,
            bundled_value_add=any(li.get("bundle") for li in lines), repeat_customer=bool(client.get("repeat_customer")),
            won=result == "won", source="outcome", rfp_id=rfp.id,
        ))
    return outcome


# --------------------------------------------------------------------------- evaluation


def _ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> tuple[float, list[dict[str, Any]]]:
    edges = np.linspace(0, 1, bins + 1)
    table, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if not mask.any():
            continue
        acc, avg = float(correct[mask].mean()), float(conf[mask].mean())
        ece += mask.mean() * abs(acc - avg)
        table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()), "confidence": round(avg, 3), "accuracy": round(acc, 3)})
    return round(float(ece), 4), table


def _evaluate_text_model(kind: str) -> dict[str, Any]:
    from app.ml.models import CategoryClassifier, ClauseClassifier
    from app.ml.registry import catalogue_rows, registry

    with session_scope() as s:
        rows = [(t.text, t.label, t.rfp_id or -t.id) for t in s.scalars(select(TrainingLabel).where(TrainingLabel.model == kind))]
    out: dict[str, Any] = {"labels": len(rows), "documents": len({r[2] for r in rows})}
    if len(rows) < MIN_REAL_FOR_EVAL:
        out["status"] = f"Needs at least {MIN_REAL_FOR_EVAL} reviewer labels for a real-data evaluation."
        return out

    def fresh(extra):
        return ClauseClassifier().train(extra) if kind == "clause" else CategoryClassifier().train(catalogue_rows(), extra)

    base = fresh([])
    by_doc: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for text, label, doc in rows:
        by_doc[doc].append((text, label))
    base_hits, blend_hits, conf, correct = [], [], [], []
    docs = list(by_doc)
    # Leave-one-document-out (capped to keep the evaluation quick).
    for doc in docs[:12]:
        train = [(t, l) for d in docs if d != doc for t, l in by_doc[d]]
        model = fresh(train)
        texts = [t for t, _ in by_doc[doc]]
        gold = [l for _, l in by_doc[doc]]
        for p, g in zip(model.predict(texts), gold):
            blend_hits.append(p.label == g)
            conf.append(p.confidence)
            correct.append(p.label == g)
        base_hits += [p.label == g for p, g in zip(base.predict(texts), gold)]
    ece, table = _ece(np.asarray(conf), np.asarray(correct, dtype=float))
    out.update(status="evaluated", method="leave-one-document-out on reviewer labels",
               synthetic_only_accuracy=round(float(np.mean(base_hits)), 4),
               with_real_labels_accuracy=round(float(np.mean(blend_hits)), 4), ece=ece, reliability=table)
    current = registry.clause_classifier() if kind == "clause" else registry.category_classifier()
    out["serving_model_real_labels"] = current.metrics.get("real_labels", 0)
    return out


def _evaluate_win_model() -> dict[str, Any]:
    from app.ml.models import BidFeatures
    from app.ml.registry import registry

    with session_scope() as s:
        real = list(s.scalars(select(DealHistory).where(DealHistory.source == "outcome")))
        rows = [(BidFeatures(price_ratio=d.price_ratio, warranty_delta_months=d.warranty_delta_months,
                             lead_time_delta_days=d.lead_time_delta_days, bundled_value_add=d.bundled_value_add,
                             repeat_customer=d.repeat_customer, segment=d.customer_segment), int(d.won)) for d in real]
    out: dict[str, Any] = {"outcomes": len(rows)}
    if len(rows) < MIN_REAL_FOR_EVAL:
        out["status"] = f"Needs at least {MIN_REAL_FOR_EVAL} recorded outcomes for a real-data evaluation."
        return out
    model = registry.win_model()
    p = np.asarray([model.predict(f) for f, _ in rows])
    y = np.asarray([w for _, w in rows], dtype=float)
    ece, table = _ece(p, y)
    out.update(status="evaluated", brier=round(float(np.mean((p - y) ** 2)), 4), predicted_win_rate=round(float(p.mean()), 4),
               actual_win_rate=round(float(y.mean()), 4), ece=ece, reliability=table)
    return out


def status() -> dict[str, Any]:
    from app.ml.registry import registry

    with session_scope() as s:
        outcomes = list(s.scalars(select(BidOutcome)))
        counts = defaultdict(int)
        for t in s.scalars(select(TrainingLabel)):
            counts[t.model] += 1
        summary = {"won": sum(o.result == "won" for o in outcomes), "lost": sum(o.result == "lost" for o in outcomes),
                   "cancelled": sum(o.result == "cancelled" for o in outcomes)}
    return {
        "labels": dict(counts), "outcomes": summary,
        "models": {
            "clause_classifier": registry.clause_classifier().metrics,
            "category_classifier": registry.category_classifier().metrics,
            "win_model": registry.win_model().metrics,
        },
    }


def evaluate() -> dict[str, Any]:
    return {"clause": _evaluate_text_model("clause"), "category": _evaluate_text_model("category"),
            "win": _evaluate_win_model()}
