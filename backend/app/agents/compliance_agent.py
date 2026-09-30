"""Tender Compliance Agent.

Reads the obligations the parser found in the tender and answers each one the
way a bid manager would, from facts rather than generated text:

* **Eligibility** – every pre-qualification criterion is checked against the
  company profile (turnover by financial year, years in business, completed
  similar orders, certifications, OEM authorisations, offices, MSE status).
* **Technical compliance** – every specification row is compared with the
  catalogue data of the product offered for that line; failures name the
  parameter and, where one exists, a compliant alternative.
* **Commercial and contractual terms** – delivery, warranty, support levels,
  payment, liquidated damages, securities and liability are checked against
  lead times, the warranty actually quoted, the support model and policy
  limits, and turned into risk flags.
* **Everything else** is grounded in the knowledge base (retrieval) or recorded
  as an undertaking.

The result is a clause-by-clause compliance matrix, an eligibility verdict, a
document checklist, risk flags and a bid / no-bid recommendation. Reviewer
corrections (status and wording per clause) are applied last and marked.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import (
    ChecklistItem, ComplianceItem, ComplianceReport, EligibilityCheck, EligibilityCriterion, Evidence, InternalPricing,
    ParsedRfp, RiskFlag,
)
from app.agents.parser_agent import spec_fit
from app.db.models import Product
from app.db.session import session_scope
from app.nlp.attributes import check as attribute_check
from app.nlp.line_items import extract_specs
from app.nlp.tender import fmt_inr
from app.nlp.text import analyze, fold
from app.pricing.warranty import months_in
from app.rag.stores import knowledge_store

CERT_TOKENS = re.compile(r"(iso\s*/?\s*(?:iec\s*)?\d{4,5}(?:-\d)?|gdpr|dpdp|soc ?2|energy star|epeat|\bbis\b|rohs|ce marking|ukca|"
                         r"e-waste)", re.I)
GENERIC_STEMS = set(analyze(
    "bidder supplier purchaser shall must provide supply supplied within days day order purchase contract tender bid "
    "equipment item items goods all each per required requirement including include successful work works period"))
MSME_PAYMENT_DAYS = 45
LD_CAP_LIMIT_PCT = 10.0


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


_SEGMENT_SYNONYMS = {"computer": "it", "computers": "it", "ict": "it", "information": "it", "hardware": "hardware",
                     "sale": "supply", "sales": "supply", "trading": "supply", "supplies": "supply"}
_SEGMENT_STOP = {"of", "the", "and", "from", "in", "for", "technology", "products", "equipment"}


def _same_segment(asked: str, held: str) -> bool:
    """'supply of computer hardware' ~ 'it hardware supply'; 'ict system integration' ~ 'system integration'."""
    def toks(t: str) -> set[str]:
        return {_SEGMENT_SYNONYMS.get(w, w) for w in re.findall(r"[a-z]+", t.lower()) if w not in _SEGMENT_STOP}

    a, h = toks(asked), toks(held)
    return bool(a) and (a <= h or h <= a or len(a & h) >= 2)


def _days(text: str) -> int | None:
    m = re.search(r"within\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+(business days|working days|days|weeks|months)",
                  text, re.I)
    if not m:
        return None
    from app.nlp.text import parse_number

    n = parse_number(m.group(1))
    if n is None:
        return None
    unit = m.group(2).lower()
    return int(n * 7 if unit.startswith("week") else n * 30 if unit.startswith("month") else n)


class ComplianceAgent(Agent):
    stage = "compliance"
    name = "Tender Compliance Agent"
    produces = "compliance"
    consumes = ("parsed", "costing")

    def run(self, ctx: PipelineContext, log: StageLog) -> ComplianceReport:
        parsed: ParsedRfp = ctx.require("parsed")
        costing: InternalPricing = ctx.require("costing")
        company = ctx.company
        profile = {"short_name": company.get("short_name", "local"), **company.get("profile", {})}
        doc = parsed.document
        long_form = bool(doc and doc.long_form)
        self._kb = knowledge_store()
        self._log = log
        lines = {l.line_no: l for l in costing.lines}
        value = sum(l.standard_price * l.quantity for l in costing.lines)
        estimate = next((f.amount for f in (doc.facts if doc else []) if f.key == "estimated_value" and f.amount), None)
        with session_scope() as s:
            self._products = {p.sku: p for p in s.scalars(select(Product).where(Product.active.is_(True)))}
        sections = {s.id: s for s in (doc.sections if doc else [])}

        # ---- eligibility
        checks = [self._eligibility(c, profile, costing, estimate or value, parsed) for c in (doc.eligibility if doc else [])]
        overrides = (ctx.overrides or {}).get("eligibility", {})
        for chk in checks:
            ov = overrides.get(chk.id)
            if ov:
                chk.status = ov.get("status", chk.status)
                chk.position = ov.get("position") or chk.position
                chk.overridden = True
        for chk in checks:
            log.decision(f"Eligibility {chk.id}: {chk.status}", criterion=chk.label, position=chk.position)
        verdict = self._verdict(checks)

        # ---- clause-by-clause matrix
        risks: list[RiskFlag] = []
        items: list[ComplianceItem] = []
        by_text = {fold(c.text): c for c in checks}
        for r in parsed.requirements:
            if r.actor != "bidder":
                continue
            if long_form:
                if r.modality == "information" and r.category not in ("warranty", "standards", "delivery"):
                    continue
                if r.modality == "information" and r.type == "scope":
                    continue
            elif r.type == "scope" and r.modality == "information":
                continue
            sec = sections.get(r.section) if r.section else None
            item = ComplianceItem(id=r.id, clause=r.clause, section=r.section, section_title=sec.title if sec else None,
                                  page=r.page, text=r.text, category=r.category, modality=r.modality, line_no=r.line_no,
                                  status="Noted", response="Noted.", basis="Recorded")
            if r.category == "eligibility":
                chk = by_text.get(fold(r.text))
                self._from_eligibility(item, chk)
            elif r.category == "technical" and r.source == "table":
                self._spec_row(item, lines.get(r.line_no) if r.line_no else None, parsed)
            elif r.category == "technical":
                self._undertaking(item, "Technical undertaking")
            elif r.category == "delivery":
                self._delivery(item, parsed, costing, company)
            elif r.category == "warranty":
                self._warranty(item, parsed, costing, profile, risks)
            elif r.category == "standards":
                self._standards(item)
            elif r.category == "commercial":
                self._commercial(item, parsed, profile, value, risks)
            elif r.category == "legal":
                self._legal(item, risks)
            elif r.category in ("submission", "evaluation"):
                item.status, item.response, item.basis = "Noted", "Noted; will be followed in the bid.", "Procedural instruction"
            else:
                self._grounded(item)
            items.append(item)

        # Reviewer corrections win.
        for item in items:
            ov = (ctx.overrides or {}).get("compliance", {}).get(item.id)
            if ov:
                item.status = ov.get("status", item.status)
                item.response = ov.get("response") or item.response
                item.overridden = True
                item.basis = "Reviewer decision"

        risks += self._document_risks(parsed, value, profile)
        risks = self._dedupe_risks(risks)
        counts: dict[str, int] = {}
        for i in items:
            counts[i.status] = counts.get(i.status, 0) + 1
        mandatory = [i for i in items if i.modality == "mandatory" and i.status != "Noted"]
        met = sum(i.status in ("Complies", "Complies with note") for i in mandatory)
        recommendation, reasons = self._recommend(verdict, checks, items, risks)
        checklist = self._checklist(checks, doc.forms if doc else [], costing, profile, parsed)
        benefits = self._benefits(parsed, profile)
        deviations = counts.get("Deviation", 0)
        summary = (f"{met} of {len(mandatory)} mandatory requirements met"
                   + (f", {deviations} deviation(s)" if deviations else "")
                   + f"; eligibility: {verdict.lower()}; recommendation: {recommendation.lower()}.")
        log.info("Compliance matrix built", items=len(items), by_status=counts, mandatory=len(mandatory), mandatory_met=met)
        log.decision(f"Recommendation: {recommendation}", reasons=reasons, eligibility=verdict,
                     high_risks=[r.title for r in risks if r.severity == "high"])
        return ComplianceReport(
            items=items, eligibility=checks, eligibility_verdict=verdict, recommendation=recommendation, reasons=reasons,
            counts=counts, mandatory_total=len(mandatory), mandatory_met=met, risks=risks, checklist=checklist,
            benefits=benefits, contract_value_estimate=round(value, 2), summary=summary,
        )

    def summarize(self, output: ComplianceReport) -> str:  # type: ignore[override]
        return output.summary[:1].upper() + output.summary[1:]

    # ------------------------------------------------------------------ eligibility

    def _eligibility(self, c: EligibilityCriterion, profile: dict, costing: InternalPricing, estimate: float,
                     parsed: ParsedRfp) -> EligibilityCheck:
        chk = EligibilityCheck(id=c.id, kind=c.kind, label=c.label, text=c.text, clause=c.clause, page=c.page,
                               status="Needs review", position="Not in the company profile; review manually.",
                               documents=c.documents)
        p = c.params
        today = date.today()
        if not profile:
            return chk
        if c.kind == "turnover":
            fy = profile.get("turnover_inr", {})
            years = p.get("financial_years") or sorted(fy)[-int(p.get("years") or 3):]
            values = [fy[y] for y in years if y in fy]
            if not values or not p.get("amount"):
                return chk
            basis = min(values) if p.get("basis") == "each year" else sum(values) / len(values)
            chk.evidence = [f"FY {y}: {fmt_inr(fy[y])}" for y in years if y in fy]
            ok = basis >= p["amount"]
            label = "lowest year" if p.get("basis") == "each year" else "average"
            chk.position = f"{label.capitalize()} turnover {fmt_inr(basis)} against {fmt_inr(p['amount'])} required."
            chk.status = "Meets" if ok else "Does not meet"
            seg_text = p.get("segment") or ""
            seg = seg_text.lower()
            if ok and seg:
                share = next((v for k, v in profile.get("turnover_segments_pct", {}).items() if _same_segment(seg, k)), None)
                need = p.get("segment_share_pct")
                if share is not None and need:
                    chk.evidence.append(f"{seg_text} share of turnover: {share}%")
                    if share < need:
                        chk.status, chk.position = "Does not meet", chk.position + f" {seg_text} is {share}% of turnover against {need:g}% required."
                    else:
                        chk.position += f" {seg_text} is {share}% of turnover (at least {need:g}% required)."
                elif share is not None:
                    chk.evidence.append(f"{seg_text}: {share}% of turnover")
                    chk.position += f" {share}% of turnover is from {seg_text}."
                else:
                    chk.status = "Needs review"
                    chk.position += f" Turnover split for '{seg}' is not in the profile; confirm with the CA certificate."
        elif c.kind == "net_worth":
            nw = profile.get("net_worth_inr")
            if nw is not None:
                need = p.get("amount") or 0
                chk.status = "Meets" if nw > 0 and nw >= need else "Does not meet"
                chk.position = f"Net worth {fmt_inr(nw)} as of {profile.get('net_worth_as_of', 'latest audit')}."
        elif c.kind == "experience_years":
            inc = profile.get("incorporated_on")
            if inc and p.get("years"):
                years = (today - date.fromisoformat(inc)).days / 365.25
                chk.status = "Meets" if years >= p["years"] else "Does not meet"
                chk.position = f"Incorporated {date.fromisoformat(inc).strftime('%d %b %Y')} ({years:.0f} years) against {p['years']} required."
                chk.evidence = [profile.get("constitution", ""), f"CIN {profile.get('cin', '')}"]
        elif c.kind == "similar_works":
            window = int(p.get("years") or 7)
            sectors = set(p.get("sectors") or [])
            creds = [cr for cr in profile.get("credentials", [])
                     if (today - date.fromisoformat(cr["completed_on"])).days <= window * 365.25
                     and (not sectors or cr["sector"] in sectors)]
            best = None
            for opt in p.get("options") or []:
                threshold = opt.get("value") or (estimate * opt["pct_of_estimate"] / 100 if opt.get("pct_of_estimate") else None)
                if not threshold:
                    continue
                qualifying = [cr for cr in creds if cr["value_inr"] >= threshold]
                if len(qualifying) >= opt["count"]:
                    best = (opt, threshold, qualifying)
                    break
            scope = f" for {_join(sorted(sectors))} clients" if sectors else ""
            if best:
                opt, threshold, qualifying = best
                chk.status = "Meets"
                chk.position = (f"{len(qualifying)} completed orders of at least {fmt_inr(threshold)}{scope} in the last {window} years "
                                f"({opt['count']} required).")
                chk.evidence = [f"{cr['client']}: {fmt_inr(cr['value_inr'])}, {cr['completed_on'][:7]}" for cr in qualifying[:4]]
            elif p.get("options"):
                chk.status = "Does not meet"
                chk.position = f"Not enough completed orders{scope} of the required value in the last {window} years."
                chk.evidence = [f"{cr['client']}: {fmt_inr(cr['value_inr'])}" for cr in creds[:4]]
        elif c.kind == "supplied_quantity":
            cat, need = p.get("category"), p.get("quantity")
            window = int(p.get("years") or 3)
            sectors = set(p.get("sectors") or [])
            if cat and need:
                creds = [cr for cr in profile.get("credentials", [])
                         if (today - date.fromisoformat(cr["completed_on"])).days <= window * 365.25
                         and (not sectors or cr["sector"] in sectors)]
                total = sum(cr.get("devices", {}).get(cat, 0) for cr in creds)
                chk.status = "Meets" if total >= need else "Does not meet"
                chk.position = f"{total:,} {p.get('item', cat)} supplied{' to ' + _join(sorted(sectors)) + ' clients' if sectors else ''} in the last {window} years against {need:,} required."
                chk.evidence = [f"{cr['client']}: {cr['devices'].get(cat, 0)}" for cr in creds if cr.get("devices", {}).get(cat)]
        elif c.kind == "certification":
            key = lambda std: fold(std).replace(" ", "")  # noqa: E731
            held = {key(x["standard"]): x for x in profile.get("certifications", [])}
            stds = p.get("standards") or []
            have = [s for s in stds if key(s) in held]
            missing = [s for s in stds if s not in have]
            if stds:
                chk.evidence = [f"{held[key(s)]['name']} valid until {held[key(s)]['valid_until']}" for s in have]
                if missing:
                    chk.status = "Does not meet"
                    chk.position = f"{_join(have) + ' held; ' if have else ''}{_join(missing)} not held."
                else:
                    chk.status = "Meets"
                    chk.position = f"{_join(have)} held and valid."
        elif c.kind == "oem_authorisation":
            brands = sorted({l.brand for l in costing.lines if l.category not in ("service",)})
            authorised = {fold(b) for b in profile.get("oem_authorisations", [])}
            missing = [b for b in brands if fold(b) not in authorised]
            if missing:
                chk.status = "Does not meet"
                chk.position = f"Not an authorised partner for {_join(missing)}; change the offered brand or obtain authorisation."
            else:
                chk.status = "Documents required"
                chk.position = f"Authorised partner for all offered brands ({_join(brands)}); a tender-specific MAF is needed from each OEM."
            chk.evidence = [f"Authorised: {_join([b for b in brands if fold(b) in authorised])}"] if brands else []
        elif c.kind == "engineers":
            have, need = profile.get("certified_engineers"), p.get("count")
            if have is not None and need:
                chk.status = "Meets" if have >= need else "Does not meet"
                chk.position = f"{have} certified engineers on payroll against {need} required."
        elif c.kind == "local_presence":
            places = p.get("places") or []
            offices = profile.get("offices", [])
            hits = [o for o in offices if o["state"] in places or o["city"] in places]
            if places:
                chk.status = "Meets" if hits else "Does not meet"
                chk.position = (f"Offices in {_join([o['city'] for o in hits])} ({hits[0]['state']})." if hits
                                else f"No office or service centre in {_join(places)}.")
                chk.evidence = [f"{o['city']}: {o['type']}" for o in hits]
        elif c.kind == "blacklisting":
            if profile.get("blacklisted") is False:
                chk.status = "Documents required"
                chk.position = "Never blacklisted or debarred; self-declaration to be signed."
        elif c.kind == "registration":
            chk.status = "Meets"
            chk.position = f"{profile.get('constitution', 'Registered company')}; GSTIN {profile.get('gstin')}, PAN {profile.get('pan')}."
        elif c.kind == "local_content":
            lc = profile.get("local_content", {})
            chk.status = "Needs review"
            chk.position = f"{lc.get('class', 'Local-content class not recorded')}. {lc.get('note', '')} Confirm the class per item."
        elif c.kind == "msme":
            m = profile.get("msme", {})
            if m.get("valid"):
                chk.status = "Meets"
                chk.position = f"Udyam-registered {m.get('category', '').lower()} enterprise ({m.get('udyam_number')})."
        return chk

    @staticmethod
    def _verdict(checks: list[EligibilityCheck]) -> str:
        if not checks:
            return "Not assessed"
        statuses = {c.status for c in checks}
        if "Does not meet" in statuses:
            return "Not eligible"
        if "Needs review" in statuses:
            return "Review required"
        if "Documents required" in statuses:
            return "Eligible subject to documents"
        return "Eligible"

    @staticmethod
    def _from_eligibility(item: ComplianceItem, chk: EligibilityCheck | None) -> None:
        if chk is None:
            item.status, item.response, item.basis = "Noted", "Noted.", "Eligibility statement"
            return
        mapping = {"Meets": "Complies", "Documents required": "Complies with note", "Needs review": "Complies with note",
                   "Does not meet": "Deviation"}
        item.status = mapping[chk.status]  # type: ignore[assignment]
        item.response = chk.position
        item.basis = f"Eligibility check {chk.id} against company profile"
        item.verify = chk.status == "Needs review"

    # ------------------------------------------------------------------ technical

    def _spec_row(self, item: ComplianceItem, line, parsed: ParsedRfp) -> None:
        if line is None:
            item.status, item.response = "Clarification required", "No line of the schedule is linked to this specification."
            item.basis, item.verify = "Specification not linked to a priced line", True
            return
        product = self._products.get(line.sku)
        param, _, want = item.text.partition(":")
        name = f"{line.brand} {line.name}" if not line.name.lower().startswith(line.brand.lower()) else line.name
        item.basis = f"Compared with catalogue data for {line.sku}"
        if re.match(r"\s*warranty", param, re.I):
            need = months_in(want)
            if need:
                ext = next((a for a in line.included_addons if a.kind == "warranty"), None)
                if line.warranty_months >= need:
                    item.status = "Complies with note" if ext else "Complies"
                    item.response = (f"{name}: {line.warranty_months} months including {ext.name.lower()}, priced in." if ext
                                     else f"{name}: {line.warranty_months} months standard warranty.")
                else:
                    item.status = "Deviation"
                    item.response = (f"{name} carries {line.warranty_months} months and no extension reaches {need}; "
                                     f"propose OEM extended support or seek a clarification.")
                return
        requested = extract_specs(f"{param} {want}")
        if line.category == "component":
            requested.pop("form_factor", None)  # "tower" here describes the host machine, not the card
        if re.match(r"\s*(operating system|os)\b", param, re.I) and product is not None:
            os_have = fold(str((product.specs or {}).get("os", "")))
            ok = "windows 11" in os_have and ("pro" in os_have or "professional" not in fold(want))
            item.status = "Complies" if ok else "Deviation"
            item.response = f"{name}: {(product.specs or {}).get('os', 'OS not recorded')}."
            return
        if product is not None and requested:
            fit, reasons = spec_fit(requested, product)
            if fit is not None:
                failed = [r for r in reasons if "below" in r or "differs" in r or "unlikely" in r]
                if not failed and fit >= 0.99:
                    item.status, item.response = "Complies", f"{name}: {'; '.join(reasons)}."
                elif not failed:
                    item.status, item.response = "Complies with note", f"{name}: {'; '.join(reasons)}."
                    item.verify = True
                else:
                    item.status = "Deviation"
                    alt = self._alternative(line, requested)
                    item.response = f"{name}: {'; '.join(failed)}." + (f" Compliant alternative: {alt}." if alt else
                                                                       " No compliant model in the catalogue.")
                return
        if product is not None:
            met, why = attribute_check(param, want, product)
            if met is True:
                item.status, item.response = "Complies", f"{name}: {why}."
                return
            if met is False:
                item.status = "Deviation"
                alt = next((f"{p.name} ({p.sku})" for p in self._products.values()
                            if p.category == line.category and p.sku != line.sku and attribute_check(param, want, p)[0]), None)
                item.response = f"{name}: {why}." + (f" Compliant alternative: {alt}." if alt else "")
                return
        item.status = "Complies with note"
        item.verify = True
        item.response = f"{name} offered; confirm '{param.strip()}' against the OEM datasheet."
        item.basis = "Parameter not held in catalogue data"

    def _alternative(self, line, requested: dict) -> str | None:
        for p in self._products.values():
            if p.category != line.category or p.sku == line.sku:
                continue
            fit, _ = spec_fit(requested, p)
            if fit is not None and fit >= 0.99:
                return f"{p.name} ({p.sku})"
        return None

    # ------------------------------------------------------------------ commercial and service terms

    def _delivery(self, item: ComplianceItem, parsed: ParsedRfp, costing: InternalPricing, company: dict) -> None:
        about_supply = re.search(r"\bdeliver|\bsuppl(?:y|ied)\b|complet|install|commission|go[- ]live", item.text, re.I) and \
            not re.search(r"survey|submit|furnish|report|plan\b", item.text, re.I)
        need = _days(item.text) if about_supply else None
        lead = max((l.lead_time_days for l in costing.lines), default=0)
        transit = 2 if parsed.client.country == company["country"] else 6
        install = 5 if re.search(r"install|commission", item.text, re.I) else 0
        done = lead + transit + install
        item.basis = "Lead times of offered products plus transit and installation"
        if need:
            if done <= need:
                item.status, item.response = "Complies", f"Planned completion by day {done} against {need} days."
            elif done <= need * 1.5:
                item.status = "Complies with note"
                item.response = f"Longest lead time is {lead} days; phased delivery keeps in-stock items within {need} days."
            else:
                item.status = "Deviation"
                item.response = f"Earliest completion is day {done}, beyond the {need} days required."
        else:
            self._grounded(item, fallback="Accepted; will comply.")

    def _warranty(self, item: ComplianceItem, parsed: ParsedRfp, costing: InternalPricing, profile: dict,
                  risks: list[RiskFlag]) -> None:
        t = item.text
        support = profile.get("support", {})
        need = months_in(t) if re.search(r"warrant", t, re.I) else None
        if need:
            from app.pricing.warranty import months_by_category

            per = months_by_category(t)
            required = lambda l: per.get(l.category, need) if per else need  # noqa: E731
            hw = [l for l in costing.lines if (not per or l.category in per) and l.category not in ("software", "service", "cabling")]
            short = [l for l in hw if l.warranty_months < required(l)]
            extended = [l for l in hw if l.included_addons and l.warranty_months >= required(l)]
            item.basis = "Warranty quoted per line (including mandated extensions)"
            spans = sorted(set(per.values())) if per else [need]
            label = " / ".join(f"{m}-month" for m in spans)
            if short:
                item.status = "Deviation"
                item.response = (f"{_join([l.name for l in short[:3]])} cannot be offered with the required cover; "
                                 f"{len(hw) - len(short)} of {len(hw)} lines comply.")
            elif extended:
                item.status = "Complies with note"
                item.response = f"{label} cover quoted as required; extended warranty priced in for {len(extended)} line(s)."
            else:
                item.status, item.response = "Complies", f"All covered lines carry the required {label} warranty."
            return
        hours = re.findall(r"within\s+(\d+)\s*(?:hours|hrs)", t, re.I) if re.search(r"attend|respon|report", t, re.I) else []
        if re.search(r"standby|replacement unit", t, re.I):
            item.status, item.basis = "Complies", "Support model"
            item.response = "Accepted; standby units will be held at our service location for the warranty period."
            return
        if re.search(r"24\s*[x×/]\s*7|round the clock|24 hours a day", t, re.I):
            if support.get("helpdesk_24x7"):
                item.status, item.response = "Complies", "24x7 helpdesk operated."
            else:
                item.status = "Complies with note"
                item.response = (f"Current service desk hours are {support.get('helpdesk_hours', 'business hours')}; "
                                 "24x7 cover to be provided through an extended rota for this contract.")
                item.verify = True
                risks.append(RiskFlag(title="24x7 helpdesk commitment", severity="medium", clause=item.clause, page=item.page,
                                      detail="The tender requires round-the-clock support; our service desk is not 24x7 today."))
            item.basis = "Support model in company profile"
            return
        if hours:
            respond = int(hours[0])
            city = parsed.client.city
            offices = {o["city"] for o in profile.get("offices", [])}
            within = support.get("onsite_response_hours", 8)
            item.basis = "Support levels in company profile"
            if respond >= within and (not city or city in offices):
                item.status, item.response = "Complies", f"On-site response within {within} hours from our {city or 'nearest'} office."
            else:
                item.status = "Complies with note"
                where = f"{city} has no {profile.get('short_name', 'local')} office" if city and city not in offices else "response time is tighter than standard"
                item.response = (f"{where[:1].upper() + where[1:]}; a field engineer will be stationed locally for the warranty "
                                 f"period to meet the {respond}-hour response.")
                item.verify = True
                risks.append(RiskFlag(title="On-site response obligation", severity="medium", clause=item.clause, page=item.page,
                                      detail=f"{respond}-hour response at {city or 'site'} needs a locally based engineer; "
                                             "provision the cost in the price."))
            return
        if re.search(r"resident engineer|onsite engineer|on-site engineer|dedicated (?:onsite )?engineer", t, re.I):
            item.status, item.basis = "Complies with note", "Manpower commitment"
            item.response = "Resident engineer will be deployed as specified; manpower cost to be provisioned in the price."
            risks.append(RiskFlag(title="Resident engineer", severity="low", clause=item.clause, page=item.page,
                                  detail="Dedicated manpower is required after go-live; ensure it is costed."))
            return
        self._grounded(item, fallback="Accepted; will comply.")

    def _standards(self, item: ComplianceItem) -> None:
        standards = list(dict.fromkeys(t.strip() for t in CERT_TOKENS.findall(item.text)))
        item.basis = "Knowledge base (certifications and compliance)"
        if not standards:
            self._grounded(item, fallback="Accepted; will comply.")
            return
        covered, missing, ev = [], [], []
        norm = lambda t: re.sub(r"[\s/]|iec", "", t.lower())  # noqa: E731
        for std in standards:
            hits = self._kb.evidence(f"{std} compliance", k=1)
            if hits and norm(std) in norm(hits[0].text):
                covered.append(std)
                ev.append(Evidence(source=hits[0].source, section=hits[0].section, text=hits[0].text, score=hits[0].score))
            else:
                missing.append(std)
        item.evidence = ev
        if not missing:
            item.status, item.response = "Complies", f"{_join(covered)}: confirmed; certificates available."
        elif covered:
            item.status, item.response = "Complies with note", f"{_join(covered)} confirmed; {_join(missing)} to be confirmed."
        else:
            item.status, item.response = "Clarification required", f"Please confirm the requirement for {_join(missing)}."

    def _commercial(self, item: ComplianceItem, parsed: ParsedRfp, profile: dict, value: float, risks: list[RiskFlag]) -> None:
        t = item.text
        item.status, item.response, item.basis = "Complies", "Accepted.", "Commercial term accepted"
        m = re.search(r"within\s+(\d+)\s+days[^.]*invoice|payment[^.]*within\s+(\d+)\s+days", t, re.I)
        if m:
            days = int(m.group(1) or m.group(2))
            if days > MSME_PAYMENT_DAYS:
                item.status = "Complies with note"
                item.response = (f"Accepted; as a registered MSE we request payment within {MSME_PAYMENT_DAYS} days in line with "
                                 "Section 15 of the MSMED Act, 2006.")
                risks.append(RiskFlag(title="Payment beyond 45 days", severity="medium", clause=item.clause, page=item.page,
                                      detail=f"{days}-day payment term exceeds the MSMED Act limit for MSE suppliers."))
            else:
                item.response = f"Accepted: payment within {days} days of invoice."
            return
        if re.search(r"liquidated damages", t, re.I):
            m = re.search(r"(\d(?:\.\d+)?)\s*%[^.]{0,80}?(week|day|month)[^.]*?maximum (?:of )?(\d{1,2})\s*%", t, re.I)
            if m:
                cap = float(m.group(3))
                item.status = "Complies with note"
                item.response = f"Accepted; maximum exposure {cap:g}% of contract value (about {fmt_inr(value * cap / 100)})."
                risks.append(RiskFlag(title="Liquidated damages", severity="high" if cap > LD_CAP_LIMIT_PCT else "low",
                                      clause=item.clause, page=item.page,
                                      detail=f"{m.group(1)}% per {m.group(2)} up to {cap:g}% (≈ {fmt_inr(value * cap / 100)})."))
            return
        # The rate must belong to the guarantee itself ("performance security of 3% of the order value"), not
        # to a payment clause that merely mentions it ("balance 10% after submission of the performance security").
        pbg = re.search(r"performance (?:security|bank guarantee|guarantee)[^.%]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%", t, re.I)
        if pbg:
            m = pbg
            if m:
                pct = float(m.group(1))
                item.response = f"Accepted; bank guarantee of {pct:g}% (about {fmt_inr(value * pct / 100)}) will be furnished."
                risks.append(RiskFlag(title="Performance security", severity="low", clause=item.clause, page=item.page,
                                      detail=f"{pct:g}% bank guarantee blocks about {fmt_inr(value * pct / 100)} of credit limits."))
            return
        if re.search(r"\bemd\b|earnest money|bid security", t, re.I) and profile.get("msme", {}).get("valid") and \
                re.search(r"forfeit|refund|exempt", t, re.I):
            item.response = "Accepted; EMD exemption claimed as a Udyam-registered small enterprise."
            return
        if re.search(r"advance", t, re.I) and re.search(r"bank guarantee", t, re.I):
            item.status, item.response = "Complies with note", "Accepted; advance will be claimed against an advance bank guarantee."
            return
        if re.search(r"firm|fixed|no price variation|price variation", t, re.I):
            item.status = "Complies with note"
            item.response = "Accepted; prices held firm, with currency exposure on imported hardware covered by the FX buffer."
            return
        if re.search(r"paid|payment", t, re.I) and "%" in t:
            item.response = "Accepted as per the milestone schedule."

    def _legal(self, item: ComplianceItem, risks: list[RiskFlag]) -> None:
        t = item.text
        item.status, item.response, item.basis = "Complies", "Accepted.", "Contract condition accepted"
        if re.search(r"unlimited liability", t, re.I):
            item.status = "Deviation"
            item.response = "We propose that aggregate liability be capped at the contract value, except for fraud or wilful misconduct."
            item.basis = "Liability policy: capped at contract value"
            risks.append(RiskFlag(title="Unlimited liability", severity="high", clause=item.clause, page=item.page,
                                  detail="The tender asks for unlimited liability; seek a cap at the pre-bid meeting."))
        elif re.search(r"indemnif", t, re.I):
            item.status, item.response = "Complies with note", "Accepted; IP indemnity is backed by the OEMs' indemnities."
        elif re.search(r"terminat\w* for convenience|terminate the contract for convenience", t, re.I):
            item.status, item.response = "Complies with note", "Accepted; we request payment for goods delivered up to termination."
            risks.append(RiskFlag(title="Termination for convenience", severity="low", clause=item.clause, page=item.page,
                                  detail="The buyer may terminate without cause."))
        elif re.search(r"data protection|dpdp|personal data", t, re.I):
            self._standards(item)
        elif re.search(r"sub-?contract", t, re.I):
            item.status, item.response = "Complies with note", "Accepted; installation manpower is engaged under our direct supervision."

    def _undertaking(self, item: ComplianceItem, basis: str) -> None:
        item.status, item.response, item.basis = ("Complies", "Accepted; will comply.", basis) if item.modality != "information" \
            else ("Noted", "Noted.", basis)

    def _grounded(self, item: ComplianceItem, fallback: str = "Accepted; will comply.") -> None:
        # Evidence must share real subject matter with the clause, not just procurement vocabulary.
        want = set(analyze(item.text)) - GENERIC_STEMS
        def relevant(h) -> bool:
            shared = want & (set(analyze(h.text)) | set(analyze(h.section)))
            return h.score >= 0.4 and len(shared) >= 2 and len(shared) / max(1, min(len(want), 8)) >= 0.35

        hits = [h for h in self._kb.evidence(item.text, k=3) if relevant(h)]
        item.evidence = [Evidence(source=h.source, section=h.section, text=h.text, score=h.score) for h in hits[:2]]
        if hits:
            item.status, item.response, item.basis = "Complies", "Confirmed; see supporting statement.", "Knowledge base evidence"
        elif item.modality == "information":
            item.status, item.response, item.basis = "Noted", "Noted.", "Informational clause"
        else:
            item.status, item.response, item.basis = "Complies", fallback, "Undertaking"

    # ------------------------------------------------------------------ roll-up

    @staticmethod
    def _document_risks(parsed: ParsedRfp, value: float, profile: dict) -> list[RiskFlag]:
        out: list[RiskFlag] = []
        doc = parsed.document
        if not doc:
            return out
        for f in doc.facts:
            if f.key == "reverse_auction":
                out.append(RiskFlag(title="Reverse auction", severity="medium", page=f.page,
                                    detail="Final prices are discovered in a reverse auction; hold back negotiation room."))
        for n in doc.evaluation.notes:
            if "Quantities may be varied" in n:
                out.append(RiskFlag(title="Quantity variation", severity="low",
                                    detail="Quantities may change at award at the same unit rates; check tier-discount assumptions."))
        due = parsed.due_date
        if due:
            days = (date.fromisoformat(due) - date.today()).days
            if 0 <= days <= 7:
                out.append(RiskFlag(title="Deadline close", severity="high", detail=f"Bids are due in {days} day(s)."))
        return out

    @staticmethod
    def _dedupe_risks(risks: list[RiskFlag]) -> list[RiskFlag]:
        seen, out = set(), []
        for r in sorted(risks, key=lambda r: {"high": 0, "medium": 1, "low": 2}[r.severity]):
            if r.title not in seen:
                seen.add(r.title)
                out.append(r)
        return out

    @staticmethod
    def _recommend(verdict: str, checks: list[EligibilityCheck], items: list[ComplianceItem],
                   risks: list[RiskFlag]) -> tuple[str, list[str]]:
        reasons: list[str] = []
        failed = [c for c in checks if c.status == "Does not meet"]
        deviations = [i for i in items if i.status == "Deviation" and i.modality == "mandatory"]
        if failed:
            for c in failed:
                reasons.append(f"Eligibility not met — {c.label.lower()}: {c.position}")
            reasons.append("Raise the gap at the pre-bid meeting; bid only if the criterion is relaxed.")
            return "Do not bid", reasons
        if deviations:
            reasons.append(f"{len(deviations)} mandatory requirement(s) cannot be met as specified; declare them as deviations "
                           "or seek clarification.")
        review = [c for c in checks if c.status == "Needs review"]
        if review:
            reasons.append(f"{len(review)} eligibility criterion(s) need manual confirmation: {_join([c.label for c in review])}.")
        high = [r for r in risks if r.severity == "high"]
        if high:
            reasons.append(f"High risks: {_join([r.title for r in high])}.")
        if deviations or high or review:
            return "Bid with clarifications", reasons
        reasons.append("Eligible, technically compliant and no high contractual risk.")
        return "Bid", reasons

    @staticmethod
    def _checklist(checks: list[EligibilityCheck], forms: list[str], costing: InternalPricing, profile: dict,
                   parsed: ParsedRfp) -> list[ChecklistItem]:
        out: list[ChecklistItem] = []
        defaults = {
            "turnover": ("Audited financial statements and CA turnover certificate", "Ready"),
            "net_worth": ("CA certificate of net worth", "Ready"),
            "experience_years": ("Certificate of incorporation", "Ready"),
            "similar_works": ("Work orders with completion certificates", "Ready"),
            "supplied_quantity": ("Supply orders and delivery certificates", "Ready"),
            "certification": ("Copies of certificates", "Ready"),
            "engineers": ("List of certified engineers with certificates", "To prepare"),
            "local_presence": ("Proof of office / service centre", "Ready"),
            "blacklisting": ("Self-declaration of non-blacklisting", "To prepare"),
            "registration": ("GST registration and PAN", "Ready"),
            "local_content": ("Local-content self-certificate", "To prepare"),
        }
        for c in checks:
            if c.kind == "oem_authorisation":
                for brand in sorted({l.brand for l in costing.lines if l.category != "service"}):
                    out.append(ChecklistItem(name=f"Manufacturer's authorisation form – {brand}", status="To obtain",
                                             source=c.clause, note="Tender-specific MAF from the OEM"))
                continue
            name, status = defaults.get(c.kind, (c.documents or c.label, "To prepare"))
            if c.status == "Does not meet":
                status = "To obtain"
            out.append(ChecklistItem(name=c.documents or name, status=status, source=c.clause,  # type: ignore[arg-type]
                                     note=c.position if c.status != "Meets" else None))
        m = profile.get("msme", {})
        doc = parsed.document
        if m.get("valid") and doc and any(f.key == "emd" for f in doc.facts) and any(f.key == "msme" for f in doc.facts):
            out.append(ChecklistItem(name="Udyam registration certificate (EMD / fee exemption)", status="Ready",
                                     note=m.get("udyam_number")))
        for f in forms:
            out.append(ChecklistItem(name=f, status="To prepare", source="Annexure"))
        seen, unique = set(), []
        for c in out:
            if fold(c.name) not in seen:
                seen.add(fold(c.name))
                unique.append(c)
        return unique

    @staticmethod
    def _benefits(parsed: ParsedRfp, profile: dict) -> list[str]:
        out: list[str] = []
        doc = parsed.document
        m = profile.get("msme", {})
        if not doc or not m.get("valid"):
            return out
        emd = next((f for f in doc.facts if f.key == "emd"), None)
        msme = next((f for f in doc.facts if f.key == "msme"), None)
        if emd and emd.amount and msme:
            out.append(f"EMD of {fmt_inr(emd.amount)} waived as a Udyam-registered {m.get('category', '').lower()} enterprise.")
        fee = next((f for f in doc.facts if f.key == "tender_fee"), None)
        if fee and msme and msme.value.startswith("EMD"):
            out.append("Tender fee exemption available to MSEs.")
        if any("Purchase preference" in n for n in doc.evaluation.notes):
            out.append("MSE purchase preference: may be offered a share of the order by matching L1 if within 15% of L1.")
        return out

