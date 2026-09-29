"""Bid analysis report — an executive, presentation-grade PDF.

Complements the client quotation and the internal pricing memo with a
narrative view of the bid: the recommendation, competitive position by line,
margin structure, the key pricing decisions, delivery roadmap, requirement
coverage and the risks a reviewer should weigh. Visual language: generous
white space, a serif display face, small letter-spaced section labels,
gradient score bars and soft cards.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.agents.messages import CompetitiveAnalysis, Localisation, ParsedRfp, PricedLine, Proposal
from app.finance.money import fmt
from app.services.pdf_renderer import FONT_DIR, NumberedCanvas, _register_fonts, esc

NAVY = colors.HexColor("#12263A")
INK = colors.HexColor("#1E2A36")
BODY = colors.HexColor("#3F4A56")
MUTED = colors.HexColor("#8A7E6B")
GOLD = colors.HexColor("#B8862B")
GOLD_LIGHT = colors.HexColor("#E4C98F")
TRACK = colors.HexColor("#F4ECDD")
CARD = colors.HexColor("#FBF7EF")
CARD_LINE = colors.HexColor("#EFE3CB")
SLATE = colors.HexColor("#5B7896")
SLATE_LIGHT = colors.HexColor("#B9CADB")
GOOD = colors.HexColor("#2F7D6D")
WARN = colors.HexColor("#B7791F")
BAD = colors.HexColor("#B4443C")

_ready = False


def _fonts() -> None:
    global _ready
    if _ready:
        return
    _register_fonts()
    pdfmetrics.registerFont(TTFont("Serif", str(FONT_DIR / "SourceSerif4-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Serif-SemiBold", str(FONT_DIR / "SourceSerif4-SemiBold.ttf")))
    _ready = True


def _styles() -> dict[str, ParagraphStyle]:
    _fonts()
    base = ParagraphStyle("b", fontName="Inter-Regular", fontSize=9.4, leading=14.6, textColor=BODY)
    return {
        "body": base,
        "small": ParagraphStyle("s", parent=base, fontSize=7.8, leading=11.4, textColor=MUTED),
        "title": ParagraphStyle("t", parent=base, fontName="Serif-SemiBold", fontSize=27, leading=31, textColor=INK),
        "meta": ParagraphStyle("m", parent=base, fontSize=8.8, textColor=MUTED),
        "eyebrow": ParagraphStyle("e", parent=base, fontName="Inter-SemiBold", fontSize=7.6, leading=10, textColor=GOLD,
                                  spaceBefore=16, spaceAfter=8),
        "lead": ParagraphStyle("l", parent=base, fontName="Serif-SemiBold", fontSize=15.5, leading=20.5, textColor=INK,
                               spaceAfter=7),
        "h3": ParagraphStyle("h3", parent=base, fontName="Inter-SemiBold", fontSize=10, leading=13.5, textColor=INK),
        "label": ParagraphStyle("lb", parent=base, fontName="Inter-SemiBold", fontSize=8.6, leading=11, textColor=INK),
        "bullet": ParagraphStyle("bu", parent=base, leftIndent=13, spaceAfter=5),
    }


def spaced(text: str) -> str:
    """Letter-spaced small caps label."""
    return "&nbsp;".join(esc(text.upper()))


# --------------------------------------------------------------------------- flowables


class ScoreBar(Flowable):
    """Label row above a rounded gradient bar with the value at its right end."""

    def __init__(self, label: str, sub: str, value: float, width: float, display: str, tone: str = "gold") -> None:
        super().__init__()
        self.label, self.sub, self.value, self.w, self.display, self.tone = label, sub, max(0.0, min(1.0, value)), width, display, tone

    def wrap(self, *_):
        return self.w, 27

    def draw(self) -> None:
        c = self.canv
        c.setFont("Inter-SemiBold", 8.6)
        c.setFillColor(INK)
        c.drawString(0, 18, self.label)
        lw = pdfmetrics.stringWidth(self.label, "Inter-SemiBold", 8.6)
        c.setFont("Inter-Regular", 7.6)
        c.setFillColor(MUTED)
        c.drawString(lw + 6, 18, self.sub)
        h, r = 8.5, 4.25
        c.setFillColor(TRACK)
        c.roundRect(0, 3, self.w, h, r, stroke=0, fill=1)
        fw = max(h, self.w * self.value)
        start, end = (GOLD_LIGHT, GOLD) if self.tone == "gold" else (SLATE_LIGHT, SLATE)
        c.saveState()
        p = c.beginPath()
        p.roundRect(0, 3, fw, h, r)
        c.clipPath(p, stroke=0, fill=0)
        c.linearGradient(0, 0, fw, 0, (start, end), extend=False)
        c.restoreState()
        c.setFont("Inter-SemiBold", 7.8)
        c.setFillColor(INK)
        c.drawRightString(self.w - 6, 4.8, self.display)


class Tiles(Flowable):
    """A row of soft rounded KPI tiles with serif figures."""

    def __init__(self, items: list[tuple[str, str]], width: float, height: float = 50) -> None:
        super().__init__()
        self.items, self.w, self.h = items, width, height

    def wrap(self, *_):
        return self.w, self.h

    def draw(self) -> None:
        c = self.canv
        gap = 7
        tw = (self.w - gap * (len(self.items) - 1)) / len(self.items)
        for i, (value, label) in enumerate(self.items):
            x = i * (tw + gap)
            c.setFillColor(CARD)
            c.setStrokeColor(CARD_LINE)
            c.setLineWidth(0.6)
            c.roundRect(x, 0, tw, self.h, 7, stroke=1, fill=1)
            size = 15 if len(value) < 12 else 12.5
            c.setFont("Serif-SemiBold", size)
            c.setFillColor(INK)
            c.drawCentredString(x + tw / 2, self.h - 24, value)
            c.setFont("Inter-Regular", 7.2)
            c.setFillColor(MUTED)
            c.drawCentredString(x + tw / 2, 11, label)


class StackBar(Flowable):
    """Revenue split into cost, bundled services and margin, with a legend."""

    def __init__(self, parts: list[tuple[str, float, colors.Color, str]], width: float) -> None:
        super().__init__()
        self.parts, self.w = parts, width

    def wrap(self, *_):
        return self.w, 42

    def draw(self) -> None:
        c = self.canv
        total = sum(p[1] for p in self.parts) or 1
        h, y = 12, 26
        c.saveState()
        path = c.beginPath()
        path.roundRect(0, y, self.w, h, 6)
        c.clipPath(path, stroke=0, fill=0)
        x = 0.0
        for _, value, colour, _ in self.parts:
            w = self.w * value / total
            c.setFillColor(colour)
            c.rect(x, y, w + 0.5, h, stroke=0, fill=1)
            x += w
        c.restoreState()
        lx = 0.0
        for label, value, colour, text in self.parts:
            c.setFillColor(colour)
            c.circle(lx + 3.5, 10.5, 3.2, stroke=0, fill=1)
            c.setFont("Inter-SemiBold", 7.8)
            c.setFillColor(INK)
            c.drawString(lx + 10, 8, label)
            c.setFont("Inter-Regular", 7.6)
            c.setFillColor(MUTED)
            lw = pdfmetrics.stringWidth(label, "Inter-SemiBold", 7.8)
            c.drawString(lx + 14 + lw, 8, f"{text} · {100 * value / total:.1f}%")
            lx += self.w / len(self.parts)


class Timeline(Flowable):
    """Dotted milestone timeline with a connecting rule."""

    def __init__(self, items: list[tuple[str, str]], width: float, styles) -> None:
        super().__init__()
        self.items, self.w, self.st = items, width, styles
        self._paras = []

    def wrap(self, *_):
        self._paras = []
        total = 0.0
        for head, text in self.items:
            ph = Paragraph(f"<font name='Inter-SemiBold' color='#B8862B'>{esc(head)}</font>", self.st["body"])
            pt = Paragraph(esc(text), self.st["body"])
            h1 = ph.wrap(self.w - 16, 1000)[1]
            h2 = pt.wrap(self.w - 16, 1000)[1]
            self._paras.append((ph, h1, pt, h2))
            total += h1 + h2 + 9
        self.h = total
        return self.w, total

    def draw(self) -> None:
        c = self.canv
        y = self.h
        centres = []
        for ph, h1, pt, h2 in self._paras:
            y -= h1
            ph.drawOn(c, 16, y)
            centres.append(y + h1 / 2)
            y -= h2
            pt.drawOn(c, 16, y)
            y -= 9
        c.setStrokeColor(GOLD_LIGHT)
        c.setLineWidth(1.2)
        if len(centres) > 1:
            c.line(4, centres[0], 4, centres[-1])
        for cy in centres:
            c.setFillColor(colors.white)
            c.circle(4, cy, 4.2, stroke=0, fill=1)
            c.setFillColor(GOLD)
            c.circle(4, cy, 3.1, stroke=0, fill=1)


class Dots(Flowable):
    """Bulleted list with coloured dots (like a key-points panel)."""

    def __init__(self, items: list[tuple[str, colors.Color]], width: float, styles) -> None:
        super().__init__()
        self.items, self.w, self.st = items, width, styles

    def wrap(self, *_):
        self._paras = []
        total = 0.0
        for text, colour in self.items:
            p = Paragraph(text, self.st["body"])
            h = p.wrap(self.w - 16, 1000)[1]
            self._paras.append((p, h, colour))
            total += h + 6
        self.h = total
        return self.w, total

    def draw(self) -> None:
        y = self.h
        for p, h, colour in self._paras:
            y -= h
            p.drawOn(self.canv, 16, y)
            self.canv.setFillColor(colour)
            self.canv.circle(5, y + h - 5.5, 3.3, stroke=0, fill=1)
            y -= 6


def _card(content: list, width: float) -> Table:
    t = Table([[content]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD), ("BOX", (0, 0), (-1, -1), 0.6, CARD_LINE),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    return t


# --------------------------------------------------------------------------- narrative helpers

STRATEGY_NOTES = {
    "Value differentiation": "competitor below our cost or margin floor; we hold price and include a free service",
    "Floor defence": "competitor below our margin floor; held at the policy minimum",
    "Competitive undercut": "priced just under the lowest competitor",
    "Competitive match": "priced level with the market",
    "Margin capture": "market sits above our standard price; margin retained",
    "Value premium": "priced above market, justified by warranty, lead time or service",
    "Standard pricing": "no market reference; list less volume tier",
    "Reviewer override": "price set manually by the reviewer",
}


def _verdict(strat: CompetitiveAnalysis) -> tuple[str, str]:
    p, m = strat.win_probability, strat.margin_pct
    if p >= 0.55 and m >= 10:
        return "Strong bid", "Recommend submitting as priced."
    if p >= 0.35:
        return "Competitive bid", "Recommend submitting; value-led positioning carries the offer."
    return "Stretch bid", "Submit only if the relationship justifies it; several lines face aggressive pricing."


def render_report(path: Path, *, company: dict, parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation,
                  proposal: Proposal, approval: dict | None = None) -> Path:
    st = _styles()
    page_w, page_h = A4
    margin = 22 * mm
    width = page_w - 2 * margin
    base = strat.base_currency
    mb = lambda v: fmt(v, base, 0)  # noqa: E731
    mc = lambda v: fmt(v, loc.currency, loc.decimals)  # noqa: E731

    def decorate(c, _doc):
        c.saveState()
        # Wordmark: small diamond + letter-spaced name.
        x, y = margin, page_h - 15 * mm
        c.setFillColor(GOLD)
        p = c.beginPath()
        p.moveTo(x + 4, y + 8)
        p.lineTo(x + 8, y + 4)
        p.lineTo(x + 4, y)
        p.lineTo(x, y + 4)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFont("Inter-SemiBold", 7.4)
        c.drawString(x + 14, y + 1.5, "  ".join(" ".join(company["short_name"].upper()).split("   ")))
        c.setFont("Inter-Regular", 6.8)
        c.setFillColor(MUTED)
        c.drawRightString(page_w - margin, y + 7, "BID ANALYSIS")
        c.setFont("Inter-SemiBold", 9.5)
        c.setFillColor(GOLD)
        c.drawRightString(page_w - margin, y - 4, " ".join(proposal.quote_number))
        c.setFont("Inter-Regular", 7)
        c.setFillColor(MUTED)
        c.drawString(margin, 10 * mm, f"{company['short_name']} · Bid analysis report")
        if not approval:
            c.drawCentredString(page_w / 2, 10 * mm, "Draft for internal review")
        c.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=28 * mm,
                          bottomMargin=22 * mm, title=f"Bid analysis — {parsed.client.name or ''}",
                          author=company["name"])
    doc.addPageTemplates([PageTemplate("r", [Frame(margin, 20 * mm, width, page_h - 48 * mm, id="f")], onPage=decorate)])

    s: list = []
    client = parsed.client.name or "Client"
    meta = [x for x in [
        f"Ref {parsed.client_reference}" if parsed.client_reference else None,
        f"Due {date.fromisoformat(parsed.due_date):%d %B %Y}" if parsed.due_date else None,
        f"Prepared {date.fromisoformat(proposal.issue_date):%d %B %Y}",
        f"Version {proposal.version}",
    ] if x]
    s += [Paragraph(esc(client), st["title"]), Spacer(1, 4), Paragraph(esc("  ·  ".join(meta)), st["meta"]), Spacer(1, 10)]
    s.append(Table([[""]], colWidths=[width], rowHeights=[1], style=[("LINEABOVE", (0, 0), (-1, -1), 0.6, CARD_LINE)]))

    verdict, advice = _verdict(strat)
    s.append(Paragraph(spaced(f"{verdict} · {advice.split(';')[0].rstrip('.')}"), st["eyebrow"]))
    s.append(Paragraph(
        f"A {mc(loc.grand_total)} offer at {strat.margin_pct:.1f}% gross margin, with a "
        f"{100 * strat.win_probability:.0f}% modelled chance of winning.", st["lead"]))
    vd = strat.strategy_counts.get("Value differentiation", 0)
    summary = (
        f"We have priced {len(strat.lines)} lines for {esc(client)}"
        f"{', ' + esc(parsed.client.city or parsed.client.country_name or '') if (parsed.client.city or parsed.client.country_name) else ''}. "
        f"{strat.below_cost_competitors} line(s) meet competitors priced below our own landed cost"
        + (f"; on {vd} line(s) we hold price and compete on value, including services worth {mc(loc.bundled_value)} at no charge. "
           if vd else ". ")
        + f"Tax treatment: {esc(loc.tax_summary)}; the quotation is issued in {loc.currency}. {esc(advice)}"
    )
    s += [Paragraph(summary, st["body"]), Spacer(1, 12)]
    s.append(Tiles([
        (mc(loc.grand_total), "quotation value"),
        (f"{strat.margin_pct:.1f}%", "gross margin"),
        (f"{100 * strat.win_probability:.0f}%", "win probability"),
        (mb(strat.expected_profit), "expected profit"),
    ], width))

    s.append(Paragraph(spaced("Win probability by line"), st["eyebrow"]))
    for line in sorted(strat.lines, key=lambda l: -l.revenue):
        s.append(ScoreBar(line.name if len(line.name) < 46 else line.name[:44] + "…", line.strategy.lower(),
                          line.win_probability, width, f"{100 * line.win_probability:.0f}"))
    s.append(Spacer(1, 3))
    s.append(Paragraph("Bars show the modelled chance of winning each line at the recommended price and terms, "
                       "ordered by line value.", st["small"]))

    # ---- economics
    s.append(CondPageBreak(90 * mm))
    s.append(Paragraph(spaced("Margin structure"), st["eyebrow"]))
    s.append(StackBar([
        ("Landed cost", strat.cost, SLATE_LIGHT, mb(strat.cost)),
        ("Services", strat.bundle_cost, GOLD_LIGHT, mb(strat.bundle_cost)),
        ("Margin", max(0.0, strat.margin), GOLD, mb(strat.margin)),
    ], width))
    s.append(Spacer(1, 6))
    offers = sum(l.market.count for l in strat.lines)
    overrides = sum(1 for l in strat.lines if l.overridden)
    s.append(Paragraph(spaced("How the price was set"), st["eyebrow"]))
    s.append(Tiles([
        (str(offers), "competitor offers analysed"),
        (str(strat.below_cost_competitors), "lines with below-cost rivals"),
        (str(sum(1 for l in strat.lines if l.bundle)), "value bundles included"),
        (str(overrides), "reviewer adjustments"),
    ], width, 46))
    s.append(Spacer(1, 10))
    for name, count in sorted(strat.strategy_counts.items(), key=lambda kv: -kv[1]):
        s.append(Paragraph(f"<font name='Inter-SemiBold' color='#1E2A36'>{esc(name)}</font> — {count} line(s): "
                           f"{esc(STRATEGY_NOTES.get(name, ''))}.", st["bullet"], bulletText="•"))

    # ---- key decisions
    s.append(CondPageBreak(60 * mm))
    s.append(Paragraph(spaced("Key pricing decisions"), st["eyebrow"]))
    for line in _key_lines(strat):
        best = line.market.best
        facts = f"Our price {mb(line.unit_price)} per {line.unit}"
        if best:
            facts += f" · lowest competitor {esc(best.competitor)} at {mb(best.unit_price_base)}"
        facts += f" · landed cost {mb(line.unit_cost)}"
        body = [
            Paragraph(f"{esc(line.name)} <font name='Inter-Regular' size='8' color='#8A7E6B'>× {line.quantity:,}</font>", st["h3"]),
            Spacer(1, 5),
            ScoreBar("Margin", f"{line.margin_pct:.1f}% after services", max(0.0, line.margin_pct) / 30, width - 24,
                     f"{line.margin_pct:.1f}%", tone="slate"),
            Spacer(1, 4),
            Paragraph(esc(line.headline) + ".", st["body"]),
            Spacer(1, 3),
            Paragraph(esc(_pick_reason(line)), st["body"]),
            Spacer(1, 4),
            Paragraph(esc(facts), st["small"]),
        ]
        if line.bundle:
            body.append(Paragraph(f"Included at no charge: {esc(line.bundle.name)} — worth {mb(line.bundle.total_value)} to the client.",
                                  ParagraphStyle("gold", parent=st["small"], textColor=GOLD)))
        s += [KeepTogether([_card(body, width)]), Spacer(1, 7)]

    # ---- delivery
    s.append(CondPageBreak(60 * mm))
    s.append(Paragraph(spaced("Delivery roadmap"), st["eyebrow"]))
    s.append(Timeline([(f"Day {m.day} — {m.label}", m.detail) for m in proposal.milestones], width, st))
    if parsed.terms.delivery_days:
        done = proposal.milestones[-1].day if proposal.milestones else 0
        s.append(Spacer(1, 4))
        s.append(Paragraph(f"Requested completion within {parsed.terms.delivery_days} days; planned completion day {done}"
                           f"{' — comfortably inside the window.' if done <= parsed.terms.delivery_days else ' — phased delivery proposed.'}",
                           st["small"]))

    # ---- requirements
    if proposal.compliance:
        s.append(CondPageBreak(50 * mm))
        s.append(Paragraph(spaced("Requirement coverage"), st["eyebrow"]))
        counted = [r for r in proposal.compliance if r.status != "Noted"]
        met = sum(1 for r in counted if r.status.startswith("Complies"))
        if counted:
            s.append(ScoreBar("Requirements met", f"{met} of {len(counted)} stated requirements",
                              met / len(counted), width, f"{met}/{len(counted)}"))
            s.append(Spacer(1, 6))
        tone = {"Complies": GOOD, "Complies with note": WARN, "Clarification required": BAD, "Noted": SLATE_LIGHT}
        s.append(Dots([(f"<font name='Inter-SemiBold' color='#1E2A36'>{esc(r.status)}</font> — {esc(r.response)}",
                        tone[r.status]) for r in proposal.compliance if r.status != "Noted"], width, st))

    # ---- risks and next steps
    s.append(CondPageBreak(50 * mm))
    s.append(Paragraph(spaced("Risks to weigh"), st["eyebrow"]))
    risks = _risks(parsed, strat, loc)
    s.append(Dots([(esc(r), BAD if i < 2 else WARN) for i, r in enumerate(risks)] or
                  [("No material risks identified.", GOOD)], width, st))
    s.append(Paragraph(spaced("Next steps"), st["eyebrow"]))
    steps = [
        "Review the flagged lines in the pricing console and confirm or adjust the recommended prices.",
        "Confirm stock and lead times with distribution for any backordered items before approval.",
        "Approve the quotation to issue the final document without the draft marking.",
        f"Submit to {esc(parsed.client.contact_name or 'the client')} before "
        f"{date.fromisoformat(parsed.due_date):%d %B %Y}." if parsed.due_date else "Submit to the client.",
    ]
    s.append(Dots([(t, GOLD) for t in steps], width, st))
    if approval:
        s.append(Spacer(1, 8))
        s.append(Paragraph(f"Approved by {esc(approval.get('actor', ''))} on {esc(approval.get('at', ''))}.", st["body"]))
    s.append(Spacer(1, 14))
    s.append(Table([[""]], colWidths=[width], rowHeights=[1], style=[("LINEABOVE", (0, 0), (-1, -1), 0.6, CARD_LINE)]))
    s.append(Spacer(1, 6))
    s.append(Paragraph(
        "Win probabilities come from a logistic model trained on historical bid outcomes and competitor prices from the "
        "market intelligence feed; they indicate relative likelihood, not certainty. Prices respect the minimum-margin "
        "policy for every product. Exchange rate: " + esc(f"{loc.fx_source}, as of {loc.fx_as_of}") + ".", st["small"]))

    doc.build(s, canvasmaker=NumberedCanvas)
    return path


def _key_lines(strat: CompetitiveAnalysis) -> list[PricedLine]:
    """The lines a reviewer most needs to understand: high value or strategically interesting."""
    interesting = [l for l in strat.lines if l.strategy in ("Value differentiation", "Floor defence", "Reviewer override") or l.flags]
    ranked = sorted(interesting, key=lambda l: -l.revenue)[:3]
    for l in sorted(strat.lines, key=lambda l: -l.revenue):
        if len(ranked) >= 3:
            break
        if l not in ranked:
            ranked.append(l)
    return ranked


def _pick_reason(line: PricedLine) -> str:
    for r in line.rationale:
        if r.startswith(("The best competitor", "Policy:", "The bundle outperforms", "No policy-compliant")):
            return r
    return line.rationale[-2] if len(line.rationale) > 1 else (line.rationale[0] if line.rationale else "")


def _risks(parsed: ParsedRfp, strat: CompetitiveAnalysis, loc: Localisation) -> list[str]:
    out = []
    low = [l for l in strat.lines if l.win_probability < 0.25]
    if low:
        out.append(f"{len(low)} line(s) have a win probability below 25% ({', '.join(l.name for l in low[:3])}); "
                   "competitors are pricing below what our margin policy allows.")
    back = [l for l in strat.lines if any(f.startswith("Backorder") for f in l.flags)]
    if back:
        out.append(f"Stock is short for {', '.join(l.name for l in back)}; confirm distributor lead times.")
    manual = [l for l in strat.lines if l.overridden and ("Below margin floor" in l.flags or "Loss-making price" in l.flags)]
    if manual:
        out.append(f"Reviewer prices breach the margin floor on {len(manual)} line(s).")
    if parsed.terms.lowest_price_award:
        out.append("The award goes to the lowest compliant bid, so value-led pricing carries more risk than usual.")
    if loc.fx_stale and loc.currency != loc.base_currency:
        out.append("Exchange rates come from a fallback source; confirm before sending.")
    if loc.currency != loc.base_currency:
        out.append(f"Currency exposure: the quote is fixed in {loc.currency}; a {loc.fx_buffer_pct:g}% buffer is included.")
    out += [w for w in parsed.warnings if "no suitable catalogue match" in w]
    return out
