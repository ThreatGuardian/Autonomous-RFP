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
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import (
    ClientInfo, CommercialTerms, CurrencyInfo, ParsedRfp, ProductMatch, RequestedItem, Requirement,
)
from app.db.models import Customer, Product
from app.db.session import session_scope
from app.ml.registry import registry
from app.nlp import extractors as ex
from app.nlp.gazetteer import countries, country_currency
from app.nlp.line_items import RawItem, build_item, extract_table_items
from app.nlp.text import fold, normalize, split_sentences, tokenize
from app.rag.stores import catalogue_store

MATCHED_THRESHOLD = 0.42
UNMATCHED_THRESHOLD = 0.30
NON_ITEM_CLAUSES = {"delivery", "payment", "submission", "evaluation", "compliance"}
BRAND_ALIASES = {"fortigate": "fortinet", "meraki": "cisco", "hpe": "hpe", "hp": "hp"}


# --------------------------------------------------------------------------- spec fit


def _product_spec_view(p: Product) -> dict[str, Any]:
    s = dict(p.specs or {})
    view: dict[str, Any] = {
        k: s[k] for k in ("ram_gb", "storage_gb", "screen_in", "ports", "capacity_va", "bays")
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
    at_least("cpu_tier", "CPU tier")
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
    for key, label in (("poe", "PoE"), ("resolution", "Resolution"), ("wifi", "Wi-Fi standard"), ("topology", "UPS topology"), ("cpu_family", "CPU family")):
        if key in requested:
            ok = have.get(key) == requested[key]
            scores.append(1.0 if ok else 0.2)
            reasons.append(f"{label} {'matches' if ok else 'differs'}")
    if not scores:
        return None, []
    return sum(scores) / len(scores), reasons


# --------------------------------------------------------------------------- agent


class RfpParserAgent(Agent):
    stage = "intake"
    name = "RFP Parser Agent"
    produces = "parsed"

    def run(self, ctx: PipelineContext, log: StageLog) -> ParsedRfp:
        text = normalize(ctx.raw_text)
        lines = [l for l in text.split("\n")]
        warnings: list[str] = []
        log.info("Document normalised", characters=len(text), lines=len(lines))

        client = self._client(text, ctx, log)
        currency = self._currency(text, client, ctx, log)
        month_first = client.country == "US"
        dates = ex.extract_dates(text, month_first=month_first)
        log.info("Dates resolved by role", **dates)

        terms = self._terms(text, client, ctx, log)

        # --- sentence classification
        clause_model = registry.clause_classifier()
        category_model = registry.category_classifier()
        table_items, consumed = extract_table_items(lines)
        if table_items:
            log.info("Tabular schedule detected", rows=len(table_items))

        units: list[str] = []
        for i, line in enumerate(lines):
            if i in consumed or not line.strip():
                continue
            # Bulleted or short lines are atomic; longer prose is split into sentences.
            if len(line) < 180:
                units.append(line.strip())
            else:
                units.extend(split_sentences(line))
        units = [
            u for u in units
            if len(u) > 3 and not ex.is_header_field(u) and not ex.is_address_line(u) and not ex.is_title_line(u)
        ]
        clause_preds = clause_model.predict(units)

        raw_items: list[RawItem] = list(table_items)
        requirements: list[Requirement] = []
        for idx, (unit, pred) in enumerate(zip(units, clause_preds)):
            candidate = build_item(unit)
            if candidate:
                cat = category_model.predict_one(candidate.description)
                p_item = pred.distribution.get("line_item", 0.0)
                accept = (pred.label == "line_item" and pred.confidence >= 0.4) or (
                    p_item >= 0.2 and cat.confidence >= 0.7 and pred.label not in NON_ITEM_CLAUSES
                )
                if accept:
                    raw_items.append(candidate)
                    continue
                if pred.label == "line_item":
                    log.warn("Quantity-like sentence rejected as line item", text=unit[:120], category_confidence=round(cat.confidence, 3))
            if (
                pred.label != "line_item" and len(tokenize(unit)) >= 3 and not ex.is_heading(unit)
                and not ex.labelled_value(unit + "\n", "client") and not ex.labelled_value(unit + "\n", "address")
            ):
                # Low-confidence clauses are kept as general context rather than mislabelled.
                label = pred.label if pred.confidence >= 0.45 else "scope"
                requirements.append(Requirement(id=f"R{len(requirements) + 1:02d}", text=unit, type=label, confidence=round(pred.confidence, 3)))

        counts: dict[str, int] = {}
        for r in requirements:
            counts[r.type] = counts.get(r.type, 0) + 1
        log.info("Clauses classified", sentences=len(units), requirements=len(requirements), by_type=counts)

        # --- product resolution
        items = self._resolve_items(raw_items, category_model, log)
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

        parsed = ParsedRfp(
            title=ex.extract_title(text),
            client_reference=ex.extract_reference(text),
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
                "sentences": len(units),
                "line_items": len(items),
                "matched": sum(i.status == "matched" for i in items),
                "mean_match_confidence": round(sum(i.match_confidence for i in items) / len(items), 3) if items else 0,
            },
        )
        return parsed

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
            hits = store.search(raw.description, k=6, category_prior=prior)
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
