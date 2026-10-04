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
    BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
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


def _catalogue_details(skus: list[str]) -> dict[str, dict[str, Any]]:
    """Make, model and tax code of the quoted products, for the item description."""
    from sqlalchemy import select

    from app.db.models import Product
    from app.db.session import session_scope

    with session_scope() as s:
        return {p.sku: {"brand": p.brand, "mpn": p.mpn, "hsn": p.hsn}
                for p in s.scalars(select(Product).where(Product.sku.in_(skus)))}


def _quotation_terms(company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation,
                     proposal: Proposal) -> list[tuple[str, str]]:
    """Numbered terms and conditions of the quotation, as (heading, text)."""
    valid = date.fromisoformat(proposal.valid_until).strftime("%d %B %Y")
    delivered = next((m for m in proposal.milestones if m.label == "Delivered to site"), None)
    installed = next((m for m in proposal.milestones if m.label.startswith("Installation")), None)
    place = ", ".join(x for x in (parsed.client.city, parsed.client.region, parsed.client.country_name) if x) or "the delivery address"
    terms = parsed.terms
    hardware = [l for l in strat.lines if l.category not in ("software", "service")]
    warranty = sorted({l.warranty_months for l in hardware})
    out = [
        ("Prices", f"All prices are in {loc.currency} per unit as itemised above"
                   + (f", {terms.incoterm} {place}" if terms.incoterm else f", delivered to {place}") + "."),
        ("Taxes", loc.tax_summary + "." + (" " + " ".join(loc.tax_notes) if loc.tax_notes else "")),
        ("Delivery", (f"Within {delivered.day} days of receipt of a purchase order" if delivered else "As agreed in the purchase order")
                     + (f"; installation and hand-over completed by day {installed.day}." if installed else ".")),
        ("Payment", f"{terms.payment_days or 30} days from the date of invoice"
                    + (f", with {terms.advance_pct:g}% advance against the purchase order" if terms.advance_pct else "") + "."),
    ]
    if warranty:
        span = f"{warranty[0]} months" if len(warranty) == 1 else f"{warranty[0]} to {warranty[-1]} months as stated per item"
        out.append(("Warranty", f"Manufacturer's warranty of {span}, registered in the purchaser's name. "
                                "Units found dead on arrival and reported within seven days are replaced at no cost."))
    out.append(("Validity", f"This quotation is valid until {valid}."))
    if loc.currency != loc.base_currency:
        out.append(("Exchange rate", f"Prices are fixed in {loc.currency}; currency movements during the validity period are borne by us."))
    if parsed.document is not None and parsed.document.long_form:
        out.append(("Tender conditions", "This offer is made against the tender referenced above and accepts its conditions "
                                         "except as stated in our compliance statement."))
    out.append(("Acceptance", "Please issue the purchase order in the name of "
                              f"{company['name']}, quoting the quotation number above."))
    return out


def render_quotation(path: Path, *, company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis,
                     loc: Localisation, proposal: Proposal, approved: bool) -> Path:
    """A commercial quotation ready to send: letterhead, items, totals, terms, bank details and signature.

    Internal figures (cost, margin, win probability, competitor prices) never appear here.
    """
    from app.finance.money import amount_in_words

    st = _styles()
    page_w, page_h = A4
    margin = 16 * mm
    content_w = page_w - 2 * margin
    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=40 * mm,
                          bottomMargin=22 * mm, title=f"Quotation {proposal.quote_number}", author=company["name"],
                          subject=parsed.title)
    money = lambda v: fmt(v, loc.currency, loc.decimals, symbol=False)  # noqa: E731
    issued = date.fromisoformat(proposal.issue_date).strftime("%d %b %Y")
    valid = date.fromisoformat(proposal.valid_until).strftime("%d %b %Y")
    tax_id = f"{company['tax_id_label']} {company['tax_id']}" if company.get("tax_id") else ""

    def letterhead(c, _doc):
        c.saveState()
        top = page_h - 14 * mm
        _wordmark(c, margin, top - 9 * mm, company, 1.0)
        c.setFont("Inter-Regular", 7.4)
        c.setFillColor(MUTED)
        address = company["address_lines"]
        lines = [", ".join(address[:2]), ", ".join(address[2:]),
                 "  ·  ".join(x for x in (company.get("phone"), company.get("email"), company.get("website")) if x)]
        y = top - 13 * mm
        for line in (x for x in lines if x):
            c.drawString(margin, y, line)
            y -= 3.4 * mm
        c.setFillColor(INK)
        c.setFont("Inter-SemiBold", 20)
        c.drawRightString(page_w - margin, top - 5 * mm, "QUOTATION")
        c.setFont("Inter-Regular", 8)
        c.setFillColor(BODY)
        c.drawRightString(page_w - margin, top - 10.5 * mm, f"No. {proposal.quote_number}")
        c.drawRightString(page_w - margin, top - 14.5 * mm, f"Date {issued}")
        if tax_id:
            c.drawRightString(page_w - margin, top - 18.5 * mm, tax_id)
        c.setStrokeColor(BRAND)
        c.setLineWidth(1.4)
        c.line(margin, page_h - 35 * mm, page_w - margin, page_h - 35 * mm)
        if not approved:
            _watermark(c, "DRAFT")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(margin, 15 * mm, page_w - margin, 15 * mm)
        c.setFont("Inter-Regular", 6.8)
        c.setFillColor(MUTED)
        c.drawString(margin, 11 * mm, f"{company['name']}  ·  {tax_id}" if tax_id else company["name"])
        if not approved:
            c.setFillColor(WARN)
            c.drawCentredString(page_w / 2, 17 * mm, "Draft for internal review — not valid until approved")
        c.restoreState()

    doc.addPageTemplates([PageTemplate("page", [Frame(margin, 22 * mm, content_w, page_h - 62 * mm, id="body",
                                                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=letterhead)])
    story: list = []

    # ---- parties and reference
    cl = parsed.client
    half = (content_w - 8 * mm) / 2
    location = ", ".join(x for x in (cl.city, cl.region, cl.country_name) if x)
    bill_to = _kv_block("Quotation to", [
        ("", cl.name or "—"), ("Attn.", cl.contact_name or ""), ("", location), ("", cl.email or ""),
        ("Tax ID", cl.tax_id or ""),
    ], st, half)
    reference = _kv_block("Reference", [
        ("Your reference", parsed.client_reference or "—"),
        ("Quotation no.", proposal.quote_number), ("Date", issued), ("Valid until", valid),
        ("Currency", loc.currency), ("Version", str(proposal.version)),
    ], st, half)
    parties = Table([[bill_to, reference]], colWidths=[half + 8 * mm, half])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [parties, Spacer(1, 5 * mm)]

    story.append(Paragraph(f"<font name='Inter-SemiBold' color='#0F172A'>Subject:</font> Quotation for {esc(parsed.title)}",
                           st["body"]))
    story.append(Spacer(1, 2.5 * mm))
    story.append(Paragraph(esc(proposal.salutation), st["body"]))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        "Thank you for your enquiry. We are pleased to quote for the goods and services below on the terms and "
        "conditions set out in this quotation.", st["body"]))
    story.append(Spacer(1, 4 * mm))

    # ---- items
    info = _catalogue_details([l.sku for l in loc.lines])
    warranty = {l.line_no: l.warranty_months for l in strat.lines}
    category = {l.line_no: l.category for l in strat.lines}
    show_code = any(info.get(l.sku, {}).get("hsn") for l in loc.lines)
    head = ["S.No", "Description"] + (["Tax code"] if show_code else []) + ["Qty", "Unit", "Unit price", "Tax", "Amount"]
    right_from = 2 + (1 if show_code else 0)
    rows = [[Paragraph(h, st["th_r"] if i >= right_from else st["th"]) for i, h in enumerate(head)]]
    for l in loc.lines:
        d = info.get(l.sku, {})
        desc = f"<font name='Inter-Medium' color='#0F172A'>{esc(l.name)}</font>"
        make = " · ".join(x for x in (f"Make: {d['brand']}" if d.get("brand") else "", f"Model: {d['mpn']}" if d.get("mpn") else "") if x)
        if make:
            desc += f"<br/><font color='#64748B' size='7'>{esc(make)}</font>"
        desc += f"<br/><font color='#64748B' size='7'>{esc(_short(l.description, 110))}</font>"
        if category.get(l.line_no) not in ("software", "service") and warranty.get(l.line_no):
            desc += f"<br/><font color='#64748B' size='7'>Warranty: {warranty[l.line_no]} months</font>"
        if l.bundle_name:
            desc += f"<br/><font color='#8A5A0B' size='7'>Includes {esc(l.bundle_name)} at no extra charge</font>"
        tax = f"{l.tax_rate_pct:g}%" if l.tax_rate_pct else "0%"
        row = [Paragraph(str(l.line_no), st["cell"]), Paragraph(desc, st["cell"])]
        if show_code:
            row.append(Paragraph(esc(d.get("hsn") or "—"), st["cell"]))
        row += [Paragraph(f"{l.quantity:,}", st["cell_r"]), Paragraph(esc(l.unit or "unit"), st["cell_r"]),
                Paragraph(esc(money(l.unit_price)), st["cell_r"]), Paragraph(tax, st["cell_r"]),
                Paragraph(esc(money(l.net)), st["cell_r"])]
        rows.append(row)
    fixed = [10 * mm] + ([16 * mm] if show_code else []) + [12 * mm, 12 * mm, 24 * mm, 11 * mm, 26 * mm]
    widths = [fixed[0], content_w - sum(fixed)] + fixed[1:]
    story.append(_table(rows, widths, zebra=False))

    # ---- totals and amount in words
    totals = [[Paragraph("Subtotal", st["total_label"]), Paragraph(esc(money(loc.subtotal)), st["total_value"])]]
    for t in loc.tax_breakdown:
        totals.append([Paragraph(f"{esc(t.name)} @ {t.rate_pct:g}%", st["total_label"]), Paragraph(esc(money(t.amount)), st["total_value"])])
    totals.append([Paragraph(f"Total ({loc.currency})", st["grand_label"]), Paragraph(esc(money(loc.grand_total)), st["grand_value"])])
    tt = Table(totals, colWidths=[56 * mm, 34 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND), ("TOPPADDING", (0, -1), (-1, -1), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]))
    words = Paragraph(f"<font name='Inter-SemiBold' color='#0F172A'>Amount in words:</font> "
                      f"{esc(amount_in_words(loc.grand_total, loc.currency))}", st["body"])
    story += [Spacer(1, 2 * mm), KeepTogether([tt, Spacer(1, 3 * mm), words])]

    if proposal.inclusions:
        story += [Spacer(1, 5 * mm), Paragraph("Included at no extra charge", st["h3"])]
        for inc in proposal.inclusions:
            story.append(Paragraph(f"<font name='Inter-Medium' color='#0F172A'>{esc(inc['service'])}</font> for "
                                   f"{esc(inc['item'])} × {inc['quantity']:,} — {esc(inc['description'])}", st["bullet"], bulletText="•"))

    # ---- terms and conditions
    story += [CondPageBreak(45 * mm), Spacer(1, 4 * mm), Paragraph("Terms and conditions", st["h3"])]
    for i, (heading, text) in enumerate(_quotation_terms(company, parsed, strat, loc, proposal), 1):
        story.append(Paragraph(f"<font name='Inter-Medium' color='#0F172A'>{i}. {esc(heading)}.</font> {esc(text)}", st["body"]))
        story.append(Spacer(1, 1.2 * mm))

    # ---- bank details and signature
    bank = company.get("bank") or {}
    bank_rows = [(k, v) for k, v in (("Account name", company["name"]), ("Bank", bank.get("name")),
                                     ("Account no.", bank.get("account")), ("IFSC", bank.get("ifsc")),
                                     ("Sort / routing code", bank.get("routing")), ("SWIFT", bank.get("swift"))) if v]
    bank_block = _kv_block("Bank details for payment", bank_rows, st, half)
    signer = proposal.signatory
    sign = Table([
        [Paragraph(f"FOR {esc(company['name']).upper()}", st["label"])],
        [Spacer(1, 17 * mm)],
        [Paragraph(f"<font name='Inter-SemiBold' color='#0F172A'>{esc(signer['name'])}</font><br/>"
                   f"{esc(signer['title'])}<br/>Authorised signatory", st["value"])],
    ], colWidths=[half])
    sign.setStyle(TableStyle([("LINEBELOW", (0, 1), (0, 1), 0.6, MUTED), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    closing = Table([[bank_block, sign]], colWidths=[half + 8 * mm, half])
    closing.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [Spacer(1, 6 * mm), KeepTogether([closing])]

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
