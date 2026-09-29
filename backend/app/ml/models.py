"""Trained models: clause classifier, line-item category classifier, win-probability model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer

from app.ml.corpus import category_corpus, clause_corpus
from app.nlp.text import analyze, fold


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def analyze_ngrams(text: str) -> list[str]:
    """Stemmed unigrams plus adjacent bigrams (module-level so models pickle)."""
    toks = analyze(text)
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


def _text_pipeline(C: float) -> Pipeline:
    features = FeatureUnion(
        [
            ("words", TfidfVectorizer(analyzer=analyze_ngrams, sublinear_tf=True, min_df=1)),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), preprocessor=fold, sublinear_tf=True, min_df=2)),
        ]
    )
    return Pipeline([("features", features), ("clf", LogisticRegression(C=C, max_iter=3000))])


@dataclass
class Prediction:
    label: str
    confidence: float
    distribution: dict[str, float]


class TextClassifier:
    """Shared behaviour for the two TF-IDF + logistic-regression text models."""

    name = "text-classifier"

    def __init__(self, C: float = 8.0) -> None:
        self.pipeline = _text_pipeline(C)
        self.metrics: dict[str, Any] = {}
        self.trained_at: str | None = None

    @property
    def labels(self) -> list[str]:
        return list(self.pipeline.classes_)

    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        if not texts:
            return []
        proba = self.pipeline.predict_proba(list(texts))
        classes = self.labels
        out = []
        for row in proba:
            i = int(np.argmax(row))
            out.append(Prediction(classes[i], float(row[i]), {c: round(float(p), 4) for c, p in zip(classes, row)}))
        return out

    def predict_one(self, text: str) -> Prediction:
        return self.predict([text])[0]

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "trained_at": self.trained_at, "labels": self.labels, "metrics": self.metrics}


class ClauseClassifier(TextClassifier):
    """Classifies each RFP sentence into a requirement type."""

    name = "clause-classifier"

    def train(self) -> "ClauseClassifier":
        x_train, y_train = clause_corpus(held_out=False)
        x_test, y_test = clause_corpus(per_label=120, held_out=True)
        self.pipeline.fit(x_train, y_train)
        pred = self.pipeline.predict(x_test)
        self.metrics = {
            "train_samples": len(x_train),
            "holdout_samples": len(x_test),
            "holdout_accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "holdout_macro_f1": round(float(f1_score(y_test, pred, average="macro")), 4),
            "evaluation": "unseen template families",
        }
        self.trained_at = _now()
        return self


class CategoryClassifier(TextClassifier):
    """Predicts the product category of a free-text line item."""

    name = "category-classifier"

    def train(self, catalog: list[dict]) -> "CategoryClassifier":
        texts, labels = category_corpus(catalog)
        x_train, x_test, y_train, y_test = train_test_split(texts, labels, test_size=0.2, random_state=3, stratify=labels)
        self.pipeline.fit(x_train, y_train)
        pred = self.pipeline.predict(x_test)
        self.metrics = {
            "train_samples": len(x_train),
            "holdout_samples": len(x_test),
            "holdout_accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "holdout_macro_f1": round(float(f1_score(y_test, pred, average="macro")), 4),
            "evaluation": "stratified 80/20 split",
        }
        # Refit on everything for serving.
        self.pipeline.fit(texts, labels)
        self.trained_at = _now()
        return self


# --------------------------------------------------------------------------- win probability

SEGMENTS = ["enterprise", "smb", "public", "education", "healthcare"]
WARRANTY_CLIP = 24  # months; the bid ledger spans -12..+24
LEAD_CLIP = 21  # days


@dataclass
class BidFeatures:
    price_ratio: float  # our price / best competitor price
    warranty_delta_months: int = 0
    lead_time_delta_days: int = 0
    bundled_value_add: bool = False
    repeat_customer: bool = False
    segment: str = "smb"


def featurize(rows: Sequence[BidFeatures]) -> np.ndarray:
    """Engineered features: price gap, segment-specific price gap interactions, service terms."""
    out = []
    for r in rows:
        gap = r.price_ratio - 1.0
        # Clip service terms to the support of the training data so that, e.g., a
        # lifetime cable warranty cannot extrapolate into a certain win.
        warranty = max(-WARRANTY_CLIP, min(WARRANTY_CLIP, r.warranty_delta_months))
        lead = max(-LEAD_CLIP, min(LEAD_CLIP, r.lead_time_delta_days))
        seg = [1.0 if r.segment == s else 0.0 for s in SEGMENTS]
        out.append(
            [gap, *[gap * s for s in seg], warranty / 12.0, lead / 7.0,
             float(r.bundled_value_add), float(r.repeat_customer), *seg[1:]]
        )
    return np.asarray(out, dtype=float)


class WinProbabilityModel:
    """Logistic model of P(win | price position, service terms, buyer) learned from the bid ledger."""

    name = "win-probability"

    def __init__(self) -> None:
        self.pipeline = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(C=1.0, max_iter=2000))])
        self.metrics: dict[str, Any] = {}
        self.trained_at: str | None = None

    def train(self, deals: Sequence[dict[str, Any]]) -> "WinProbabilityModel":
        rows = [
            BidFeatures(
                price_ratio=d["price_ratio"],
                warranty_delta_months=d["warranty_delta_months"],
                lead_time_delta_days=d["lead_time_delta_days"],
                bundled_value_add=d["bundled_value_add"],
                repeat_customer=d["repeat_customer"],
                segment=d["customer_segment"],
            )
            for d in deals
        ]
        x = featurize(rows)
        y = np.asarray([int(d["won"]) for d in deals])
        x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.25, random_state=17, stratify=y)
        self.pipeline.fit(x_tr, y_tr)
        p = self.pipeline.predict_proba(x_te)[:, 1]
        self.metrics = {
            "train_samples": int(len(y_tr)),
            "holdout_samples": int(len(y_te)),
            "holdout_auc": round(float(roc_auc_score(y_te, p)), 4),
            "holdout_brier": round(float(brier_score_loss(y_te, p)), 4),
            "holdout_log_loss": round(float(log_loss(y_te, p)), 4),
            "base_win_rate": round(float(y.mean()), 4),
        }
        self.pipeline.fit(x, y)
        self.trained_at = _now()
        return self

    def predict(self, features: BidFeatures) -> float:
        return float(self.pipeline.predict_proba(featurize([features]))[0, 1])

    def curve(self, base: BidFeatures, ratios: Sequence[float]) -> list[float]:
        rows = [BidFeatures(**{**base.__dict__, "price_ratio": r}) for r in ratios]
        return [float(p) for p in self.pipeline.predict_proba(featurize(rows))[:, 1]]

    def price_elasticity(self, segment: str) -> float:
        """d logit / d price_ratio for a segment, in original units (for explanations)."""
        clf: LogisticRegression = self.pipeline.named_steps["clf"]
        scale: StandardScaler = self.pipeline.named_steps["scale"]
        coef = clf.coef_[0] / scale.scale_
        idx = SEGMENTS.index(segment) if segment in SEGMENTS else 1
        return float(coef[0] + coef[1 + idx])

    def describe(self) -> dict[str, Any]:
        clf: LogisticRegression = self.pipeline.named_steps["clf"]
        names = ["price_gap", *[f"price_gap×{s}" for s in SEGMENTS], "warranty_years", "lead_time_weeks",
                 "bundled_value_add", "repeat_customer", *[f"segment={s}" for s in SEGMENTS[1:]]]
        scale: StandardScaler = self.pipeline.named_steps["scale"]
        coefs = clf.coef_[0] / scale.scale_
        return {
            "name": self.name,
            "trained_at": self.trained_at,
            "metrics": self.metrics,
            "coefficients": {n: round(float(c), 4) for n, c in zip(names, coefs)},
            "odds_ratio_bundled": round(math.exp(float(coefs[names.index("bundled_value_add")])), 3),
        }
