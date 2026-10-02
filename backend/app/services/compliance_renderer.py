"""Clause-by-clause compliance statement (client-facing tender annexure).

Tenders ask bidders to state, for every clause and specification parameter,
whether the offer complies and to list deviations separately. This document is
generated from the Tender Compliance Agent's report in the same visual
language as the quotation: eligibility compliance with the documents enclosed,
the compliance matrix grouped by the tender's own sections, a statement of
deviations ("Nil" when there are none) and the declaration.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

from app.agents.messages import ComplianceItem, ComplianceReport, ParsedRfp, Proposal
from app.services.pdf_renderer import (
    ACCENT, BAD, GOOD, INK, LINE, MUTED, SOFT, WARN, NumberedCanvas, _footer, _kv_block, _styles, _table, _watermark,
    _wordmark, esc,
)

STATUS_LABEL = {"Complies": "Complies", "Complies with note": "Complies (note)", "Clarification required": "Clarification",
                "Deviation": "Deviation", "Noted": "Noted"}
STATUS_COLOUR = {"Complies": GOOD, "Complies with note": WARN, "Clarification required": BAD, "Deviation": BAD, "Noted": MUTED}
ELIG_COLOUR = {"Meets": GOOD, "Documents required": WARN, "Needs review": WARN, "Does not meet": BAD}
ELIG_LABEL = {"Meets": "Complies", "Documents required": "Complies", "Needs review": "Complies (note)", "Does not meet": "Does not comply"}


def _summary_tiles(values: list[tuple[str, str, colors.Color]], width: float, st) -> Table:
    cells = []
    for value, label, colour in values:
        big = ParagraphStyle("tile", parent=st["body"], fontName="Inter-SemiBold", fontSize=15, leading=19, textColor=colour)
        cells.append([Paragraph(esc(value), big), Spacer(1, 1.5 * mm), Paragraph(esc(label), st["small"])])
    t = Table([[c for c in cells]], colWidths=[width / len(values)] * len(values))
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def render_compliance(path: Path, *, company: dict, parsed: ParsedRfp, report: ComplianceReport, proposal: Proposal,
                      approved: bool) -> Path:
    st = _styles()
    page_w, page_h = A4
    content_w = page_w - 36 * mm
    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=24 * mm,
                          bottomMargin=20 * mm, title=f"Compliance statement {proposal.quote_number}", author=company["name"],
                          subject=parsed.title)
    footer_left = f"{company['name']}  ·  Compliance statement to {parsed.client_reference or parsed.title[:40]}"

    def page(c, _doc):
        c.saveState()
        _wordmark(c, 18 * mm, page_h - 15 * mm, company, 0.66)
        c.setFont("Inter-SemiBold", 8)
        c.setFillColor(INK)
        c.drawRightString(page_w - 18 * mm, page_h - 10.5 * mm, "Compliance statement")
        c.setFont("Inter-Regular", 7.2)
        c.setFillColor(MUTED)
        c.drawRightString(page_w - 18 * mm, page_h - 14.5 * mm, f"{proposal.quote_number} · version {proposal.version}")
        c.setStrokeColor(LINE)
        c.line(18 * mm, page_h - 18 * mm, page_w - 18 * mm, page_h - 18 * mm)
        if not approved:
            _watermark(c, "DRAFT")
        _footer(c, company, footer_left)
        c.restoreState()

    doc.addPageTemplates([PageTemplate("p", [Frame(18 * mm, 20 * mm, content_w, page_h - 44 * mm, id="f")], onPage=page)])
    s: list = []
    c = parsed.client
    tender = parsed.document
    s.append(Paragraph("Statement of compliance", st["h1"]))
    s.append(Spacer(1, 2 * mm))
    s.append(Paragraph(esc(parsed.title), st["body"]))
    s.append(Spacer(1, 5 * mm))
    half = (content_w - 10 * mm) / 2
    left = _kv_block("Submitted to", [("", c.name or "—"), ("", ", ".join(x for x in [c.city, c.region] if x)),
                                      ("Tender", parsed.client_reference or "—")], st, half)
    right = _kv_block("Submitted by", [("", company["name"]), (company["tax_id_label"], company["tax_id"]),
                                       ("Date", date.fromisoformat(proposal.issue_date).strftime("%d %b %Y"))], st, half)
    meta = Table([[left, right]], colWidths=[half + 10 * mm, half])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    s += [meta, Spacer(1, 5 * mm)]

    counted = [i for i in report.items if i.status != "Noted"]
    deviations = [i for i in report.items if i.status == "Deviation"]
    clar = [i for i in report.items if i.status == "Clarification required"]
    s.append(_summary_tiles([
        (f"{report.mandatory_met}/{report.mandatory_total}", "mandatory clauses complied", INK),
        (str(sum(i.status == "Complies" for i in counted)), "fully compliant clauses", GOOD),
        (str(len(deviations)), "deviations declared", BAD if deviations else GOOD),
        (str(len(clar)), "clarifications sought", WARN if clar else GOOD),
    ], content_w, st))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph(
        f"We have examined the tender document{' (' + str(tender.pages) + ' pages)' if tender else ''} and confirm that our offer "
        "complies with its requirements except as stated in the statement of deviations below. Responses marked "
        "“note” comply with a qualification described in the response.", st["body"]))

    # ---- eligibility
    if report.eligibility:
        s.append(CondPageBreak(40 * mm))
        s.append(Paragraph("Eligibility and pre-qualification", st["h2"]))
        rows = [[Paragraph(h, st["th"]) for h in ("Ref", "Criterion", "Compliance", "Our position and documents")]]
        for e in report.eligibility:
            docs = f"<br/><font color='#64748B' size='6.8'>Documents: {esc(e.documents)}</font>" if e.documents else ""
            rows.append([
                Paragraph(esc(e.clause or e.id), st["cell_muted"]), Paragraph(esc(e.text), st["cell"]),
                Paragraph(f"<font name='Inter-SemiBold' color='{ELIG_COLOUR[e.status].hexval()}'>{ELIG_LABEL[e.status]}</font>", st["cell"]),
                Paragraph(esc(e.position) + docs, st["cell"]),
            ])
        s.append(_table(rows, [15 * mm, (content_w - 43 * mm) * 0.5, 28 * mm, (content_w - 43 * mm) * 0.5]))

    # ---- clause-by-clause, grouped by the tender's own sections
    s.append(CondPageBreak(40 * mm))
    s.append(Paragraph("Clause-by-clause compliance", st["h2"]))
    groups: dict[str, list[ComplianceItem]] = {}
    for i in report.items:
        if i.category == "eligibility":
            continue
        groups.setdefault(i.section_title or "General requirements", []).append(i)
    for title, items in groups.items():
        rows = [[Paragraph(h, st["th"]) for h in ("Clause", "Requirement", "Compliance", "Response")]]
        for i in items:
            page = f"<br/><font color='#94A3B8' size='6.4'>p. {i.page}</font>" if i.page and tender and not tender.pages_estimated else ""
            response = esc(i.response)
            if i.evidence and i.response.startswith("Confirmed"):
                response = f"{esc(i.evidence[0].text)}<br/><font color='#64748B' size='6.6'>{esc(i.evidence[0].section)}</font>"
            rows.append([
                Paragraph(esc(i.clause or i.id) + page, st["cell_muted"]), Paragraph(esc(i.text), st["cell"]),
                Paragraph(f"<font name='Inter-SemiBold' color='{STATUS_COLOUR[i.status].hexval()}'>{STATUS_LABEL[i.status]}</font>", st["cell"]),
                Paragraph(response, st["cell"]),
            ])
        heading = Paragraph(esc(title), st["h3"])
        table = _table(rows, [16 * mm, (content_w - 44 * mm) * 0.5, 28 * mm, (content_w - 44 * mm) * 0.5])
        s += [KeepTogether([heading, table])] if len(items) <= 6 else [heading, table]
        s.append(Spacer(1, 2 * mm))

    # ---- deviations
    s.append(CondPageBreak(40 * mm))
    s.append(Paragraph("Statement of deviations", st["h2"]))
    if deviations:
        rows = [[Paragraph(h, st["th"]) for h in ("Clause", "Tender requirement", "Deviation and proposal")]]
        for i in deviations:
            rows.append([Paragraph(esc(i.clause or i.id), st["cell_muted"]), Paragraph(esc(i.text), st["cell"]),
                         Paragraph(esc(i.response), st["cell"])])
        s.append(_table(rows, [16 * mm, (content_w - 16 * mm) * 0.48, (content_w - 16 * mm) * 0.52]))
    else:
        s.append(Paragraph("Nil. The offer complies with all clauses of the tender.", st["body"]))
    if clar:
        s.append(Paragraph("Clarifications requested", st["h3"]))
        for i in clar:
            s.append(Paragraph(f"<font name='Inter-Medium' color='#0F172A'>{esc(i.clause or i.id)}</font> — {esc(i.response)}",
                               st["bullet"], bulletText="•"))

    # ---- declaration
    s.append(CondPageBreak(45 * mm))
    s.append(Paragraph("Declaration", st["h2"]))
    s.append(Paragraph(
        "We declare that the information given in this statement is true and correct, that the offered equipment is new "
        "and of current manufacture, and that we accept all terms and conditions of the tender other than the deviations "
        "stated above.", st["body"]))
    s.append(Spacer(1, 10 * mm))
    sig = Table([[Paragraph(f"<font name='Inter-SemiBold' color='#0F172A'>{esc(proposal.signatory.get('name', ''))}</font><br/>"
                            f"{esc(proposal.signatory.get('title', ''))}, {esc(company['name'])}", st["body"])]],
                colWidths=[80 * mm])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.8, ACCENT), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 5)]))
    s.append(sig)
    s.append(Spacer(1, 3 * mm))
    s.append(Paragraph("Authorised signatory (signature and company seal)", st["small"]))

    doc.build(s, canvasmaker=NumberedCanvas)
    return path
