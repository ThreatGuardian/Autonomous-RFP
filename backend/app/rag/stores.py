"""Concrete retrieval stores built on :class:`HybridIndex`.

* ``KnowledgeStore`` – company knowledge base (markdown), chunked by section and
  by sentence, used by the drafting stage to ground proposal text in evidence.
* ``CatalogueStore`` – product catalogue, used by the parser to resolve free-text
  line items to SKUs.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.config import DATA_DIR
from app.db.models import Product
from app.db.session import session_scope
from app.nlp.text import split_sentences
from app.rag.index import Document, Hit, HybridIndex


@dataclass
class Passage:
    id: str
    source: str
    title: str
    section: str
    text: str
    score: float

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class KnowledgeStore:
    def __init__(self) -> None:
        sections: list[Document] = []
        sentences: list[Document] = []
        for path in sorted((DATA_DIR / "knowledge").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title_match = re.search(r"^# (.+)$", text, re.M)
            title = title_match.group(1).strip() if title_match else path.stem
            for block in re.split(r"^## ", text, flags=re.M)[1:]:
                heading, _, body = block.partition("\n")
                body = body.strip()
                sec_id = f"{path.stem}#{len(sections)}"
                meta = {"source": path.name, "title": title, "section": heading.strip()}
                # Section heading is indexed with the body so "warranty" queries find warranty sections.
                sections.append(Document(sec_id, f"{heading}. {body}", {**meta, "body": body}))
                for j, sent in enumerate(split_sentences(body)):
                    # Contextual chunking: the sentence is indexed with its document and
                    # section titles so short sentences keep their topical anchor.
                    sentences.append(
                        Document(f"{sec_id}.{j}", f"{title}. {heading}. {sent}", {**meta, "body": sent, "section_id": sec_id})
                    )
        self.sections = HybridIndex(sections)
        self.sentences = HybridIndex(sentences)

    @staticmethod
    def _to_passage(hit: Hit) -> Passage:
        m = hit.doc.meta
        return Passage(hit.doc.id, m["source"], m["title"], m["section"], m["body"], round(hit.score, 4))

    def retrieve(self, query: str, k: int = 3, min_score: float = 0.12) -> list[Passage]:
        return [self._to_passage(h) for h in self.sections.mmr(query, k=k, min_score=min_score)]

    def evidence(self, query: str, k: int = 2, min_score: float = 0.15, sections: int = 2) -> list[Passage]:
        """Two-stage retrieval: rank sections, then the best sentences inside them.

        Section-level ranking decides *what topic* answers the requirement; the
        sentence stage then picks the most specific supporting statements, so a
        stray number match ("30 minutes" vs "30 days") cannot pull in an
        off-topic sentence.
        """
        top_sections = self.sections.search(query, k=sections)
        top_sections = [h for h in top_sections if h.score >= min_score]
        if not top_sections:
            return []
        section_score = {h.doc.id: h.score for h in top_sections}
        pool = self.sentences.search(query, k=60)
        ranked = []
        for hit in pool:
            sid = hit.doc.meta["section_id"]
            if sid in section_score:
                ranked.append((0.55 * section_score[sid] + 0.45 * hit.score, hit))
        ranked.sort(key=lambda t: -t[0])
        out: list[Passage] = []
        for score, hit in ranked[:k]:
            passage = self._to_passage(hit)
            passage.score = round(score, 4)
            out.append(passage)
        return out


class CatalogueStore:
    def __init__(self, products: list[Product]) -> None:
        self.products = {p.sku: p for p in products}
        self.order = [p.sku for p in products]
        docs = []
        for p in products:
            spec_text = " ".join(f"{k.replace('_', ' ')} {v}" for k, v in (p.specs or {}).items())
            text = " ".join([p.name, p.brand, p.category.replace("_", " "), p.mpn, p.description, spec_text, " ".join(p.keywords or [])])
            docs.append(Document(p.sku, text, {"category": p.category}))
        self.index = HybridIndex(docs)

    def search(self, query: str, k: int = 5, category_prior: dict[str, float] | None = None) -> list[Hit]:
        boost = None
        if category_prior:
            boost = {i: 1.0 + 0.35 * category_prior.get(self.products[sku].category, 0.0) for i, sku in enumerate(self.order)}
        return self.index.search(query, k=k, boost=boost)


_lock = threading.Lock()
_knowledge: KnowledgeStore | None = None
_catalogue: tuple[str, CatalogueStore] | None = None


def knowledge_store() -> KnowledgeStore:
    global _knowledge
    with _lock:
        if _knowledge is None:
            _knowledge = KnowledgeStore()
        return _knowledge


def catalogue_store() -> CatalogueStore:
    """Catalogue index, rebuilt automatically when the product table changes."""
    global _catalogue
    with session_scope() as s:
        products = list(s.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.id)))
        signature = "|".join(f"{p.sku}:{p.name}:{p.description}:{p.keywords}:{p.specs}" for p in products)
    with _lock:
        if _catalogue is None or _catalogue[0] != signature:
            _catalogue = (signature, CatalogueStore(products))
        return _catalogue[1]


def invalidate_catalogue() -> None:
    global _catalogue
    with _lock:
        _catalogue = None
