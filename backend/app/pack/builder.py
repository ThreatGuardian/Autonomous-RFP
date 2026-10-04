"""Full response pack: everything a bidder uploads or hands in, filled from company data.

The pack is assembled from what the agents already produced plus the company
profile and knowledge base:

* **Technical proposal** (PDF and editable Word) – covering letter, bidder
  information form, eligibility statement with evidence, item-by-item technical
  compliance (make and model offered against every specification row),
  commercial and general conditions, deviations, delivery plan, warranty and
  support, declarations (non-blacklisting, MSE, local content, integrity) and
  the document checklist mapped to the pack.
* **Compliance statement** (the Tender Compliance Agent's PDF).
* **Financial bid** – the priced quotation, kept apart for the price envelope.
* **OEM authorisation requests** – one letter per brand offered, asking the
  manufacturer for the tender-specific authorisation form.
* **Submission index** – what goes in which envelope.

Nothing is invented: every value comes from the profile, the parsed tender,
the priced lines or retrieved knowledge-base passages; gaps are left as
bracketed placeholders for the bid team.
"""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from app.agents.messages import CompetitiveAnalysis, ComplianceReport, InternalPricing, ParsedRfp, Proposal
from app.finance.money import fmt
from app.nlp.tender import fmt_inr
from app.rag.stores import knowledge_store
from app.report.export import render_docx, render_pdf

STATUS_WORD = {"Complies": "Yes", "Complies with note": "Yes, with note", "Clarification required": "Clarification",
               "Deviation": "No – deviation", "Noted": "Noted"}


def _p(text: str) -> dict:
    return {"type": "paragraph", "text": text}


def _table(header: list[str], rows: list[list[str]], widths: list[float] | None = None) -> dict:
    block = {"type": "table", "header": header, "rows": rows}
    if widths:
        block["widths"] = widths
    return block


def _date(iso: str | None) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d %B %Y") if iso else "[date]"
    except ValueError:
        return iso or "[date]"


def _signature(company: dict) -> dict:
    s = company.get("signatory", {})
    return _p(f"For {company['name']}  ·  {s.get('name', '[authorised signatory]')}, {s.get('title', '')}  ·  "
              f"Place: {company['address_lines'][-2].split(',')[-1].strip() if len(company['address_lines']) > 1 else ''}  ·  "
              f"Date: {date.today().strftime('%d %B %Y')}  ·  (Signature and seal)")


def technical_proposal(company: dict, parsed: ParsedRfp, costing: InternalPricing, strategy: CompetitiveAnalysis,
                       compliance: ComplianceReport | None, proposal: Proposal) -> dict[str, Any]:
    prof = company.get("profile", {})
    client = parsed.client
    ref = parsed.client_reference or "[RFP reference]"
    subject = parsed.title
    sections: list[dict] = []
    facts = parsed.document.facts if parsed.document else []
    validity = next((f.value for f in facts if "validity" in f.key or "validity" in f.label.lower()), None)

    # 1. covering letter
    letter = [
        _p(f"To, {client.contact_name or 'The Purchase Officer'}, {client.name or '[purchaser]'}"
           + (f", {client.city}" if client.city else "") + "."),
        _p(f"Subject: Technical proposal against {ref} – {subject}."),
        _p("Sir or Madam,"),
        _p(f"Having examined the RFP document including all annexures and corrigenda, we, {company['name']}, offer to "
           f"supply, install and commission the equipment in conformity with the said document. Our financial bid is "
           f"submitted separately in the prescribed format. We undertake, if our proposal is accepted, to deliver and "
           f"commission the goods within the period specified and to furnish the performance security required."),
        _p("We agree to abide by this proposal for the validity period stated in the RFP"
           + (f" ({validity})" if validity else "")
           + " and it shall remain binding upon us. We confirm that we have no conflict of interest and that the "
             "information given in this proposal is true and correct."),
        _signature(company),
    ]
    sections.append({"key": "letter", "title": "Covering letter", "blocks": letter})

    # 2. bidder information
    msme = prof.get("msme", {})
    fy = prof.get("turnover_inr", {})
    info = [
        ["Name of the bidder", prof.get("legal_name", company["name"])],
        ["Constitution", prof.get("constitution", "")],
        ["Date of incorporation", _date(prof.get("incorporated_on"))],
        ["CIN", prof.get("cin", "")], ["PAN", prof.get("pan", "")], ["GSTIN", prof.get("gstin", company.get("tax_id", ""))],
        ["MSME (Udyam) registration", f"{msme.get('udyam_number', '—')} ({msme.get('category', '')} enterprise)" if msme else "—"],
        ["Registered address", ", ".join(company["address_lines"])],
        ["Offices and service centres", "; ".join(f"{o['city']} – {o['type']}" for o in prof.get("offices", []))],
        ["Contact", f"{company.get('phone', '')} · {company.get('email', '')} · {company.get('website', '')}"],
        ["Authorised signatory", f"{company.get('signatory', {}).get('name', '')}, {company.get('signatory', {}).get('title', '')}"],
        ["Annual turnover", "; ".join(f"FY {y}: {fmt_inr(v)}" for y, v in sorted(fy.items())[-3:])],
        ["Net worth", f"{fmt_inr(prof['net_worth_inr'])} as of {_date(prof.get('net_worth_as_of'))}" if prof.get("net_worth_inr") else "—"],
        ["Quality certifications", "; ".join(f"{c['name']} (valid until {_date(c['valid_until'])})" for c in prof.get("certifications", []))],
        ["Bank", f"{company['bank']['name']}, A/c {company['bank']['account']}, IFSC {company['bank']['ifsc']}"],
    ]
    sections.append({"key": "bidder", "title": "Bidder information form", "blocks": [
        _table(["Particular", "Details"], info, [32, 68])]})

    # 3. eligibility
    if compliance and compliance.eligibility:
        rows = [[c.id, c.text, c.position + (f" Evidence: {'; '.join(c.evidence[:3])}." if c.evidence else ""),
                 c.documents or "—"] for c in compliance.eligibility]
        sections.append({"key": "eligibility", "title": "Eligibility criteria – bidder's statement", "blocks": [
            _p("Our position against each eligibility criterion, with the supporting documents enclosed in this pack."),
            _table(["No.", "Criterion", "Our position", "Documents enclosed"], rows, [7, 38, 37, 18])]})

    # 4. technical compliance per item
    tech: list[dict] = [_p("Make and model offered against each item of the schedule, and our compliance with every "
                           "parameter of the technical specification.")]
    offered = [[str(l.line_no), l.requested[:90], f"{l.brand} {l.name}" if not l.name.startswith(l.brand) else l.name,
                l.mpn, str(l.quantity), f"{l.warranty_months} months"] for l in costing.lines]
    tech.append(_table(["Item", "Requested", "Make and model offered", "Part number", "Qty", "Warranty"], offered,
                       [8, 29, 28, 16, 7, 12]))
    if compliance:
        by_line: dict[int, list] = {}
        for it in compliance.items:
            if it.line_no is not None and it.category == "technical":
                by_line.setdefault(it.line_no, []).append(it)
        for l in costing.lines:
            rows = []
            for it in by_line.get(l.line_no, []):
                param, _, want = it.text.partition(":")
                rows.append([param.strip(), want.strip() or it.text, it.response, STATUS_WORD.get(it.status, it.status)])
            if rows:
                tech.append({"type": "note", "text": f"Item {l.line_no} – {l.name} ({l.mpn})"})
                tech.append(_table(["Parameter", "Required", "Offered", "Complies"], rows, [16, 30, 40, 14]))
    sections.append({"key": "technical", "title": "Technical compliance statement", "blocks": tech})

    # 5. commercial and general conditions
    if compliance:
        cond = [it for it in compliance.items if it.category in ("commercial", "delivery", "warranty", "legal", "standards",
                                                                    "conditions", "instructions")]
        rows = [[it.clause or "—", it.text[:220], STATUS_WORD.get(it.status, it.status), it.response] for it in cond]
        if rows:
            sections.append({"key": "conditions", "title": "Commercial terms and conditions of contract", "blocks": [
                _table(["Clause", "Condition", "Accepted", "Our response"], rows, [9, 43, 12, 36])]})
        devs = [it for it in compliance.items if it.status in ("Deviation", "Clarification required")]
        sections.append({"key": "deviations", "title": "Statement of deviations", "blocks": [
            _table(["Clause", "Requirement", "Deviation or clarification"],
                   [[it.clause or "—", it.text[:200], it.response] for it in devs], [10, 45, 45]) if devs else
            _p("Nil. Our offer complies with all terms, conditions and specifications of the RFP.")]})

    # 6. delivery plan
    plan = [{"type": "bullets", "items": proposal.delivery_plan}] if proposal.delivery_plan else []
    if proposal.milestones:
        plan.append(_table(["Milestone", "Day", "Detail"], [[m.label, f"Day {m.day}", m.detail] for m in proposal.milestones],
                           [30, 12, 58]))
    if plan:
        sections.append({"key": "delivery", "title": "Delivery and implementation plan", "blocks": plan})

    # 7. warranty and support (grounded in the knowledge base)
    kb = knowledge_store()
    support = []
    for q in ("warranty registration replacement", "helpdesk on-site service response", "installation imaging asset tagging"):
        for ev in kb.evidence(q, k=1):
            if ev.text not in support:
                support.append(ev.text)
    s = prof.get("support", {})
    if s:
        support.append(f"Helpdesk {s.get('helpdesk_hours', '')}; on-site response within {s.get('onsite_response_hours')} "
                       f"hours {s.get('onsite_response_scope', '')}; resolution target {s.get('resolution_hours')} hours.")
    if support:
        sections.append({"key": "support", "title": "Warranty, service and support", "blocks": [{"type": "bullets", "items": support}]})

    # 8. declarations
    decl = [
        {"type": "note", "text": "Declaration regarding blacklisting"},
        _p(f"We, {company['name']}, hereby declare that our firm has not been blacklisted or debarred by any Central or "
           f"State Government department, university, PSU or local body as on the date of submission of this proposal."),
    ]
    if msme.get("valid"):
        decl += [{"type": "note", "text": "Declaration of MSE status"},
                 _p(f"We declare that we are a {msme.get('category', '').lower()} enterprise registered on the Udyam portal "
                    f"under number {msme.get('udyam_number')}, valid on the date of submission, and claim the benefits "
                    f"available to MSEs under the Public Procurement Policy for MSEs Order, 2012 (exemption from EMD and "
                    f"tender fee, and purchase preference).")]
    lc = prof.get("local_content", {})
    if lc:
        decl += [{"type": "note", "text": "Self-certificate of local content"},
                 _p(f"We certify that we are a {lc.get('class', '[class]')} under the Public Procurement (Preference to Make "
                    f"in India) Order, 2017. {lc.get('note', '')}")]
    decl += [{"type": "note", "text": "Integrity undertaking"},
             _p("We undertake that we have not offered and will not offer any gift, inducement or consideration to any "
                "officer of the purchaser in connection with this RFP, and that we have not colluded with other bidders."),
             _signature(company)]
    sections.append({"key": "declarations", "title": "Declarations", "blocks": decl})

    # 9. checklist
    if compliance and compliance.checklist:
        where = {"Ready": "Enclosed", "To prepare": "Prepared in this pack", "To obtain": "To be obtained"}
        rows = [[str(i + 1), c.name, where.get(c.status, c.status), c.note or c.source or ""]
                for i, c in enumerate(compliance.checklist)]
        sections.append({"key": "checklist", "title": "Checklist of documents", "blocks": [
            _table(["No.", "Document", "Status", "Source or note"], rows, [7, 45, 18, 30])]})

    return {"title": f"Technical proposal – {client.name or 'purchaser'}", "subtitle": f"{ref} · {subject} · submitted by "
            f"{company['name']}", "quote_number": proposal.quote_number,
            "sections": [{**s, "hidden": False} for s in sections]}


def maf_letters(company: dict, parsed: ParsedRfp, costing: InternalPricing) -> dict[str, Any]:
    brands: dict[str, list] = {}
    for l in costing.lines:
        if l.category not in ("service", "software"):
            brands.setdefault(l.brand, []).append(l)
    sections = []
    for brand, lines in sorted(brands.items()):
        items = [f"{l.name} ({l.mpn}), quantity {l.quantity}" for l in lines]
        sections.append({"key": f"maf-{brand}", "title": f"Request for authorisation – {brand}", "blocks": [
            _p(f"To, The Channel Manager, {brand} India."),
            _p(f"Subject: Manufacturer's Authorisation Form for {parsed.client_reference or 'the RFP'} of "
               f"{parsed.client.name or 'the purchaser'}."),
            _p(f"We, {company['name']}, an authorised partner of {brand}, intend to bid against the above RFP"
               + (f", due on {_date(parsed.due_date)}" if parsed.due_date else "")
               + ". We request you to issue a tender-specific Manufacturer's Authorisation Form in the purchaser's format, "
                 "extending your full warranty through us, for the following products:"),
            {"type": "bullets", "items": items},
            _p("We would be grateful to receive the signed authorisation at least three working days before the due date."),
            _signature(company), {"type": "pagebreak"}]})
    return {"title": "OEM authorisation requests", "subtitle": f"{parsed.client_reference or ''} · {parsed.client.name or ''}",
            "quote_number": "", "sections": [{**s, "hidden": False} for s in sections]}


def submission_index(company: dict, parsed: ParsedRfp, strategy: CompetitiveAnalysis, files: dict[str, str]) -> dict[str, Any]:
    a = [[name, purpose] for name, purpose in files.items() if not name.startswith("03_")]
    b = [[name, purpose] for name, purpose in files.items() if name.startswith("03_")]
    return {"title": "Submission pack", "subtitle": f"{parsed.client_reference or ''} · {parsed.client.name or ''} · "
            f"prepared {date.today().strftime('%d %B %Y')}", "quote_number": "",
            "sections": [
                {"key": "a", "title": "Envelope A – technical bid", "hidden": False, "blocks": [
                    _p("Documents to be submitted in the technical envelope. No price may appear in these documents."),
                    _table(["File", "Contents"], a, [40, 60])]},
                {"key": "b", "title": "Envelope B – financial bid", "hidden": False, "blocks": [
                    _p(f"Total offer value {fmt(strategy.revenue, strategy.base_currency, 0)} before tax. Submit only in "
                       f"the financial envelope, in the purchaser's price format."),
                    _table(["File", "Contents"], b, [40, 60])]},
                {"key": "c", "title": "Before sealing", "hidden": False, "blocks": [{"type": "bullets", "items": [
                    "Sign and stamp every page; number the pages and fill the page numbers into the checklist.",
                    "Attach the OEM authorisation forms once received, and the certificates listed in the checklist.",
                    "Superscribe the envelopes with the RFP number and due date as instructed in the RFP.",
                ]}]},
            ]}


def build_pack(out_dir: Path, *, company: dict, parsed: ParsedRfp, costing: InternalPricing, strategy: CompetitiveAnalysis,
               compliance: ComplianceReport | None, proposal: Proposal, existing: dict[str, Path]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tech = technical_proposal(company, parsed, costing, strategy, compliance, proposal)
    files: dict[str, Path] = {}
    purposes: dict[str, str] = {}
    files["01_Technical_proposal.pdf"] = render_pdf(tech, out_dir / "01_Technical_proposal.pdf", company, label="TECHNICAL PROPOSAL",
                                                    footer="Technical proposal", draft_note=None)
    purposes["01_Technical_proposal.pdf"] = "Covering letter, bidder information, eligibility, technical compliance, conditions, declarations"
    files["01_Technical_proposal.docx"] = render_docx(tech, out_dir / "01_Technical_proposal.docx", company, label="Technical proposal")
    purposes["01_Technical_proposal.docx"] = "Editable copy of the technical proposal"
    if "compliance" in existing:
        files["02_Compliance_statement.pdf"] = existing["compliance"]
        purposes["02_Compliance_statement.pdf"] = "Clause-by-clause compliance statement"
    if "quotation" in existing:
        files["03_Financial_bid.pdf"] = existing["quotation"]
        purposes["03_Financial_bid.pdf"] = "Priced quotation with GST (financial envelope only)"
    maf = maf_letters(company, parsed, costing)
    if maf["sections"]:
        files["04_OEM_authorisation_requests.docx"] = render_docx(maf, out_dir / "04_OEM_authorisation_requests.docx", company,
                                                                  label="OEM authorisation request")
        purposes["04_OEM_authorisation_requests.docx"] = f"Letters to {len(maf['sections'])} manufacturers requesting the MAF"
    index = submission_index(company, parsed, strategy, purposes)
    files["00_Submission_index.pdf"] = render_pdf(index, out_dir / "00_Submission_index.pdf", company, label="SUBMISSION PACK",
                                                  footer="Submission pack", draft_note=None)
    zpath = out_dir / f"{proposal.quote_number}-submission-pack.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            z.write(files[name], arcname=name)
    return zpath
