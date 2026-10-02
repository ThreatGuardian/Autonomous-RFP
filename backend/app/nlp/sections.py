"""Section tree of a tender document.

Headings are recognised from three independent signals and reconciled:

* **numbering** – ``5.1 Desktop Computer``; a numbered block whose text reads
  like a sentence (``2.3.1 The bid shall be submitted …``) is a *clause*, not a
  heading, and only lends its number to the requirements inside it;
* **keywords** – ``SECTION III – …``, ``Part B``, ``Annexure-3: …``;
* **typography** – larger or bold type in PDFs, Word heading styles in DOCX,
  short all-capitals lines in text.

Each section is then typed (notice, instructions, eligibility, scope,
technical, bill of quantities, commercial, evaluation, conditions, forms) by a
weighted lexicon over its title, falling back to its body and finally to its
parent, so "5.3 Laptop" inherits *technical* from "Section V – Technical
Specifications".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.nlp.extractors import is_address_line
from app.nlp.layout import Block
from app.nlp.line_items import build_item

SECTION_KINDS = ("notice", "instructions", "eligibility", "scope", "technical", "boq", "commercial", "evaluation",
                 "conditions", "forms", "general")

_NUM_HEAD = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})\.?(?:\s+|(?=[A-Z]))(?P<title>\S.*)$")
_KEY_HEAD = re.compile(
    r"^(?P<kw>section|chapter|part|volume)\s*[-–:.]?\s*(?P<num>[ivxl]{1,5}|\d{1,2}|[a-h])\b\s*[:.\-–]*\s*(?P<title>.*)$", re.I)
_ANNEX_HEAD = re.compile(
    r"^(?P<kw>annexure|annex|appendix|attachment|exhibit|schedule|form|format|proforma)\s*[-–:.]?\s*"
    r"(?P<num>[ivx]{1,4}|\d{1,2}|[a-h])?\b\s*[:.\-–]*\s*(?P<title>.*)$", re.I)
_LETTER_HEAD = re.compile(r"^(?P<num>[A-H])[.)]\s+(?P<title>[A-Z].{2,80})$")
_MODAL = re.compile(r"\b(shall|must|will|should|may|is|are|has|have|be|being|was|were)\b", re.I)
CLAUSE_NO = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,4}|\(?[a-z]\)|\(?[ivx]{1,4}\))\.?(?:\s+|(?=[A-Z]))")

# Lexicon: (kind, pattern, weight). Weights encode how specific a phrase is.
_LEXICON: list[tuple[str, str, float]] = [
    ("notice", r"notice inviting|invitation (?:for|to) (?:bids?|tenders?|proposals?)|\bnit\b|tender notice|key (?:dates|data)|"
               r"critical dates|important dates|bid data sheet|data sheet|fact sheet", 3),
    ("instructions", r"instructions? to (?:bidders|tenderers|consultants|applicants)|\bitb\b|bidding procedure|"
                     r"preparation (?:and submission )?of (?:bids?|proposals?)|submission of (?:bids?|proposals?)|"
                     r"general instructions|clarifications?|pre-?bid", 3),
    ("instructions", r"\bsubmission\b|\bsubmitting\b|how to (?:bid|apply|respond)", 2),
    ("eligibility", r"eligib\w*|pre-?qualification|qualification criteria|qualifying criteria|minimum qualification|"
                    r"bidder'?s? qualification", 3.5),
    ("scope", r"scope of (?:the )?(?:work|supply|services|project)|terms of reference|statement of work|background|"
              r"objectives?|project overview|about the|deliverables|introduction", 2),
    ("technical", r"technical specifications?|specifications?|technical requirements|functional requirements|"
                  r"minimum specifications?", 3),
    ("boq", r"bill of (?:quantities|quantity|materials?)|\bbo[qm]\b|schedule of (?:requirements|quantities)|list of items|"
            r"price schedule", 3.5),
    ("commercial", r"commercial", 4),
    ("commercial", r"payment|prices?\b|tax(?:es)?\b|earnest money|\bemd\b|bid security|performance (?:security|bank guarantee)|"
                   r"liquidated damages|penalt\w*|warranty|delivery|completion|inspection|acceptance", 2),
    ("evaluation", r"evaluation|selection (?:method|procedure)|award of|\bqcbs\b|scoring|marking scheme", 3),
    ("conditions", r"general conditions|special conditions|conditions of contract|\b[gs]cc\b|terms and conditions|termination|"
                   r"arbitration|force majeure|disputes?|jurisdiction|indemn\w*|confidential\w*|general terms", 3),
    ("forms", r"annexure|\bannex\b|appendix|format\b|\bform\b|declaration|undertaking|affidavit|proforma|checklist|"
              r"covering letter|authori[sz]ation|power of attorney|submission form", 2),
]
_LEX = [(k, re.compile(p, re.I), w) for k, p, w in _LEXICON]


@dataclass
class Section:
    id: str
    number: str | None
    title: str
    level: int
    kind: str = "general"
    kind_confidence: float = 0.0
    parent: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    keyword: bool = False  # "Section III", "Annexure-2": structural roots
    heading_block: int | None = None
    blocks: list[int] = field(default_factory=list)
    line_nos: list[int] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}".strip() if self.number and not self.keyword else self.title


def classify_title(title: str, body: str = "") -> tuple[str, float]:
    scores: dict[str, float] = {}
    for kind, pattern, weight in _LEX:
        if pattern.search(title):
            scores[kind] = max(scores.get(kind, 0.0), weight)
    if not scores and body:
        words = body[:3000]
        for kind, pattern, weight in _LEX:
            hits = len(pattern.findall(words))
            if hits:
                scores[kind] = scores.get(kind, 0.0) + 0.25 * weight * min(hits, 4)
        if scores and max(scores.values()) < 1.5:
            return "general", 0.0
    if not scores:
        return "general", 0.0
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, second = ranked[0][1], ranked[1][1] if len(ranked) > 1 else 0.0
    return ranked[0][0], round(top / (top + second + 0.5), 3)


def _looks_like_title(title: str, strong: bool) -> bool:
    words = title.split()
    if not words or len(words) > (18 if strong else 12):
        return False
    if title.rstrip().endswith((".", ";", ",")) and len(words) > 6:
        return False
    if re.search(r":\s*\S", title) and not strong:
        return False
    if not strong and _MODAL.search(title) and len(words) > 4:
        return False
    return bool(re.match(r"[A-Z(\"'0-9]", title))


def _is_caps_heading(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if re.search(r":\s*\S", text) or sum(c.isdigit() for c in text) > 0.15 * len(text):
        return False  # "GSTIN: 27AA…", "RFP NO.: KTU/…" are header fields, not headings
    return (len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) > 0.9 and len(text.split()) <= 12
            and not text.rstrip().endswith("."))


@dataclass
class _Heading:
    number: str | None
    title: str
    level: int
    keyword: bool


def detect_heading(block: Block, open_root_keyword: bool) -> _Heading | None:
    if block.kind != "text":
        return None
    text = re.sub(r"\s+", " ", block.text).strip()
    if len(text) > 160 or len(text) < 3:
        return None
    styled = block.style in ("heading", "title")
    m = _KEY_HEAD.match(text)
    if m and (styled or _is_caps_heading(text) or len(text.split()) <= 12):
        title = m.group("title").strip(" –-:.") or f"{m.group('kw').title()} {m.group('num').upper()}"
        return _Heading(m.group("num").upper(), title, 1, True)
    m = _ANNEX_HEAD.match(text)
    if m and (m.group("num") or m.group("kw").lower() in ("annexure", "annex", "appendix")) and len(text.split()) <= 16 \
            and (styled or _is_caps_heading(text) or m.group("num")):
        num = (m.group("num") or "").upper() or None
        label = f"{m.group('kw').title()}{'-' + num if num else ''}"
        title = m.group("title").strip(" –-:.")
        return _Heading(num, f"{label}: {title}" if title else label, 1, True)
    m = _NUM_HEAD.match(text)
    if m and (("." not in m.group("num") and int(m.group("num")) > 30) or is_address_line(text)):
        m = None  # "14 Wimpole Street, London W1G 9SX" is an address, not section 14
    if m and not styled and build_item(m.group("title")) is not None:
        m = None  # "3. 45 x 27-inch monitors" is a numbered request line, not a heading
    if m and _looks_like_title(m.group("title"), styled):
        depth = m.group("num").count(".") + 1
        level = block.level or depth
        if open_root_keyword and depth == 1 and not block.level:
            level = 2
        return _Heading(m.group("num"), m.group("title").strip(" :"), level, False)
    m = _LETTER_HEAD.match(text)
    if m and styled:
        return _Heading(m.group("num"), m.group("title"), 2, False)
    if styled and _looks_like_title(text, True) and not CLAUSE_NO.match(text):
        if block.level:
            return _Heading(None, text.strip(" :"), block.level, False)
        return _Heading(None, text.strip(" :"), 2 if open_root_keyword else 1, block.style == "title")
    if _is_caps_heading(text) and not CLAUSE_NO.match(text):
        return _Heading(None, text.title() if text.isupper() else text, 1, True)
    return None


def build_sections(blocks: list[Block]) -> tuple[list[Section], list[str | None]]:
    """Return the section list (document order) and each block's section id."""
    sections: list[Section] = []
    owner: list[str | None] = []
    stack: list[Section] = []
    # Everything before the first structural heading (numbered, "Section …", "Annexure …" or a
    # Word Heading 1) is the cover: letterhead, title and reference lines, not a section.
    cover_end = 0
    for i, block in enumerate(blocks):
        head = detect_heading(block, False)
        if head and (head.number or block.level == 1 or _KEY_HEAD.match(block.text)
                     or (head.keyword and _ANNEX_HEAD.match(block.text))):
            cover_end = i
            break
    for i, block in enumerate(blocks):
        if i < cover_end:
            owner.append(None)
            continue
        root_kw = bool(stack and stack[0].keyword)
        head = detect_heading(block, root_kw)
        if head:
            while stack and stack[-1].level >= head.level:
                stack.pop()
            sec = Section(id=f"S{len(sections) + 1}", number=head.number, title=head.title, level=head.level,
                          parent=stack[-1].id if stack else None, page_start=block.page, page_end=block.page,
                          keyword=head.keyword, heading_block=i)
            sections.append(sec)
            stack.append(sec)
            owner.append(sec.id)
            continue
        if stack:
            stack[-1].blocks.append(i)
            for s in stack:
                s.page_end = max(s.page_end or block.page, block.page)
            owner.append(stack[-1].id)
        else:
            owner.append(None)

    by_id = {s.id: s for s in sections}
    for s in sections:
        body = " ".join(blocks[i].text for i in s.blocks[:40])
        kind, conf = classify_title(s.title, body)
        # Annexure forms keep "forms" unless the title names a substantive kind (e.g. "Annexure-B: Technical Specifications").
        if s.keyword and re.match(r"(annex|appendix|attachment|exhibit|schedule|form|format|proforma)", s.title, re.I):
            if kind in ("general", "scope", "commercial") or conf < 0.5:
                kind, conf = "forms", max(conf, 0.6)
        parent = by_id.get(s.parent) if s.parent else None
        if (kind == "general" or conf < 0.45) and parent is not None and parent.kind != "general":
            kind, conf = parent.kind, round(parent.kind_confidence * 0.9, 3)
        elif parent is not None and parent.kind in ("forms", "technical", "boq") and kind in ("general", "scope", "commercial"):
            # Children of annexures, specification and schedule sections stay in their parent's kind
            # ("Warranty" as a specification parameter is not the contract's warranty clause).
            kind, conf = parent.kind, round(parent.kind_confidence * 0.9, 3)
        s.kind, s.kind_confidence = kind, conf
    return sections, owner


def section_path(sections: list[Section], sid: str | None) -> list[Section]:
    by_id = {s.id: s for s in sections}
    out: list[Section] = []
    while sid:
        s = by_id[sid]
        out.append(s)
        sid = s.parent
    return list(reversed(out))
