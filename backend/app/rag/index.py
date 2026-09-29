"""Hybrid retrieval index: Okapi BM25 + latent semantic vectors + character n-grams.

Three complementary signals are fused into a single relevance score:

* **BM25** over stemmed tokens rewards exact vocabulary overlap
  ("PoE", "Catalyst", "ISO 27001").
* **LSA vectors** (TF-IDF projected with truncated SVD) capture co-occurrence
  semantics, so "notebook" retrieves laptop passages and "backup" retrieves
  NAS and Veeam passages even without shared words.
* **Character n-gram TF-IDF** tolerates typos and part-number fragments
  ("latitud 5450", "C9200L").

All three are bounded to [0, 1] so the fused score is an absolute confidence
that callers can threshold, not only a ranking.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize as l2_normalize

from app.nlp.text import analyze, fold


@dataclass
class Document:
    id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hit:
    doc: Document
    score: float
    bm25: float
    semantic: float
    lexical: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.doc.id,
            "score": round(self.score, 4),
            "signals": {"bm25": round(self.bm25, 4), "semantic": round(self.semantic, 4), "lexical": round(self.lexical, 4)},
            "meta": self.doc.meta,
        }


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.4, b: float = 0.72) -> None:
        self.k1, self.b = k1, b
        self.doc_len = np.array([len(d) for d in corpus], dtype=float)
        self.avgdl = float(self.doc_len.mean()) if len(corpus) else 0.0
        self.tf = [Counter(d) for d in corpus]
        df: Counter[str] = Counter()
        for d in corpus:
            df.update(set(d))
        n = len(corpus)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.tf))
        for term in set(query):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(term)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                    out[i] += idf * f * (self.k1 + 1) / denom
        return out


class HybridIndex:
    WEIGHTS = {"bm25": 0.40, "semantic": 0.35, "lexical": 0.25}
    BM25_SATURATION = 6.0

    def __init__(self, documents: Iterable[Document], *, max_components: int = 96) -> None:
        self.documents = list(documents)
        if not self.documents:
            raise ValueError("HybridIndex requires at least one document")
        texts = [d.text for d in self.documents]
        analysed = [analyze(t) for t in texts]

        self.bm25 = BM25(analysed)

        self.word_vec = TfidfVectorizer(analyzer=analyze, ngram_range=(1, 1), sublinear_tf=True, min_df=1)
        word_matrix = self.word_vec.fit_transform(texts)
        n_comp = max(2, min(max_components, word_matrix.shape[0] - 1, word_matrix.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=n_comp, random_state=7)
        self.dense = l2_normalize(self.svd.fit_transform(word_matrix))

        self.char_vec = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, preprocessor=fold
        )
        self.char_matrix = self.char_vec.fit_transform(texts)

        self.fingerprint = hashlib.sha1("\x1f".join(texts).encode()).hexdigest()

    # ------------------------------------------------------------------ scoring

    def _signals(self, query: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        bm = self.bm25.scores(analyze(query))
        bm = bm / (bm + self.BM25_SATURATION)
        q_dense = l2_normalize(self.svd.transform(self.word_vec.transform([query])))
        sem = np.clip(self.dense @ q_dense[0], 0.0, 1.0)
        lex = (self.char_matrix @ self.char_vec.transform([query]).T).toarray().ravel()
        return bm, sem, np.clip(lex, 0.0, 1.0)

    def search(self, query: str, k: int = 5, *, where: dict[str, Any] | None = None, boost: dict[int, float] | None = None) -> list[Hit]:
        bm, sem, lex = self._signals(query)
        w = self.WEIGHTS
        fused = w["bm25"] * bm + w["semantic"] * sem + w["lexical"] * lex
        if boost:
            for idx, factor in boost.items():
                fused[idx] = min(1.0, fused[idx] * factor)
        order = np.argsort(-fused)
        hits: list[Hit] = []
        for i in order:
            doc = self.documents[i]
            if where and any(doc.meta.get(key) != value for key, value in where.items()):
                continue
            if fused[i] <= 0:
                break
            hits.append(Hit(doc, float(fused[i]), float(bm[i]), float(sem[i]), float(lex[i])))
            if len(hits) >= k:
                break
        return hits

    def similarity_matrix(self, indices: list[int]) -> np.ndarray:
        vecs = self.dense[indices]
        return vecs @ vecs.T

    def mmr(self, query: str, k: int = 4, *, lambda_: float = 0.7, pool: int = 12, min_score: float = 0.05) -> list[Hit]:
        """Maximal marginal relevance: relevant *and* mutually diverse passages."""
        candidates = [h for h in self.search(query, k=pool) if h.score >= min_score]
        if not candidates:
            return []
        idx_of = {id(d): i for i, d in enumerate(self.documents)}
        cand_idx = [idx_of[id(h.doc)] for h in candidates]
        sim = self.similarity_matrix(cand_idx)
        selected: list[int] = []
        remaining = list(range(len(candidates)))
        while remaining and len(selected) < k:
            best, best_val = None, -1e9
            for r in remaining:
                redundancy = max((sim[r, s] for s in selected), default=0.0)
                val = lambda_ * candidates[r].score - (1 - lambda_) * redundancy
                if val > best_val:
                    best, best_val = r, val
            assert best is not None
            selected.append(best)
            remaining.remove(best)
        return [candidates[i] for i in selected]
