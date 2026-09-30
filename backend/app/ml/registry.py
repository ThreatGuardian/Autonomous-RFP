"""Model registry: load persisted models, train on first use, expose metadata."""

from __future__ import annotations

import json
import threading
from typing import Any

import joblib
from sqlalchemy import select

from app.config import get_settings
from app.db.models import DealHistory, Product, TrainingLabel
from app.db.seed import load_json
from app.db.session import session_scope
from app.ml.models import CategoryClassifier, ClauseClassifier, WinProbabilityModel

MODEL_VERSION = "3"
RETRAIN_EVERY = 5  # new reviewer labels (or outcomes) that trigger a retrain


def labels(model: str) -> list[tuple[str, str]]:
    with session_scope() as s:
        return [(t.text, t.label) for t in s.scalars(select(TrainingLabel).where(TrainingLabel.model == model)
                                                       .order_by(TrainingLabel.id))]


def _count(model: str) -> int:
    from sqlalchemy import func

    with session_scope() as s:
        if model == "win":
            return int(s.scalar(select(func.count()).select_from(DealHistory).where(DealHistory.source == "outcome")) or 0)
        return int(s.scalar(select(func.count()).select_from(TrainingLabel).where(TrainingLabel.model == model)) or 0)


def catalogue_rows() -> list[dict]:
    """Active products from the database (includes imported items); JSON seed as fallback."""
    with session_scope() as s:
        rows = [{"name": p.name, "brand": p.brand, "category": p.category, "keywords": p.keywords or []}
                for p in s.scalars(select(Product).where(Product.active.is_(True)))]
    return rows or load_json("catalog.json")


class ModelRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, Any] = {}

    def _path(self, name: str):
        return get_settings().model_dir / f"{name}.v{MODEL_VERSION}.joblib"

    def forget(self, name: str) -> None:
        with self._lock:
            self._cache.pop(name, None)
            self._path(name).unlink(missing_ok=True)

    def _stale(self, name: str, model: Any, source: str) -> bool:
        """True when enough new real labels have arrived since the model was trained."""
        metrics = getattr(model, "metrics", {}) or {}
        seen = metrics.get("real_outcomes" if source == "win" else "real_labels", 0)
        return _count(source) - seen >= RETRAIN_EVERY

    def _load_or_train(self, name: str, trainer, source: str | None = None) -> Any:
        with self._lock:
            if name in self._cache:
                if source and self._stale(name, self._cache[name], source):
                    self.forget(name)
                else:
                    return self._cache[name]
            path = self._path(name)
            model = None
            if path.exists():
                try:
                    model = joblib.load(path)
                except Exception:  # corrupt or incompatible artefact: retrain
                    model = None
            if model is not None and source and self._stale(name, model, source):
                model = None
            if model is None:
                model = trainer()
                joblib.dump(model, path)
            self._cache[name] = model
            return model

    # ------------------------------------------------------------------ models

    def clause_classifier(self) -> ClauseClassifier:
        return self._load_or_train("clause-classifier", lambda: ClauseClassifier().train(labels("clause")), "clause")

    def category_classifier(self) -> CategoryClassifier:
        return self._load_or_train(
            "category-classifier", lambda: CategoryClassifier().train(catalogue_rows(), labels("category")), "category")

    def win_model(self) -> WinProbabilityModel:
        def train() -> WinProbabilityModel:
            with session_scope() as s:
                deals = [
                    {
                        "price_ratio": d.price_ratio,
                        "warranty_delta_months": d.warranty_delta_months,
                        "lead_time_delta_days": d.lead_time_delta_days,
                        "bundled_value_add": d.bundled_value_add,
                        "repeat_customer": d.repeat_customer,
                        "customer_segment": d.customer_segment,
                        "won": d.won,
                        "source": d.source,
                    }
                    for d in s.scalars(select(DealHistory))
                ]
            if len(deals) < 50:
                raise RuntimeError("Not enough deal history to train the win-probability model")
            return WinProbabilityModel().train(deals)

        return self._load_or_train("win-probability", train, "win")

    def retrain(self) -> dict[str, Any]:
        with self._lock:
            for name in ("clause-classifier", "category-classifier", "win-probability"):
                self.forget(name)
        return self.describe()

    def describe(self) -> dict[str, Any]:
        return {
            "clause_classifier": self.clause_classifier().describe(),
            "category_classifier": self.category_classifier().describe(),
            "win_model": self.win_model().describe(),
        }


registry = ModelRegistry()


if __name__ == "__main__":  # pragma: no cover
    from app.db.seed import seed_all

    seed_all()
    print(json.dumps(registry.retrain(), indent=2))
