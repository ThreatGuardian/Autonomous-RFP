"""PDF rendering for the client quotation and the internal pricing memo (ReportLab)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.agents.messages import CompetitiveAnalysis, Localisation, ParsedRfp, Proposal
from app.config import get_settings
from app.finance.money import fmt

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

INK = colors.HexColor("#0F172A")
BODY = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
SOFT = colors.HexColor("#F8FAFC")
BRAND = colors.HexColor("#12263A")
ACCENT = colors.HexColor("#B8862B")
GOOD = colors.HexColor("#15803D")
WARN = colors.HexColor("#B45309")
BAD = colors.HexColor("#B91C1C")

_fonts_ready = False


def _register_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    for name in ("Regular", "Medium", "SemiBold", "Bold"):
        pdfmetrics.registerFont(TTFont(f"Inter-{name}", str(FONT_DIR / f"Inter-{name}.ttf")))
    pdfmetrics.registerFontFamily("Inter", normal="Inter-Regular", bold="Inter-SemiBold",
                                  italic="Inter-Regular", boldItalic="Inter-Bold")
    _fonts_ready = True


def _styles() -> dict[str, ParagraphStyle]:
    _register_fonts()
    base = ParagraphStyle("base", fontName="Inter-Regular", fontSize=9, leading=13.2, textColor=BODY)
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7.6, leading=10.4, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10.6, textColor=INK),
        "cell_muted": ParagraphStyle("cellm", parent=base, fontSize=7.2, leading=9.6, textColor=MUTED),
        "cell_r": ParagraphStyle("cellr", parent=base, fontSize=8, leading=10.6, textColor=INK, alignment=TA_RIGHT),
        "th": ParagraphStyle("th", parent=base, fontName="Inter-SemiBold", fontSize=7.2, leading=9.5, textColor=MUTED),
        "th_r": ParagraphStyle("thr", parent=base, fontName="Inter-SemiBold", fontSize=7.2, leading=9.5, textColor=MUTED, alignment=TA_RIGHT),
        "h1": ParagraphStyle("h1", parent=base, fontName="Inter-SemiBold", fontSize=20, leading=24, textColor=INK),
        "h2": ParagraphStyle("h2", parent=base, fontName="Inter-SemiBold", fontSize=12, leading=16, textColor=INK,
                             spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base, fontName="Inter-SemiBold", fontSize=9.5, leading=13, textColor=INK,
                             spaceBefore=8, spaceAfter=3),
        "label": ParagraphStyle("label", parent=base, fontName="Inter-SemiBold", fontSize=6.8, leading=9,
                                textColor=MUTED),
        "value": ParagraphStyle("value", parent=base, fontSize=8.6, leading=11.6, textColor=INK),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=10, bulletIndent=0, spaceAfter=2),
        "total_label": ParagraphStyle("tl", parent=base, fontSize=8.6, textColor=BODY, alignment=TA_RIGHT),
        "total_value": ParagraphStyle("tv", parent=base, fontName="Inter-Medium", fontSize=8.6, textColor=INK, alignment=TA_RIGHT),
        "grand_label": ParagraphStyle("gl", parent=base, fontName="Inter-SemiBold", fontSize=10, textColor=colors.white, alignment=TA_RIGHT),
        "grand_value": ParagraphStyle("gv", parent=base, fontName="Inter-Bold", fontSize=11, textColor=colors.white, alignment=TA_RIGHT),
    }


def _short(text: str, limit: int = 78) -> str:
    """First clause of a product description, trimmed at a word boundary."""
    first = text.split(". ")[0].rstrip(".")
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0].rstrip(",;") + "…"


def esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class NumberedCanvas(rl_canvas.Canvas):
    """Canvas that knows the total page count when drawing footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved: list[dict] = []

    def showPage(self):  # noqa: N802 (ReportLab API)
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Inter-Regular", 7)
            self.setFillColor(MUTED)
            w, _ = self._pagesize
            self.drawRightString(w - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _wordmark(c: rl_canvas.Canvas, x: float, y: float, company: dict, scale: float = 1.0, light: bool = False) -> None:
    s = 9 * mm * scale
    c.setFillColor(ACCENT if light else BRAND)
    c.rect(x, y, s, s, stroke=0, fill=1)
    c.setFillColor(BRAND if light else ACCENT)
    p = c.beginPath()
    p.moveTo(x, y)
    p.lineTo(x + s, y + s)
    p.lineTo(x + s, y + s * 0.55)
    p.lineTo(x + s * 0.45, y)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.setFillColor(colors.white if light else INK)
    c.setFont("Inter-Bold", 11 * scale)
    c.drawString(x + s + 3 * mm, y + s * 0.52, company["short_name"].upper())
    c.setFont("Inter-Regular", 7 * scale)
    c.setFillColor(colors.HexColor("#CBD5E1") if light else MUTED)
    c.drawString(x + s + 3 * mm, y + s * 0.12, company["tagline"])


def _footer(c: rl_canvas.Canvas, company: dict, left: str) -> None:
    w, _ = c._pagesize
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
    c.setFont("Inter-Regular", 7)
    c.setFillColor(MUTED)
    c.drawString(18 * mm, 10 * mm, left)


def _watermark(c: rl_canvas.Canvas, text: str) -> None:
    w, h = c._pagesize
    c.saveState()
    c.setFillColor(colors.Color(0.72, 0.53, 0.17, alpha=0.08))
    c.setFont("Inter-Bold", 54)
    c.translate(w / 2, h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, text)
    c.restoreState()


def _table(data, widths, *, header=True, zebra=True, extra=None) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#CBD5E1"))]
    if zebra:
        for r in range(2 if header else 1, len(data), 2):
            style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FCFDFE")))
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def _kv_block(title: str, rows: list[tuple[str, str]], st, width: float) -> Table:
    data = [[Paragraph(esc(title).upper(), st["label"])]]
    for k, v in rows:
        if v:
            label = f"<font color='#64748B'>{esc(k)}</font>&nbsp;&nbsp;" if k else ""
            data.append([Paragraph(f"{label}{esc(v)}", st["value"])])
    t = Table(data, colWidths=[width])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 5),
    ]))
    return t


# =============================================================================== quotation


def render_quotation(path: Path, *, company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis,
                     loc: Localisation, proposal: Proposal, approved: bool) -> Path:
    st = _styles()
    page_w, page_h = A4
    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm,
                          bottomMargin=20 * mm, title=f"Quotation {proposal.quote_number}", author=company["name"],
                          subject=parsed.title)
    content_w = page_w - 36 * mm
    money = lambda v: fmt(v, loc.currency, loc.decimals)  # noqa: E731
    footer_left = f"{company['name']}  ·  {company['tax_id_label']} {company['tax_id']}  ·  {company['website']}"

    def first_page(c, _doc):
        c.saveState()
        c.setFillColor(BRAND)
        c.rect(0, page_h - 46 * mm, page_w, 46 * mm, stroke=0, fill=1)
        c.setFillColor(ACCENT)
        c.rect(0, page_h - 47.2 * mm, page_w, 1.2 * mm, stroke=0, fill=1)
        _wordmark(c, 18 * mm, page_h - 25 * mm, company, 1.1, light=True)
        c.setFillColor(colors.white)
        c.setFont("Inter-SemiBold", 22)
        c.drawRightString(page_w - 18 * mm, page_h - 21 * mm, "Quotation")
        c.setFont("Inter-Regular", 8.5)
        c.setFillColor(colors.HexColor("#CBD5E1"))
        c.drawRightString(page_w - 18 * mm, page_h - 27.5 * mm, f"{proposal.quote_number}  ·  Version {proposal.version}")
        c.setFont("Inter-Regular", 7.5)
        y = page_h - 36 * mm
        c.drawString(18 * mm, y, "  ·  ".join([*company["address_lines"][:2]]))
        c.drawString(18 * mm, y - 4 * mm, f"{company['email']}  ·  {company['phone']}")
        if not approved:
            _watermark(c, "DRAFT")
        _footer(c, company, footer_left)
        c.restoreState()

    def later_pages(c, _doc):
        c.saveState()
        _wordmark(c, 18 * mm, page_h - 14 * mm, company, 0.62)
        c.setFont("Inter-Regular", 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(page_w - 18 * mm, page_h - 11 * mm, f"Quotation {proposal.quote_number} · {parsed.client.name or ''}")
        c.setStrokeColor(LINE)
        c.line(18 * mm, page_h - 16.5 * mm, page_w - 18 * mm, page_h - 16.5 * mm)
        if not approved:
            _watermark(c, "DRAFT")
        _footer(c, company, footer_left)
        c.restoreState()

    doc.addPageTemplates([
        PageTemplate("first", [Frame(18 * mm, 20 * mm, content_w, page_h - 72 * mm, id="f1", showBoundary=0)], onPage=first_page),
        PageTemplate("later", [Frame(18 * mm, 20 * mm, content_w, page_h - 42 * mm, id="f2", showBoundary=0)], onPage=later_pages),
    ])
    from reportlab.platypus.doctemplate import NextPageTemplate

    story: list = [NextPageTemplate("later")]
    c = parsed.client
    half = (content_w - 10 * mm) / 2
    prepared = _kv_block("Prepared for", [
        ("", c.name or "—"), ("Attn.", c.contact_name or ""), ("", c.email or ""),
        ("", ", ".join(x for x in [c.region, c.country_name] if x)), ("Tax ID", c.tax_id or ""),
    ], st, half)
    details = _kv_block("Quotation details", [
        ("Issued", date.fromisoformat(proposal.issue_date).strftime("%d %b %Y")),
        ("Valid until", date.fromisoformat(proposal.valid_until).strftime("%d %b %Y")),
        ("Your reference", parsed.client_reference or "—"),
        ("Currency", loc.currency), ("Delivery terms", parsed.terms.incoterm or "Delivered to site"),
    ], st, half)
    meta = Table([[prepared, details]], colWidths=[half + 10 * mm, half])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, 6 * mm)]

    # Summary strip
    strip = Table([[
        Paragraph("TOTAL (INCL. TAX)", st["label"]), Paragraph("LINE ITEMS", st["label"]),
        Paragraph("INCLUDED VALUE", st["label"]), Paragraph("DELIVERY", st["label"]),
    ], [
        Paragraph(f"<font name='Inter-SemiBold' size='12' color='#0F172A'>{esc(money(loc.grand_total))}</font>", st["body"]),
        Paragraph(f"<font name='Inter-SemiBold' size='12' color='#0F172A'>{len(loc.lines)}</font>", st["body"]),
        Paragraph(f"<font name='Inter-SemiBold' size='12' color='#0F172A'>{esc(money(loc.bundled_value))}</font>", st["body"]),
        Paragraph(f"<font name='Inter-SemiBold' size='12' color='#0F172A'>Day {proposal.milestones[2].day if len(proposal.milestones) > 2 else '—'}</font>", st["body"]),
    ]], colWidths=[content_w * 0.34, content_w * 0.18, content_w * 0.26, content_w * 0.22])
    strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story += [strip, Spacer(1, 7 * mm)]

    # Cover letter
    story.append(Paragraph(esc(proposal.salutation), st["body"]))
    story.append(Spacer(1, 3))
    for p in proposal.cover_letter:
        story += [Paragraph(esc(p), st["body"]), Spacer(1, 4)]
    story += [Spacer(1, 4), Paragraph("Yours sincerely,", st["body"]), Spacer(1, 8),
              Paragraph(f"<font name='Inter-SemiBold' color='#0F172A'>{esc(proposal.signatory['name'])}</font><br/>"
                        f"{esc(proposal.signatory['title'])}, {esc(company['name'])}<br/>{esc(proposal.signatory['email'])}", st["body"]),
              PageBreak()]

    # Executive summary
    story.append(Paragraph("Executive summary", st["h2"]))
    for p in proposal.executive_summary:
        story.append(Paragraph(esc(p), st["bullet"], bulletText="•"))
    if proposal.highlights:
        story.append(Paragraph("Highlights", st["h3"]))
        for h in proposal.highlights:
            story.append(Paragraph(esc(h), st["bullet"], bulletText="–"))

    # Commercial schedule
    story.append(Paragraph("Commercial schedule", st["h2"]))
    head = ["#", "Item", "Qty", "Unit price", "Net", "Tax", "Total"]
    rows = [[Paragraph(h, st["th_r"] if i >= 2 else st["th"]) for i, h in enumerate(head)]]
    for l in loc.lines:
        desc = f"<font name='Inter-Medium'>{esc(l.name)}</font><br/><font color='#64748B' size='7'>{esc(l.sku)} · {esc(_short(l.description))}</font>"
        if l.bundle_name:
            desc += f"<br/><font color='#B8862B' size='7'>Includes {esc(l.bundle_name)} at no charge</font>"
        tax = f"{l.tax_rate_pct:g}%" if l.tax_rate_pct else ("0%" if l.taxes else "—")
        rows.append([
            Paragraph(str(l.line_no), st["cell"]), Paragraph(desc, st["cell"]),
            Paragraph(f"{l.quantity:,}", st["cell_r"]), Paragraph(esc(money(l.unit_price)), st["cell_r"]),
            Paragraph(esc(money(l.net)), st["cell_r"]), Paragraph(tax, st["cell_r"]), Paragraph(esc(money(l.gross)), st["cell_r"]),
        ])
    widths = [7 * mm, content_w - 7 * mm - 12 * mm - 25 * mm - 27 * mm - 11 * mm - 27 * mm, 12 * mm, 25 * mm, 27 * mm, 11 * mm, 27 * mm]
    story.append(_table(rows, widths))

    totals = [[Paragraph("Subtotal (net)", st["total_label"]), Paragraph(esc(money(loc.subtotal)), st["total_value"])]]
    for t in loc.tax_breakdown:
        totals.append([Paragraph(f"{esc(t.name)} @ {t.rate_pct:g}%", st["total_label"]), Paragraph(esc(money(t.amount)), st["total_value"])])
    totals.append([Paragraph(f"Total due ({loc.currency})", st["grand_label"]), Paragraph(esc(money(loc.grand_total)), st["grand_value"])])
    tt = Table(totals, colWidths=[52 * mm, 36 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, LINE),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND), ("TOPPADDING", (0, -1), (-1, -1), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]))
    story += [Spacer(1, 3 * mm), tt]
    notes = [loc.tax_summary + "."] + loc.tax_notes + sorted({l.tax_note for l in loc.lines if l.tax_note})
    story += [Spacer(1, 3 * mm)] + [Paragraph(esc(n), st["small"]) for n in notes]

    if proposal.inclusions:
        story.append(CondPageBreak(50 * mm))
        story.append(Paragraph("Included at no additional charge", st["h2"]))
        rows = [[Paragraph(h, st["th"]) for h in ("Service", "Applies to", "Scope")] + [Paragraph("Value", st["th_r"])]]
        for inc in proposal.inclusions:
            rows.append([Paragraph(f"<font name='Inter-Medium'>{esc(inc['service'])}</font>", st["cell"]),
                         Paragraph(f"{esc(inc['item'])} × {inc['quantity']:,}", st["cell"]),
                         Paragraph(esc(inc["description"]), st["cell_muted"]),
                         Paragraph(esc(money(inc["value"])), st["cell_r"])])
        story.append(_table(rows, [40 * mm, 45 * mm, content_w - 115 * mm, 30 * mm]))

    # Pricing basis (client-appropriate rationale)
    story.append(CondPageBreak(40 * mm))
    story.append(Paragraph("Pricing basis", st["h2"]))
    story.append(Paragraph(
        "Prices reflect current distributor costs, volume pricing for the quantities requested and the service levels "
        "described in this proposal. Where a value-added service is included, it is provided at no charge rather than "
        "reducing product quality or support.", st["body"]))
    for pl, ll in zip(strat.lines, loc.lines):
        disc = f"{pl.discount_pct:.1f}% below list price" if pl.discount_pct > 0.05 else "list price"
        extra = f"; includes {pl.bundle.name.lower()}" if pl.bundle else ""
        wty = f"; {pl.warranty_months}-month warranty" if pl.category not in ("software", "service") else ""
        story.append(Paragraph(f"<font name='Inter-Medium' color='#0F172A'>{esc(pl.name)}</font> — {disc}{esc(extra)}{wty}.",
                               st["bullet"], bulletText="•"))

    # Compliance matrix
    if proposal.compliance:
        story.append(CondPageBreak(60 * mm))
        story.append(Paragraph("Requirement compliance", st["h2"]))
        colour = {"Complies": GOOD, "Complies with note": WARN, "Clarification required": BAD, "Deviation": BAD, "Noted": MUTED}
        shown = [r for r in proposal.compliance if r.status != "Noted"]
        limit = 18
        if len(shown) > limit:
            # Long tenders: the quotation carries the exceptions; the full statement is a separate document.
            order = {"Deviation": 0, "Clarification required": 1, "Complies with note": 2, "Complies": 3}
            shown = sorted(shown, key=lambda r: order.get(r.status, 4))[:limit]
            story.append(Paragraph(
                f"The {len(proposal.compliance)} clauses of the tender are answered in the enclosed compliance statement. "
                "Deviations, clarifications and qualified responses are summarised below.", st["body"]))
            story.append(Spacer(1, 2 * mm))
        rows = [[Paragraph(h, st["th"]) for h in ("Ref", "Requirement", "Status", "Response")]]
        for r in shown:
            resp = esc(r.response)
            for e in r.evidence[:1]:
                resp += f"<br/><font color='#64748B' size='6.8'>“{esc(e.text)}” — {esc(e.section)}</font>"
            rows.append([
                Paragraph(esc(r.ref), st["cell_muted"]), Paragraph(esc(r.requirement), st["cell"]),
                Paragraph(f"<font name='Inter-SemiBold' color='{colour[r.status].hexval()}'>{esc(r.status)}</font>", st["cell"]),
                Paragraph(resp, st["cell"]),
            ])
        story.append(_table(rows, [15 * mm, (content_w - 45 * mm) * 0.45, 30 * mm, (content_w - 45 * mm) * 0.55]))

    # Delivery plan
    story.append(CondPageBreak(55 * mm))
    story.append(Paragraph("Delivery and implementation", st["h2"]))
    rows = [[Paragraph(h, st["th"]) for h in ("Milestone", "Day", "Detail")]]
    for m_ in proposal.milestones:
        rows.append([Paragraph(f"<font name='Inter-Medium'>{esc(m_.label)}</font>", st["cell"]),
                     Paragraph(f"Day {m_.day}", st["cell"]), Paragraph(esc(m_.detail), st["cell"])])
    story.append(_table(rows, [42 * mm, 18 * mm, content_w - 60 * mm]))
    story.append(Spacer(1, 3 * mm))
    for p in proposal.delivery_plan:
        story += [Paragraph(esc(p), st["body"]), Spacer(1, 3)]

    # Terms and acceptance
    story.append(CondPageBreak(60 * mm))
    story.append(Paragraph("Terms", st["h2"]))
    for t in proposal.terms:
        story.append(Paragraph(esc(t), st["bullet"], bulletText="•"))
    story.append(Spacer(1, 8 * mm))
    sign = Table([
        [Paragraph("ACCEPTED ON BEHALF OF THE CLIENT", st["label"]), Paragraph(f"FOR {esc(company['name']).upper()}", st["label"])],
        [Spacer(1, 16 * mm), Spacer(1, 16 * mm)],
        [Paragraph("Name, title, signature and date", st["small"]),
         Paragraph(f"{esc(proposal.signatory['name'])}, {esc(proposal.signatory['title'])}", st["small"])],
    ], colWidths=[half, half], hAlign="LEFT")
    sign.setStyle(TableStyle([("LINEBELOW", (0, 1), (0, 1), 0.6, MUTED), ("LINEBELOW", (1, 1), (1, 1), 0.6, MUTED),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 10 * mm)]))
    story.append(KeepTogether([sign]))
    bank = company["bank"]
    story += [Spacer(1, 6 * mm), Paragraph(
        f"Bank details: {esc(bank['name'])} · A/C {esc(bank['account'])} · IFSC {esc(bank['ifsc'])} · SWIFT {esc(bank['swift'])}",
        st["small"])]

    doc.build(story, canvasmaker=NumberedCanvas)
    return path


# =============================================================================== internal memo


def render_memo(path: Path, *, company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation,
                proposal: Proposal, approval: dict | None) -> Path:
    st = _styles()
    size = landscape(A4)
    page_w, page_h = size
    doc = BaseDocTemplate(str(path), pagesize=size, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm,
                          bottomMargin=20 * mm, title=f"Pricing memo {proposal.quote_number}", author=company["name"])
    content_w = page_w - 36 * mm
    base = strat.base_currency
    m = lambda v: fmt(v, base, 0)  # noqa: E731

    def page(c, _doc):
        c.saveState()
        _wordmark(c, 18 * mm, page_h - 15 * mm, company, 0.62)
        c.setFont("Inter-SemiBold", 7.5)
        c.setFillColor(BAD)
        c.drawRightString(page_w - 18 * mm, page_h - 11 * mm, "CONFIDENTIAL — INTERNAL USE ONLY")
        c.setStrokeColor(LINE)
        c.line(18 * mm, page_h - 17 * mm, page_w - 18 * mm, page_h - 17 * mm)
        _footer(c, company, f"Pricing memo {proposal.quote_number} v{proposal.version} · generated {date.today():%d %b %Y}")
        c.restoreState()

    doc.addPageTemplates([PageTemplate("memo", [Frame(18 * mm, 20 * mm, content_w, page_h - 42 * mm)], onPage=page)])
    story: list = [Paragraph(f"Pricing memo — {esc(parsed.client.name or 'Client')}", st["h1"]), Spacer(1, 2),
                   Paragraph(esc(parsed.title), st["small"]), Spacer(1, 5 * mm)]

    kpis = [("Revenue (net)", m(strat.revenue)), ("Landed cost", m(strat.cost)), ("Bundle cost", m(strat.bundle_cost)),
            ("Gross margin", f"{m(strat.margin)} · {strat.margin_pct:.1f}%"), ("Expected profit", m(strat.expected_profit)),
            ("Win probability", f"{100 * strat.win_probability:.0f}%")]
    kt = Table([[Paragraph(k.upper(), st["label"]) for k, _ in kpis],
                [Paragraph(f"<font name='Inter-SemiBold' size='11' color='#0F172A'>{esc(v)}</font>", st["body"]) for _, v in kpis]],
               colWidths=[content_w / len(kpis)] * len(kpis))
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                            ("LINEBEFORE", (1, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 1), (-1, 1), 7)]))
    story += [kt, Spacer(1, 3 * mm), Paragraph(esc(strat.summary), st["body"])]
    if approval:
        story.append(Paragraph(f"Approval: <font name='Inter-SemiBold'>{esc(approval.get('status', ''))}</font> "
                               f"by {esc(approval.get('actor', ''))} on {esc(approval.get('at', ''))}"
                               + (f" — “{esc(approval['note'])}”" if approval.get("note") else ""), st["body"]))

    story.append(Paragraph("Line economics", st["h2"]))
    head = ["#", "Product", "Qty", "Unit cost", "Floor", "Best competitor", "Price", "Margin", "P(win)", "Strategy"]
    rows = [[Paragraph(h, st["th_r"] if i in (2, 3, 4, 6, 7, 8) else st["th"]) for i, h in enumerate(head)]]
    for l in strat.lines:
        best = l.market.best
        comp = f"{esc(best.competitor)}<br/><font color='#64748B' size='6.8'>{esc(m(best.unit_price_base))}</font>" if best else "—"
        flag = "" if not l.flags else f"<br/><font color='#B91C1C' size='6.8'>{esc(', '.join(l.flags))}</font>"
        rows.append([
            Paragraph(str(l.line_no), st["cell"]), Paragraph(f"{esc(l.name)}<br/><font color='#64748B' size='6.8'>{esc(l.sku)}</font>", st["cell"]),
            Paragraph(f"{l.quantity:,}", st["cell_r"]), Paragraph(esc(m(l.unit_cost)), st["cell_r"]),
            Paragraph(esc(m(l.floor_price)), st["cell_r"]), Paragraph(comp, st["cell"]),
            Paragraph(esc(m(l.unit_price)), st["cell_r"]), Paragraph(f"{l.margin_pct:.1f}%", st["cell_r"]),
            Paragraph(f"{100 * l.win_probability:.0f}%", st["cell_r"]),
            Paragraph(f"{esc(l.strategy)}{(' + ' + esc(l.bundle.code)) if l.bundle else ''}{flag}", st["cell"]),
        ])
    story.append(_table(rows, [8 * mm, 54 * mm, 13 * mm, 24 * mm, 24 * mm, 42 * mm, 24 * mm, 17 * mm, 15 * mm, content_w - 221 * mm]))

    story.append(Paragraph("Rationale by line", st["h2"]))
    for l in strat.lines:
        block = [Paragraph(f"{l.line_no}. {esc(l.name)} — <font color='#B8862B'>{esc(l.headline)}</font>", st["h3"])]
        block += [Paragraph(esc(r), st["bullet"], bulletText="•") for r in l.rationale]
        if l.scenarios:
            srows = [[Paragraph(h, st["th"] if i == 0 else st["th_r"]) for i, h in
                      enumerate(("Scenario", "Unit price", "Bundle", "Margin", "P(win)", "Expected profit"))]]
            for s in l.scenarios:
                srows.append([Paragraph(esc(s.label) + ("" if s.feasible else " <font color='#B91C1C'>(not permitted)</font>"), st["cell"]),
                              Paragraph(esc(m(s.unit_price)), st["cell_r"]), Paragraph(esc(s.bundle or "—"), st["cell_r"]),
                              Paragraph(f"{s.margin_pct:.1f}%", st["cell_r"]), Paragraph(f"{100 * s.win_probability:.0f}%", st["cell_r"]),
                              Paragraph(esc(m(s.expected_profit)), st["cell_r"])])
            block += [Spacer(1, 2), _table(srows, [80 * mm, 30 * mm, 30 * mm, 24 * mm, 22 * mm, 34 * mm], zebra=False)]
        story.append(KeepTogether(block[:3]))
        story += block[3:]

    story.append(Paragraph("Currency and tax", st["h2"]))
    story.append(Paragraph(
        f"Quoted in {loc.currency}. Rate {base}/{loc.currency} {loc.fx_rate:.6f} from {esc(loc.fx_source)} (as of {esc(loc.fx_as_of)})"
        f"{' — fallback source, confirm before sending' if loc.fx_stale else ''}; buffer {loc.fx_buffer_pct:g}%; "
        f"effective {loc.fx_effective_rate:.6f}. Tax: {esc(loc.tax_summary)} for {esc(loc.jurisdiction)}.", st["body"]))
    doc.build(story, canvasmaker=NumberedCanvas)
    return path


def document_dir(reference: str) -> Path:
    d = get_settings().document_dir / reference
    d.mkdir(parents=True, exist_ok=True)
    return d
