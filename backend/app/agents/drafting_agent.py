"""Proposal Drafting Agent — retrieval-augmented composition.

The agent plans each section from the structured facts produced upstream and
grounds every claim about the company in passages retrieved from the knowledge base
(with the source recorded). Curated sentence templates produce a complete draft;
when the language model is enabled, Claude rewrites the cover letter, executive
summary and highlights from the same client-safe facts and passages, and the text is
checked for internal figures before it replaces the template. The proposal is
rendered into the client quotation and the internal pricing memo.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.messages import (
    CompetitiveAnalysis, ComplianceRow, Evidence, Localisation, Milestone, ParsedRfp, Proposal,
)
from app.finance.money import fmt
from app.llm import drafting as llm_drafting
from app.llm.client import LLMError, get_llm
from app.llm.memory import approved_letters
from app.rag.stores import Passage, knowledge_store

CATEGORY_LABELS = {
    "laptop": "notebooks", "desktop": "desktops", "workstation": "workstations", "monitor": "monitors",
    "network_switch": "network switches", "wireless": "wireless access points", "firewall": "firewalls",
    "router": "routers", "server": "servers", "storage": "storage systems", "storage_media": "drives",
    "power": "power protection", "rack": "racks", "cabling": "structured cabling", "peripheral": "peripherals",
    "printer": "printers", "av": "projectors and collaboration systems",
    "audio": "headsets and headphones", "component": "graphics cards and components", "software": "software licences", "service": "professional services",
}
SIGNATORY = {"name": "Aarav Kulkarni", "title": "Bid Manager", "email": "bids@meridiansystems.in"}
CERT_TOKENS = re.compile(r"(iso\s*/?\s*(?:iec\s*)?\d{4,5}|gdpr|dpdp|soc ?2|energy star|epeat|bis|rohs|ce marking|ukca)", re.I)


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class ProposalDraftingAgent(Agent):
    stage = "drafting"
    name = "Proposal Drafting Agent"
    produces = "proposal"
    consumes = ("parsed", "strategy", "localisation")

    def __init__(self, renderer=None) -> None:
        self._renderer = renderer

    def run(self, ctx: PipelineContext, log: StageLog) -> Proposal:
        parsed: ParsedRfp = ctx.require("parsed")
        strat: CompetitiveAnalysis = ctx.require("strategy")
        loc: Localisation = ctx.require("localisation")
        company = ctx.company
        kb = knowledge_store()
        retrieval_log: list[dict] = []

        def retrieve(purpose: str, query: str, k: int = 2, sentences: bool = True) -> list[Passage]:
            hits = kb.evidence(query, k=k) if sentences else kb.retrieve(query, k=k)
            retrieval_log.append({"purpose": purpose, "query": query,
                                  "passages": [{"source": h.source, "section": h.section, "score": h.score} for h in hits]})
            return hits

        version = int(ctx.overrides.get("_version", 1)) if ctx.overrides else 1
        issued = date.today()
        valid_until = issued + timedelta(days=company["quote_validity_days"])
        prefix = ctx.company.get("quote_prefix") or "".join(w[0] for w in ctx.company["short_name"].split()).upper()
        quote_number = f"{prefix}-Q-{issued.year}-{ctx.rfp_id:04d}"
        money = lambda v: fmt(v, loc.currency, loc.decimals)  # noqa: E731

        categories: dict[str, int] = {}
        for line in strat.lines:
            categories[line.category] = categories.get(line.category, 0) + line.quantity
        # Hardware by volume first; licences and services read naturally at the end.
        ordered = sorted(categories.items(), key=lambda kv: (kv[0] in ("software", "service", "cabling"), -kv[1]))
        uncounted = ("software", "service", "cabling")
        scope_phrase = _join([f"{q:,} {CATEGORY_LABELS.get(k, k)}" if k not in uncounted else CATEGORY_LABELS[k]
                              for k, q in ordered][:5])
        has_services = any(l.category == "service" or (l.bundle and l.bundle.kind == "service") for l in strat.lines)
        c = parsed.client
        location = ", ".join(x for x in [c.city, c.region if c.country == company["country"] else c.country_name] if x) \
            or c.country_name or "your site"
        client = parsed.client.name or "your organisation"

        # ---- cover letter
        contact = parsed.client.contact_name
        salutation = f"Dear {contact}," if contact else "Dear Procurement Team,"
        ref = f" (reference {parsed.client_reference})" if parsed.client_reference else ""
        profile = retrieve("company introduction", f"{parsed.client.segment} {scope_phrase} IT infrastructure partner track record", k=1)
        case = retrieve("relevant experience", f"{parsed.client.segment} {client} {scope_phrase} project case study", k=1)
        bundles = [l for l in strat.lines if l.bundle]
        cover = [
            f"Thank you for inviting {company['name']} to respond to your request for {parsed.title.rstrip('.')}{ref}. "
            f"We are pleased to submit our quotation for the supply{' and installation' if has_services else ''} of "
            f"{scope_phrase}, delivered to {location}.",
        ]
        if profile:
            cover.append(profile[0].text)
        if case and case[0].score >= 0.3:
            cover.append(f"Relevant experience: {case[0].text}")
        value_sentence = ""
        if bundles:
            value_sentence = (f" The offer includes {len(bundles)} value-added service{'s' if len(bundles) > 1 else ''} "
                              f"worth {money(loc.bundled_value)} at no additional charge.")
        cover.append(
            f"Our total offer is {money(loc.grand_total)} including applicable taxes, valid until "
            f"{valid_until.strftime('%d %B %Y')}.{value_sentence}"
        )
        cover.append("We would welcome the opportunity to walk you through this proposal and look forward to working with you.")
        log.info("Cover letter composed", paragraphs=len(cover), grounded_passages=len(profile) + len(case))

        # ---- compliance matrix (from the Tender Compliance Agent when it ran)
        report = ctx.messages.get("compliance")
        if report is not None:
            compliance = [
                ComplianceRow(ref=i.clause or i.id, requirement=i.text, type=i.category, status=i.status, response=i.response,
                              evidence=i.evidence, req_id=i.id)
                for i in report.items
            ]
        else:
            compliance = self._compliance(parsed, strat, loc, retrieve)
        counts: dict[str, int] = {}
        for row in compliance:
            counts[row.status] = counts.get(row.status, 0) + 1
        log.info("Compliance matrix built", rows=len(compliance), by_status=counts)

        # ---- delivery plan & milestones
        max_lead = max((l.lead_time_days for l in strat.lines), default=0)
        international = parsed.client.country != company["country"]
        transit = 6 if international else 2
        milestones = [
            Milestone(label="Purchase order", day=0, detail="Order acknowledgement and confirmed schedule within one business day."),
            Milestone(label="Staging complete", day=max_lead, detail="Goods received, configured and quality-checked at our integration centre."),
            Milestone(label="Delivered to site", day=max_lead + transit,
                      detail=f"{'Air freight, customs clearance and delivery' if international else 'Delivery'} to {location}."),
        ]
        if has_services:
            milestones.append(Milestone(label="Installation and hand-over", day=max_lead + transit + 5,
                                        detail="On-site deployment, acceptance testing and sign-off."))
        plan_q = "staging imaging deployment installation acceptance" if has_services else "delivery lead times dispatch"
        plan = [p.text for p in retrieve("delivery approach", plan_q, k=2)]
        if international:
            plan += [p.text for p in retrieve("international logistics", f"international shipping {parsed.terms.incoterm or 'DDP'} customs", k=1)]
        required = parsed.terms.delivery_days
        completion = milestones[-1].day
        if required:
            plan.append(
                f"Planned completion is day {completion} from purchase order against your requirement of {required} days"
                + ("." if completion <= required else "; we propose phased delivery so in-stock items arrive first.")
            )

        # ---- executive summary
        warranty_min = min((l.warranty_months for l in strat.lines if l.category not in ("software", "service")), default=0)
        exec_summary = [
            f"{company['short_name']} proposes {len(strat.lines)} line items covering {scope_phrase} for {client}.",
            f"Total investment {money(loc.grand_total)}, comprising {money(loc.subtotal)} net and {money(loc.tax_total)} in taxes "
            f"({loc.tax_summary}).",
            f"Delivery to site within {milestones[2].day} days of purchase order"
            + (f", with installation completed by day {completion}." if has_services else "."),
        ]
        if warranty_min:
            exec_summary.append(f"Every hardware item carries at least {warranty_min} months of warranty, registered in your name.")
        highlights = []
        grouped: dict[str, list[str]] = {}
        for l in bundles:
            grouped.setdefault(l.bundle.name, []).append(l.name)
        for name, items in grouped.items():
            highlights.append(f"{name} included at no charge for {_join(items)}")
        if counts:
            highlights.append(f"{counts.get('Complies', 0) + counts.get('Complies with note', 0)} of "
                              f"{sum(v for k, v in counts.items() if k != 'Noted')} stated requirements met")

        inclusions = [
            {"line_no": l.line_no, "item": l.name, "service": l.bundle.name, "quantity": l.quantity,
             "value": round(l.bundle.total_value * loc.fx_effective_rate, loc.decimals),
             "description": l.bundle.description}
            for l in bundles
        ]
        terms = [
            f"Prices are quoted in {loc.currency} and are valid until {valid_until.strftime('%d %B %Y')}.",
            f"Delivery terms: {parsed.terms.incoterm or 'delivered to site'}"
            + (f" {location}" if parsed.terms.incoterm else "") + ".",
            f"Payment: {parsed.terms.payment_days or 30} days from invoice"
            + (f"; {parsed.terms.advance_pct:g}% advance" if parsed.terms.advance_pct else "") + ".",
            f"Taxes: {loc.tax_summary}." + (" " + " ".join(loc.tax_notes) if loc.tax_notes else ""),
        ]
        if loc.currency != loc.base_currency:
            terms.append(f"Exchange basis: 1 {loc.currency} = {1 / loc.fx_effective_rate:,.4f} {loc.base_currency}; "
                         "we absorb currency movements of up to 3% during the validity period.")
        terms.append("Dead-on-arrival units reported within seven days are replaced at no cost.")

        llm = get_llm()
        if llm is not None:
            facts = {
                "supplier": company["name"], "client": client, "contact": contact, "request_title": parsed.title,
                "client_reference": parsed.client_reference, "delivery_location": location,
                "scope": "; ".join(f"{l.name} × {l.quantity:,}" for l in strat.lines),
                "total_including_tax": money(loc.grand_total), "total_before_tax": money(loc.subtotal),
                "tax_treatment": loc.tax_summary, "valid_until": valid_until.strftime("%d %B %Y"),
                "delivery": f"within {milestones[2].day} days of the purchase order",
                "installation_completed_by_day": completion if has_services else None,
                "minimum_hardware_warranty_months": warranty_min or None,
                "included_services": "; ".join(f"{i['service']} for {i['item']} (worth {money(i['value'])})" for i in inclusions),
                "requirements_met": (f"{counts.get('Complies', 0) + counts.get('Complies with note', 0)} of "
                                     f"{sum(v for k, v in counts.items() if k != 'Noted')}") if counts else None,
                "payment": f"{parsed.terms.payment_days or 30} days from invoice",
            }
            passages = [p.text for p in (profile + case)] + [p.text for p in retrieve(
                "drafting context", f"{parsed.client.segment} {scope_phrase} support warranty delivery", k=3)]
            amounts = [loc.grand_total, loc.subtotal, loc.tax_total, loc.bundled_value,
                       *(i["value"] for i in inclusions), *(l.net for l in loc.lines), *(l.unit_price for l in loc.lines)]
            amounts += [float(n.replace(",", "")) for v in facts.values() if isinstance(v, str)
                        for n in re.findall(r"\d[\d,]*(?:\.\d+)?", v)]
            competitors = sorted({o.competitor for l in strat.lines for o in l.market.offers})
            try:
                drafted = llm_drafting.write(llm, facts, passages, approved_letters())
                issues = llm_drafting.problems(drafted, amounts, competitors)
            except LLMError as exc:
                log.warn("Drafting model unavailable; template text kept", error=str(exc))
            else:
                if issues:
                    log.warn("Drafted text failed the client-safety check; template text kept", issues=issues)
                else:
                    salutation, cover = drafted.salutation.strip(), [p.strip() for p in drafted.cover_letter]
                    exec_summary, highlights = drafted.executive_summary, drafted.highlights or highlights
                    log.decision("Cover letter and summary written by the drafting model", model=llm.model,
                                 paragraphs=len(cover), **llm.usage.as_dict())

        proposal = Proposal(
            quote_number=quote_number, version=version, issue_date=issued.isoformat(), valid_until=valid_until.isoformat(),
            salutation=salutation, cover_letter=cover, executive_summary=exec_summary, highlights=highlights,
            compliance=compliance, compliance_counts=counts, delivery_plan=plan, milestones=milestones,
            inclusions=inclusions, terms=terms, signatory=ctx.company.get("signatory", SIGNATORY), retrieval_log=retrieval_log,
        )
        if self._renderer is not None:
            proposal.documents = self._renderer(ctx, proposal)
            log.info("Documents rendered", **proposal.documents)
        log.info("Proposal drafted", retrieval_queries=len(retrieval_log),
                 passages=sum(len(r["passages"]) for r in retrieval_log))
        return proposal

    # ------------------------------------------------------------------ compliance

    def _compliance(self, parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation, retrieve) -> list[ComplianceRow]:
        rows: list[ComplianceRow] = []
        hw = [l for l in strat.lines if l.category not in ("software", "service")]
        min_wty = min((l.warranty_months for l in hw), default=0)
        max_lead = max((l.lead_time_days for l in strat.lines), default=0)
        for req in parsed.requirements:
            if req.type == "scope":
                continue
            hits = retrieve(f"evidence for {req.id}", req.text, k=2)
            ev = [Evidence(source=h.source, section=h.section, text=h.text, score=h.score) for h in hits]
            status, response = "Noted", "Noted and accepted."
            if req.type == "warranty_support":
                need = parsed.terms.warranty_months_required
                if need and hw:
                    short = [l for l in hw if l.warranty_months < need]
                    if short:
                        status = "Complies with note"
                        response = (f"{len(hw) - len(short)} of {len(hw)} hardware lines meet {need} months as quoted; "
                                    f"warranty extensions for {_join([l.name for l in short[:2]])} are available on request.")
                    else:
                        status, response = "Complies", f"All hardware carries {min_wty}+ months of warranty (required {need})."
                else:
                    status, response = "Complies", "Support model described below, with named escalation contacts."
            elif req.type == "delivery":
                need = parsed.terms.delivery_days
                if need:
                    done = max_lead + (6 if parsed.client.country != "IN" else 2)
                    status = "Complies" if done <= need else "Complies with note"
                    response = (f"Delivery by day {done} against the required {need} days." if done <= need
                                else f"Longest lead time is {max_lead} days; phased delivery proposed so in-stock items arrive within {need} days.")
                else:
                    status, response = "Complies", f"Delivery under {parsed.terms.incoterm or 'agreed'} terms as described in the delivery plan."
            elif req.type == "compliance":
                standards = list(dict.fromkeys(t.strip() for t in CERT_TOKENS.findall(req.text)))
                if standards:
                    # Each named standard must be evidenced on its own.
                    covered, missing, ev = [], [], []
                    for std in standards:
                        hit = retrieve(f"{req.id} standard {std}", f"{std} compliance", k=1)
                        norm = lambda t: re.sub(r"[\s/]|iec", "", t.lower())  # noqa: E731
                        if hit and norm(std) in norm(hit[0].text):
                            covered.append(std)
                            ev.append(Evidence(source=hit[0].source, section=hit[0].section, text=hit[0].text, score=hit[0].score))
                        else:
                            missing.append(std)
                    if not missing:
                        status, response = "Complies", f"{_join(covered)}: confirmed; certificates available on request."
                    elif covered:
                        status = "Complies with note"
                        response = f"{_join(covered)} confirmed; please clarify the requirement for {_join(missing)}."
                    else:
                        status, response = "Clarification required", f"Please confirm the requirement for {_join(missing)}."
                elif ev and ev[0].score >= 0.45:
                    status, response = "Complies", "Confirmed; see supporting statement."
                else:
                    status, response = "Clarification required", "Please confirm the specific requirement."
            elif req.type == "payment":
                status = "Complies"
                response = f"Accepted: quotation in {loc.currency}" + (
                    f", payment {parsed.terms.payment_days} days from invoice." if parsed.terms.payment_days else ".")
            elif req.type in ("submission", "evaluation"):
                status, response, ev = "Noted", "Noted.", []
            rows.append(ComplianceRow(ref=req.id, requirement=req.text, type=req.type, status=status, response=response, evidence=ev))
        return rows

    def summarize(self, output: Proposal) -> str:  # type: ignore[override]
        c = output.compliance_counts
        return (f"Quotation {output.quote_number} v{output.version} drafted; {len(output.compliance)} requirements answered "
                f"({c.get('Complies', 0)} complies, {c.get('Clarification required', 0)} need clarification).")
