"""RFP Parser Agent.

Turns an unstructured request into a structured :class:`ParsedRfp`:

1. header entities (client, contact, reference, title) by labelled-field and
   organisation-suffix rules, reconciled against the customer master;
2. delivery jurisdiction from a gazetteer, currency from explicit pricing
   instructions or the jurisdiction default, dates by role;
3. every sentence classified by the trained clause classifier;
4. line items from tables, bullets and prose, gated by the clause and category
   classifiers so "within 30 days" is never read as thirty units;
5. each item resolved to a catalogue SKU by hybrid retrieval (with a category
   prior from the trained category classifier) re-ranked by specification fit.

When the language model is enabled (``app.llm``), Claude also reads the whole document:
its item list and terms are reconciled with the rules above, it types the requirement
sentences using reviewers' past corrections, and it chooses each product from the
retrieved candidates. The rules remain the fallback and the cross-check.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import (
    ClientInfo, CommercialTerms, CurrencyInfo, ParsedRfp, ProductMatch, RequestedItem, Requirement, TenderDocument,
    TenderSection,
)
from app.db.models import Customer, Product
from app.db.session import session_scope
from app.llm import parser as llm_parser
from app.llm.client import LLM, LLMError, get_llm
from app.ml.registry import registry
from app.nlp import extractors as ex
from app.nlp.gazetteer import countries, country_currency
from app.nlp.layout import Block, Layout, analyse
from app.nlp.line_items import RawItem, build_item, extract_specs, extract_table_items
from app.nlp.sections import CLAUSE_NO, Section, build_sections
from app.nlp.tender import (
    Unit, categorise, extract_eligibility, extract_evaluation, extract_facts, extract_key_dates, modality,
)
from app.nlp.text import analyze, fold, normalize, split_sentences, tokenize
from app.rag.stores import catalogue_store

MATCHED_THRESHOLD = 0.42
UNMATCHED_THRESHOLD = 0.30
NON_ITEM_CLAUSES = {"delivery", "payment", "submission", "evaluation", "compliance"}
BRAND_ALIASES = {"fortigate": "fortinet", "meraki": "cisco", "hpe": "hpe", "hp": "hp"}


# --------------------------------------------------------------------------- spec fit


def _product_spec_view(p: Product) -> dict[str, Any]:
    s = dict(p.specs or {})
    view: dict[str, Any] = {
        k: s[k] for k in ("ram_gb", "storage_gb", "screen_in", "ports", "capacity_va", "bays", "vram_gb", "dpi")
        if isinstance(s.get(k), (int, float)) and not isinstance(s.get(k), bool)
    }
    for k in ("poe", "wifi"):
        if k in s:
            view[k] = s[k]
    res = str(s.get("resolution", ""))
    if res:
        view["resolution"] = "4K" if res.startswith("3840") else "FHD" if res.startswith("1920") else res
    cpu = fold(str(s.get("cpu", "")))
    m = re.search(r"\bi([3579])\b|i([3579])-|ultra ([579])", cpu)
    if m:
        view["cpu_tier"] = int(next(g for g in m.groups() if g))
    elif "apple m" in cpu:
        view["cpu_tier"] = 7
    if "xeon" in cpu:
        view["cpu_family"] = "xeon"
    if "topology" in s:
        view["topology"] = "online" if "online" in s["topology"] else s["topology"]
    for k in ("throughput_gbps", "ppm"):
        if isinstance(s.get(k), (int, float)):
            view[k] = s[k]
    m = re.search(r"(\d+)\s*g", str(s.get("uplinks", "")).lower())
    if m:
        view["uplink_gbps"] = int(m.group(1))
    ff = str(s.get("form_factor", "")).lower()
    m = re.search(r"\b([124])u\b", ff)
    view_ff = f"{m.group(1)}U" if m else ("tower" if "tower" in ff else ff or None)
    if view_ff:
        view["form_factor"] = view_ff
    return view


def spec_fit(requested: dict[str, Any], product: Product) -> tuple[float | None, list[str]]:
    have = _product_spec_view(product)
    scores: list[float] = []
    reasons: list[str] = []

    def at_least(key: str, label: str, unit: str = "") -> None:
        if key not in requested:
            return
        want, got = requested[key], have.get(key)
        if got is None:
            scores.append(0.5)
            reasons.append(f"{label}: not specified by product")
        elif got >= want:
            scores.append(1.0)
            reasons.append(f"{label} {got}{unit} meets {want}{unit}")
        else:
            scores.append(0.0)
            reasons.append(f"{label} {got}{unit} below required {want}{unit}")

    at_least("ram_gb", "RAM", " GB")
    at_least("storage_gb", "Storage", " GB")
    at_least("bays", "Drive bays")
    at_least("vram_gb", "Video memory", " GB")
    at_least("dpi", "Sensor resolution", " DPI")
    if "cpu_tier" in requested:
        want, got = requested["cpu_tier"], have.get("cpu_tier")
        cpu = (product.specs or {}).get("cpu", "")
        if got is None:
            scores.append(0.5)
            reasons.append("Processor class not specified by product")
        else:
            scores.append(1.0 if got >= want else 0.0)
            reasons.append(f"{cpu or 'Processor'} {'meets' if got >= want else 'is below'} the Core i{want} class requested")
    at_least("throughput_gbps", "Throughput", " Gbps")
    at_least("uplink_gbps", "Uplink speed", "G")
    at_least("ppm", "Print speed", " ppm")
    if "capacity_va" in requested:
        want, got = requested["capacity_va"], have.get("capacity_va")
        if got is None or got < want:
            scores.append(0.0)
            reasons.append(f"Capacity {got or '?'} VA below {want} VA")
        else:
            scores.append(max(0.5, 1 - (got - want) / want))
            reasons.append(f"Capacity {got} VA covers {want} VA")
    if "screen_in" in requested and "screen_in" in have:
        diff = abs(requested["screen_in"] - have["screen_in"])
        scores.append(1.0 if diff <= 0.5 else 0.6 if diff <= 1.5 else 0.0)
        reasons.append(f"Screen {have['screen_in']}\" vs {requested['screen_in']}\" requested")
    if "ports" in requested and "ports" in have:
        want, got = requested["ports"], have["ports"]
        scores.append(1.0 if got == want else 0.6 if got > want else 0.0)
        reasons.append(f"{got} ports vs {want} requested")
    for key, label in (("poe", "PoE"), ("resolution", "Resolution"), ("wifi", "Wi-Fi standard"), ("topology", "UPS topology"),
                       ("cpu_family", "CPU family"), ("form_factor", "Form factor")):
        if key in requested:
            if have.get(key) is None:
                scores.append(0.5)
                reasons.append(f"{label}: not specified by product")
                continue
            ok = have.get(key) == requested[key]
            scores.append(1.0 if ok else 0.2)
            reasons.append(f"{label} {'matches' if ok else 'differs'}")
    if not scores:
        return None, []
    return sum(scores) / len(scores), reasons


_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def _display_title(title: str) -> str:
    """Title case for ALL-CAPS headings ("SCOPE OF WORK" -> "Scope of Work"); others unchanged."""
    letters = [c for c in title if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return title
    words = title.lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in _SMALL_WORDS:
            out.append(w)
        elif w.startswith("(") and len(w) > 1:
            out.append("(" + w[1:2].upper() + w[2:])
        elif "-" in w and not w.startswith("annexure"):
            out.append("-".join(p[:1].upper() + p[1:] for p in w.split("-")))
        else:
            out.append(w[:1].upper() + w[1:])
    result = " ".join(out)
    return re.sub(r"\b(Boq|Emd|Nit|Gcc|Scc|Itb|Oem|Maf|Gst|Msme?|Ups|Usb|Gpu|Cpu|Ai|Ml|Ict)\b", lambda m: m.group(1).upper(), result)


# --------------------------------------------------------------------------- agent


class RfpParserAgent(Agent):
    stage = "intake"
    name = "RFP Parser Agent"
    produces = "parsed"

    def run(self, ctx: PipelineContext, log: StageLog) -> ParsedRfp:
        text = normalize(ctx.raw_text)
        warnings: list[str] = []
        layout = self._layout(ctx, log)
        sections, owner = build_sections(layout.blocks)
        long_form = layout.pages >= 3 and len(sections) >= 5
        by_id = {s.id: s for s in sections}
        log.info("Document structure", format=layout.format, pages=layout.pages, sections=len(sections),
                 tables=layout.tables, long_form=long_form,
                 kinds={k: sum(1 for s in sections if s.kind == k) for k in dict.fromkeys(s.kind for s in sections)})
        warnings += layout.notes

        client = self._client(text, ctx, log)
        currency = self._currency(text, client, ctx, log)
        month_first = client.country == "US"
        dates = ex.extract_dates(text, month_first=month_first)

        units, tables = self._units(layout, sections, owner)
        # Key facts, dates, evaluation method and eligibility criteria.
        reference = ex.extract_reference(text)
        key_dates = extract_key_dates(units, month_first)
        facts = extract_facts(units, reference)
        evaluation = extract_evaluation(units)
        eligibility = extract_eligibility(units, long_form)
        for d in key_dates:
            if d.key == "submission":
                dates["due"] = d.date
            elif d.key == "publication" and not dates["issued"]:
                dates["issued"] = d.date
        log.info("Dates resolved by role", **dates)
        if key_dates:
            log.info("Key dates", **{d.key: f"{d.date} {d.time or ''}".strip() for d in key_dates})
        if facts:
            log.info("Tender key data", **{f.key: f.value for f in facts})
        if long_form:
            log.decision(f"Evaluation method: {evaluation.method}", technical_weight=evaluation.technical_weight,
                         financial_weight=evaluation.financial_weight, min_technical_score=evaluation.min_technical_score)
            log.info("Eligibility criteria extracted", count=len(eligibility),
                     kinds=[c.kind for c in eligibility])

        terms = self._terms(self._scoped_text(layout, sections, owner, long_form) or text, client, ctx, log)
        if evaluation.method == "L1":
            terms.lowest_price_award = True
        elif evaluation.method == "QCBS":
            terms.lowest_price_award = False
            if evaluation.financial_weight:
                terms.price_weight_pct = evaluation.financial_weight

        # --- line items: in long documents only from the schedule / bill of quantities
        clause_model = registry.clause_classifier()
        category_model = registry.category_classifier()
        item_kinds = self._item_kinds(sections, tables, owner, long_form)
        raw_items: list[RawItem] = []
        consumed_tables: set[int] = set()
        for tid, rows in tables.items():
            sid = owner[rows[0][0]]
            kind = by_id[sid].kind if sid else "general"
            if item_kinds is not None and kind not in item_kinds:
                continue
            found, used = extract_table_items(["| " + " | ".join(layout.blocks[i].cells or []) + " |" for i, _ in rows])
            for it in found:
                it.section = sid
            if found:
                raw_items += found
                consumed_tables.add(tid)
                log.info("Tabular schedule detected", rows=len(found), section=by_id[sid].label if sid else None)

        units = [u for u in units if u.table not in consumed_tables]
        text_units = [u for u in units if u.source == "text"]
        clause_preds = clause_model.predict([u.text for u in text_units])
        preds = dict(zip(map(id, text_units), clause_preds))
        requirements: list[Requirement] = []
        req_units: list[Unit] = []
        for u in units:
            if u.source == "field" or (long_form and u.kind == "forms"):
                continue
            if u.source == "table":
                if not self._is_requirement_row(u):
                    continue
                mod, actor = modality(u.text)
                requirements.append(Requirement(
                    id=f"R{len(requirements) + 1:02d}", text=u.text, type="technical" if u.kind != "eligibility" else "eligibility",
                    confidence=1.0, section=u.section, clause=u.clause, page=u.page,
                    modality="mandatory" if mod == "information" else mod, actor=actor,
                    category=categorise(u.text, u.kind, "line_item", 1.0, long_form), source="table"))
                req_units.append(u)
                continue
            pred = preds[id(u)]
            candidate = build_item(u.text)
            if candidate and (item_kinds is None or u.kind in item_kinds):
                cat = category_model.predict_one(candidate.description)
                p_item = pred.distribution.get("line_item", 0.0)
                accept = (pred.label == "line_item" and pred.confidence >= 0.4) or (
                    p_item >= 0.2 and cat.confidence >= 0.7 and pred.label not in NON_ITEM_CLAUSES
                )
                if accept:
                    candidate.section = u.section
                    raw_items.append(candidate)
                    continue
                if pred.label == "line_item":
                    log.warn("Quantity-like sentence rejected as line item", text=u.text[:120], section_kind=u.kind,
                             category_confidence=round(cat.confidence, 3))
            label, confidence = pred.label, pred.confidence
            if label == "line_item":
                # Item-like wording without a quantity (e.g. "Minimum 3 years warranty on all
                # hardware"): fall back to the most likely clause type that is not an item.
                label, confidence = max(((k, v) for k, v in pred.distribution.items() if k != "line_item"), key=lambda kv: kv[1])
                if confidence < 0.1:
                    continue
            if (
                len(tokenize(u.text)) >= 3 and not ex.is_heading(u.text)
                and not ex.labelled_value(u.text + "\n", "client") and not ex.labelled_value(u.text + "\n", "address")
            ):
                # Low-confidence clauses are kept as general context rather than mislabelled.
                if confidence < 0.45:
                    label = "scope"
                mod, actor = modality(u.text)
                requirements.append(Requirement(
                    id=f"R{len(requirements) + 1:02d}", text=u.text, type=label, confidence=round(confidence, 3),
                    section=u.section, clause=u.clause, page=u.page, modality=mod, actor=actor,
                    category=categorise(u.text, u.kind, label, confidence, long_form)))
                req_units.append(u)

        counts: dict[str, int] = {}
        for r in requirements:
            counts[r.type] = counts.get(r.type, 0) + 1
        log.info("Clauses classified", sentences=len(text_units), requirements=len(requirements), by_type=counts,
                 mandatory=sum(r.modality == "mandatory" for r in requirements))

        # --- the parser model reads the whole document and cross-checks the rules
        llm = get_llm()
        if llm is not None:
            raw_items = self._model_reading(llm, text, raw_items, client, terms, dates, log, warnings)
            self._model_clause_types(llm, requirements, req_units, long_form, log)
            counts = {}
            for r in requirements:
                counts[r.type] = counts.get(r.type, 0) + 1

        # --- specifications linked from technical sections ("as per specification 5.1")
        spec_links = self._link_specs(raw_items, sections, units, category_model, log) if long_form else {}

        # --- product resolution
        items = self._resolve_items(raw_items, category_model, log)
        if llm is not None:
            self._model_products(llm, items, log)
            log.info("Language model usage", model=llm.model, **llm.usage.as_dict())
        for raw, item in zip(self._dedupe(raw_items), items):
            sid = spec_links.get(id(raw))
            if sid:
                by_id[sid].line_nos.append(item.line_no)
        line_by_section = {lno: s.id for s in sections for lno in s.line_nos}
        for r in requirements:
            if r.source == "table" and r.category == "technical":
                r.line_no = next((lno for lno, sid in line_by_section.items() if sid == r.section), None)
        if not items:
            warnings.append("No priced line items could be identified in the request.")
        for it in items:
            if it.status == "unmatched":
                warnings.append(f"Line {it.line_no} ('{it.description[:60]}') has no suitable catalogue match and will be excluded.")
            elif it.status == "ambiguous":
                warnings.append(f"Line {it.line_no} matched with low confidence; please confirm {it.selected_sku}.")
        if not dates["due"]:
            warnings.append("No submission deadline found.")
        if not client.country:
            warnings.append("Delivery country not found; domestic supply assumed.")

        document = self._document(layout, sections, requirements, facts, key_dates, eligibility, evaluation, long_form, text)
        parsed = ParsedRfp(
            title=ex.extract_title(text),
            client_reference=reference,
            client=client,
            currency=currency,
            issued_on=dates["issued"],
            due_date=dates["due"],
            delivery_by=dates["delivery"],
            terms=terms,
            line_items=items,
            requirements=requirements,
            requirement_counts=counts,
            warnings=warnings,
            stats={
                "sentences": len(text_units),
                "line_items": len(items),
                "matched": sum(i.status == "matched" for i in items),
                "mean_match_confidence": round(sum(i.match_confidence for i in items) / len(items), 3) if items else 0,
                "pages": layout.pages,
                "sections": len(sections),
                "mandatory": sum(r.modality == "mandatory" for r in requirements),
                "engine": f"{llm.model} with rules" if llm is not None else "rules",
            },
            document=document,
        )
        return parsed

    # ------------------------------------------------------------------ document structure

    def _layout(self, ctx: PipelineContext, log: StageLog) -> Layout:
        data = None
        if ctx.source_path is not None and ctx.source_path.exists():
            data = ctx.source_path.read_bytes()
        layout = analyse(ctx.source_filename, data, ctx.raw_text)
        log.info("Layout analysed", source="original file" if data is not None else "extracted text", **layout.stats())
        return layout

    @staticmethod
    def _units(layout: Layout, sections: list[Section], owner: list[str | None]) -> tuple[list[Unit], dict[int, list[tuple[int, Block]]]]:
        by_id = {s.id: s for s in sections}
        headings = {s.heading_block for s in sections}
        units: list[Unit] = []
        tables: dict[int, list[tuple[int, Block]]] = {}
        headers: dict[int, list[str]] = {}
        for i, b in enumerate(layout.blocks):
            if i in headings:
                continue
            sid = owner[i]
            sec = by_id.get(sid) if sid else None
            kind = sec.kind if sec else "general"
            base_clause = sec.number if sec and sec.number and not sec.keyword else (sec.number if sec else None)
            if b.kind == "row" and b.table is not None:
                tables.setdefault(b.table, []).append((i, b))
                cells = b.cells or []
                if b.table not in headers:
                    headers[b.table] = cells
                    continue
                header = headers[b.table]
                serial = cells[0] if cells and re.fullmatch(r"\d{1,3}\.?|[a-z]\)?", cells[0] or "") else None
                clause = f"{base_clause} ({serial.rstrip('.')})" if base_clause and serial else base_clause
                row_text = " | ".join(c for c in cells if c)
                h = " ".join(header).lower()
                if re.search(r"parameter|specification|feature|attribute", h) and len(cells) >= 2:
                    params = [c for c in cells if c and c != serial]
                    row_text = f"{params[0]}: {' '.join(params[1:])}" if len(params) >= 2 else row_text
                elif re.search(r"criteri|eligib|requirement|condition", h):
                    ci = next((j for j, x in enumerate(header) if re.search(r"criteri|eligib|requirement|condition", x, re.I)), None)
                    if ci is not None and ci < len(cells) and cells[ci]:
                        row_text = cells[ci]
                units.append(Unit(row_text, sid, kind, b.page, clause, source="table", table=b.table, cells=cells, header=header))
                continue
            text = b.text.replace("\t", " ")
            m = CLAUSE_NO.match(text)
            clause = base_clause
            if m and re.match(r"\d", m.group(1)):
                clause = m.group(1)
                text = text[m.end():].strip()
            pieces = split_sentences(text) if len(text) >= 180 else [text.strip()]
            for piece in pieces:
                piece = piece.strip()
                if len(piece) <= 3:
                    continue
                if ex.is_header_field(piece):
                    units.append(Unit(piece, sid, kind, b.page, clause, source="field"))
                elif not ex.is_address_line(piece) and not ex.is_title_line(piece):
                    units.append(Unit(piece, sid, kind, b.page, clause))
        return units, tables

    @staticmethod
    def _is_requirement_row(u: Unit) -> bool:
        h = " ".join(u.header or []).lower()
        if re.search(r"parameter|specification|feature|attribute", h):
            return len(u.text.split()) >= 2
        if re.search(r"criteri|eligib|requirement|condition", h):
            return len(u.text.split()) >= 5
        return False

    @staticmethod
    def _item_kinds(sections: list[Section], tables: dict, owner: list[str | None], long_form: bool) -> set[str] | None:
        if not long_form:
            return None
        if any(s.kind == "boq" for s in sections):
            return {"boq"}
        return {"boq", "scope", "technical", "general", "notice"}

    @staticmethod
    def _scoped_text(layout: Layout, sections: list[Section], owner: list[str | None], long_form: bool) -> str:
        """Text for term extraction: commercial and scope sections first; eligibility and forms excluded."""
        if not long_form:
            return ""
        by_id = {s.id: s for s in sections}
        order = ["commercial", "boq", "scope", "notice", "technical", "evaluation", "conditions", "instructions", "general"]
        parts: dict[str, list[str]] = {k: [] for k in order}
        for i, b in enumerate(layout.blocks):
            sid = owner[i]
            kind = by_id[sid].kind if sid else "general"
            if kind in parts and b.kind == "text":
                parts[kind].append(b.text)
        return normalize("\n".join(line for k in order for line in parts[k]))

    def _link_specs(self, raw_items: list[RawItem], sections: list[Section], units: list[Unit], category_model,
                    log: StageLog) -> dict[int, str]:
        """Attach each schedule line to the technical section that specifies it."""
        tech = [s for s in sections if s.kind == "technical" and not any(c.parent == s.id for c in sections)]
        if not tech:
            return {}
        rows: dict[str, list[str]] = {}
        for u in units:
            if u.section and u.kind == "technical":
                rows.setdefault(u.section, []).append(u.text)
        links: dict[int, str] = {}
        title_cats = {s.id: category_model.predict_one(s.title).label for s in tech}
        for raw in raw_items:
            target = None
            m = re.search(r"(?:specification|spec\.?|clause|section|annexure|item)\s*(?:no\.?\s*)?(\d{1,2}(?:\.\d{1,2})+)", raw.text, re.I)
            if m:
                target = next((s for s in tech if s.number == m.group(1)), None)
            if target is None:
                want = set(analyze(raw.description))
                best, best_score = None, 0.0
                cat = category_model.predict_one(raw.description).label
                same = [s for s in tech if title_cats[s.id] == cat]
                for s in tech:
                    have = set(analyze(s.title))
                    if not have:
                        continue
                    score = len(want & have) / len(have)
                    if title_cats[s.id] == cat:
                        # A section of the same product category; decisive when it is the only one.
                        score += 0.35 + (0.3 if len(same) == 1 else 0.0)
                    if score > best_score:
                        best, best_score = s, score
                target = best if best_score >= 0.6 else None
            if target is None:
                continue
            spec_text = f"{target.title}. " + ". ".join(rows.get(target.id, []))
            specs = extract_specs(spec_text)
            added = {k: v for k, v in specs.items() if k not in raw.specs}
            raw.specs = {**specs, **raw.specs}
            raw.context = spec_text[:600]
            links[id(raw)] = target.id
            log.info("Specification linked to schedule line", line=raw.description[:70], section=target.label,
                     added_specs=added or None)
        return links

    @staticmethod
    def _dedupe(raw_items: list[RawItem]) -> list[RawItem]:
        out, seen = [], set()
        for raw in raw_items:
            key = (fold(raw.description), raw.quantity)
            if key not in seen:
                seen.add(key)
                out.append(raw)
        return out

    @staticmethod
    def _document(layout: Layout, sections: list[Section], requirements: list[Requirement], facts, key_dates, eligibility,
                  evaluation, long_form: bool, text: str) -> TenderDocument:
        out: list[TenderSection] = []
        for s in sections:
            reqs = [r for r in requirements if r.section == s.id]
            out.append(TenderSection(
                id=s.id, number=s.number, title=_display_title(s.label if not s.keyword else s.title), level=s.level, kind=s.kind,
                kind_confidence=s.kind_confidence, parent=s.parent, page_start=s.page_start, page_end=s.page_end,
                requirement_count=len(reqs), mandatory_count=sum(r.modality == "mandatory" for r in reqs), line_nos=s.line_nos,
            ))
        forms = [s.title for s in sections if s.kind == "forms" and s.level == 1]
        return TenderDocument(
            format=layout.format, pages=layout.pages, pages_estimated=layout.pages_estimated, words=len(text.split()),
            tables=layout.tables, scanned_pages=layout.scanned_pages, removed_lines=layout.removed_lines, long_form=long_form,
            sections=out, facts=facts, key_dates=key_dates, eligibility=eligibility, evaluation=evaluation, forms=forms,
            notes=layout.notes,
        )

    # ------------------------------------------------------------------ language model

    def _model_reading(self, llm: LLM, text: str, rule_items: list[RawItem], client: ClientInfo,
                       terms: CommercialTerms, dates: dict[str, str | None], log: StageLog,
                       warnings: list[str]) -> list[RawItem]:
        """Read the document with the parser model; reconcile its items and fill gaps in client and terms."""
        try:
            found = llm_parser.extract(llm, text)
        except LLMError as exc:
            log.warn("Parser model unavailable; items and terms from rules only", error=str(exc))
            return rule_items
        c = found.client
        filled = {}
        for key, value in (("name", c.name), ("contact_name", c.contact_name), ("email", c.email), ("phone", c.phone),
                           ("city", c.city)):
            if value and not getattr(client, key):
                setattr(client, key, value.strip()[:160])
                filled[key] = value
        code = (c.country_code or "").upper()
        if not client.country and code in countries():
            client.country, client.country_name = code, countries()[code].name
            client.region = c.region if c.region in countries()[code].regions else None
            filled["country"] = code
        t = found.terms
        for key, value in (("delivery_days", t.delivery_days), ("payment_days", t.payment_days),
                           ("advance_pct", t.advance_pct), ("warranty_months_required", t.warranty_months)):
            if value is not None and value >= 0 and getattr(terms, key, None) is None:
                setattr(terms, key, value)
                filled[key] = value
        if t.incoterm and not terms.incoterm and t.incoterm.upper() in ex.INCOTERMS:
            terms.incoterm, terms.incoterm_source = t.incoterm.upper(), "read by the parser model"
            filled["incoterm"] = terms.incoterm
        if not dates.get("due") and llm_parser.due_date(found.due_date):
            dates["due"] = found.due_date
            filled["due_date"] = found.due_date
        if filled:
            log.info("Parser model filled fields the rules missed", **filled)

        model_items = [llm_parser.to_raw_item(i) for i in found.items if i.quantity > 0 and i.description.strip()]
        if not model_items:
            log.warn("Parser model listed no items; using the rule-based item list")
            return rule_items
        rec = llm_parser.reconcile(rule_items, model_items)
        log.decision("Items read by the parser model and reconciled with the rules", model_items=len(model_items),
                     rule_items=len(rule_items), agreed=rec.agreed, quantity_differences=rec.quantity_changes or None,
                     only_model=rec.model_only or None, only_rules=rec.rules_only or None)
        for change in rec.quantity_changes:
            warnings.append(f"Quantity differs between readings ({change}); the parser model's value is used — please confirm.")
        for desc in rec.rules_only:
            warnings.append(f"'{desc}' looked like an item to the rules but not to the parser model; it is not priced.")
        for note in found.ambiguities[:5]:
            warnings.append(f"To confirm: {note}")
        return rec.items

    def _model_clause_types(self, llm: LLM, requirements: list[Requirement], req_units: list[Unit], long_form: bool,
                            log: StageLog) -> None:
        """Re-type requirement sentences with the parser model (table rows keep their section's type)."""
        labels = [str(l) for l in registry.clause_classifier().labels if str(l) != "line_item"]
        clauses = [(r.id, r.text) for r in requirements if r.source == "text"]
        try:
            typed = llm_parser.classify(llm, clauses, labels)
        except LLMError as exc:
            log.warn("Parser model could not type the requirements; trained classifier used", error=str(exc))
            return
        changed = 0
        for r, u in zip(requirements, req_units):
            label = typed.get(r.id)
            if label is None or label == r.type:
                continue
            r.type, r.confidence = label, 0.9
            r.category = categorise(u.text, u.kind, label, 0.9, long_form)
            changed += 1
        log.info("Requirement types reviewed by the parser model", typed=len(typed), changed_from_classifier=changed)

    def _model_products(self, llm: LLM, items: list[RequestedItem], log: StageLog) -> None:
        """Let the parser model choose each product among the retrieved candidates."""
        store = catalogue_store()
        lines = []
        for it in items:
            if not it.candidates:
                continue
            cands = []
            for c in it.candidates[:4]:
                p = store.products.get(c.sku)
                if p is not None:
                    cands.append({"sku": p.sku, "name": p.name, "brand": p.brand, "category": p.category,
                                  "specs": llm_parser.spec_summary(p.specs or {}) or p.description[:200]})
            lines.append({"line": it.line_no, "request": it.description[:300], "specs": llm_parser.spec_summary(it.specs),
                          "candidates": cands})
        try:
            choices = llm_parser.choose(llm, lines)
        except LLMError as exc:
            log.warn("Parser model could not choose products; retrieval ranking used", error=str(exc))
            return
        for it in items:
            choice = choices.get(it.line_no)
            if choice is None:
                continue
            if choice.sku is None:
                if it.status == "matched":
                    it.status = "ambiguous"
                log.decision(f"Line {it.line_no}: no candidate meets the request", reason=choice.reason)
                continue
            cand = next(c for c in it.candidates if c.sku == choice.sku)
            cand.reasons.insert(0, f"Chosen by the parser model: {choice.reason}")
            changed = choice.sku != it.selected_sku
            it.selected_sku, it.match_confidence = cand.sku, round(cand.score, 3)
            # The model's choice still has to pass the specification check and the retrieval floor.
            weak = (cand.spec_fit is not None and cand.spec_fit < 0.5) or cand.score < UNMATCHED_THRESHOLD
            it.status = "ambiguous" if weak else "matched"
            log.decision(f"Line {it.line_no}: {'changed to' if changed else 'confirmed'} {cand.sku}", reason=choice.reason)

    def summarize(self, output: ParsedRfp) -> str:  # type: ignore[override]
        s = output.stats
        who = output.client.name or "Unknown client"
        where = output.client.country_name or "unknown location"
        return f"{who} ({where}): {s['line_items']} line items, {s['matched']} matched, {len(output.requirements)} requirements."

    # ------------------------------------------------------------------ pieces

    def _client(self, text: str, ctx: PipelineContext, log: StageLog) -> ClientInfo:
        name, how = ex.extract_client_name(text)
        contact = ex.extract_contact(text)
        loc = ex.extract_location(text)
        segment, seg_source = ex.infer_segment(text, name)
        client = ClientInfo(
            name=name, contact_name=contact["name"], email=contact["email"], phone=contact["phone"],
            country=loc.country, region=loc.region, city=loc.city, segment=segment, segment_source=seg_source,
            tax_id=ex.extract_tax_id(text),
        )
        log.info("Client identified", name=name, method=how, contact=contact["name"])
        log.info("Delivery jurisdiction", country=loc.country, region=loc.region, evidence=loc.evidence)

        customer = self._match_customer(name)
        if customer:
            client.customer_id = customer.id
            client.repeat_customer = customer.deals_won > 0
            client.segment, client.segment_source = customer.segment, "customer master"
            client.tax_id = client.tax_id or customer.tax_id
            if not client.country:
                client.country, client.region = customer.country, customer.region
            elif client.country == customer.country and not client.region:
                client.region = customer.region
            log.decision("Matched existing customer record", customer=customer.name, deals_won=customer.deals_won, segment=customer.segment)
        if not client.country:
            client.country, client.region = ctx.company["country"], None
        c = countries().get(client.country)
        client.country_name = c.name if c else client.country
        client.is_eu = bool(c and c.eu)
        log.info("Buyer segment", segment=client.segment, source=client.segment_source)
        return client

    @staticmethod
    def _match_customer(name: str | None) -> Customer | None:
        if not name:
            return None
        want = set(tokenize(name))
        best, best_score = None, 0.0
        with session_scope() as s:
            for c in s.scalars(select(Customer)):
                have = set(tokenize(c.name))
                if not have or not want:
                    continue
                score = len(want & have) / len(want | have)
                if score > best_score:
                    best, best_score = c, score
        return best if best_score >= 0.6 else None

    def _currency(self, text: str, client: ClientInfo, ctx: PipelineContext, log: StageLog) -> CurrencyInfo:
        code, evidence = ex.extract_currency(text, client.country)
        if code:
            log.decision("Currency taken from explicit pricing instruction", currency=code, evidence=evidence)
            return CurrencyInfo(code=code, source="explicit", evidence=evidence)
        default = country_currency(client.country)
        if default:
            log.decision("Currency defaulted to delivery country currency", currency=default, country=client.country)
            return CurrencyInfo(code=default, source="country_default")
        base = ctx.company["base_currency"]
        log.decision("Currency defaulted to company base currency", currency=base)
        return CurrencyInfo(code=base, source="company_default")

    def _terms(self, text: str, client: ClientInfo, ctx: PipelineContext, log: StageLog) -> CommercialTerms:
        raw = ex.extract_terms(text)
        terms = CommercialTerms(**{k: v for k, v in raw.items() if k in CommercialTerms.model_fields})
        terms.delivery_location = ex.labelled_value(text, "address")
        if terms.incoterm:
            terms.incoterm_source = "stated in request"
        elif client.country != ctx.company["country"]:
            terms.incoterm, terms.incoterm_source = "DDP", "policy default for international supply"
        log.info("Commercial terms", **terms.model_dump(exclude_none=True))
        return terms

    def _resolve_items(self, raw_items: list[RawItem], category_model, log: StageLog) -> list[RequestedItem]:
        store = catalogue_store()
        out: list[RequestedItem] = []
        seen: set[tuple[str, int]] = set()
        for raw in raw_items:
            key = (fold(raw.description), raw.quantity)
            if key in seen:
                continue
            seen.add(key)
            cat = category_model.predict_one(raw.description)
            prior = {c: p for c, p in cat.distribution.items() if p >= 0.05}
            query = f"{raw.description} {raw.context}".strip() if raw.context else raw.description
            hits = store.search(query, k=6, category_prior=prior)
            candidates: list[ProductMatch] = []
            for h in hits:
                product = store.products[h.doc.id]
                fit, reasons = spec_fit(raw.specs, product)
                score = h.score if fit is None else 0.6 * h.score + 0.4 * fit
                if raw.brand:
                    brand = BRAND_ALIASES.get(raw.brand, raw.brand)
                    if brand in fold(product.brand):
                        score += 0.08
                        reasons.append(f"Brand {product.brand} as requested")
                    else:
                        score -= 0.10
                        reasons.append(f"Requested brand '{raw.brand}' differs from {product.brand}")
                # Category coherence: scale by how plausible the product's category is
                # under the trained category model, relative to the most likely one.
                coherence = min(1.0, cat.distribution.get(product.category, 0.0) / max(cat.confidence, 1e-6))
                score *= 0.55 + 0.45 * coherence
                if coherence < 0.5:
                    reasons.append(f"Category {product.category} is unlikely for this request (predicted {cat.label})")
                candidates.append(
                    ProductMatch(
                        sku=product.sku, name=product.name, category=product.category, score=round(max(0.0, min(1.0, score)), 4),
                        retrieval_score=round(h.score, 4), spec_fit=None if fit is None else round(fit, 3), reasons=reasons,
                    )
                )
            candidates.sort(key=lambda c: -c.score)
            best = candidates[0] if candidates else None
            if best is None or best.score < UNMATCHED_THRESHOLD:
                status, sku, conf = "unmatched", None, best.score if best else 0.0
            elif best.score < MATCHED_THRESHOLD or (best.spec_fit is not None and best.spec_fit < 0.5):
                status, sku, conf = "ambiguous", best.sku, best.score
            else:
                status, sku, conf = "matched", best.sku, best.score
            item = RequestedItem(
                line_no=len(out) + 1, text=raw.text, description=raw.description, quantity=raw.quantity,
                quantity_source=raw.quantity_source, unit=raw.unit, category=cat.label,
                category_confidence=round(cat.confidence, 3), specs=raw.specs, brand=raw.brand,
                candidates=candidates[:4], selected_sku=sku, match_confidence=round(conf, 3), status=status,
            )
            out.append(item)
            log.decision(
                f"Line {item.line_no}: {status}",
                request=raw.description[:90], quantity=raw.quantity, quantity_rule=raw.quantity_source,
                predicted_category=cat.label, sku=sku, confidence=item.match_confidence,
                runner_up=candidates[1].sku if len(candidates) > 1 else None,
            )
        return out
