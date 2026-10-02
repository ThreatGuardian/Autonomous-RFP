"""Warranty obligations: what each line must carry, and how to meet it.

A tender may require longer cover than the manufacturer's standard warranty
("5 years comprehensive onsite"). When a warranty-extension value-add closes
the gap it is *mandatory* for that line: its cost belongs in the landed cost
and its value in the price, rather than being offered as a free bundle.
"""

from __future__ import annotations

import re

from app.agents.messages import ParsedRfp, ValueAddOption
from app.nlp.text import parse_number

HARDWARE_EXCLUDED = {"software", "service", "cabling"}
_WARRANTY_RE = re.compile(r"(\d+|one|two|three|four|five|six|seven)\s*[- ]?\s*(years?|yrs?|months?)", re.I)


def months_in(text: str) -> int | None:
    m = _WARRANTY_RE.search(text)
    if not m:
        return None
    n = parse_number(m.group(1))
    if n is None:
        return None
    return int(n * 12 if m.group(2).lower().startswith("y") else n)


def months_by_category(text: str) -> dict[str, int]:
    """Per-category durations in a clause that names several ("cards three years and UPS two years").

    The clause is cut after each duration; the categories named in a piece take
    that piece's duration. A single-duration clause maps all named categories.
    """
    out: dict[str, int] = {}
    start = 0
    for m in _WARRANTY_RE.finditer(text):
        n = parse_number(m.group(1))
        if n is None:
            continue
        months = int(n * 12 if m.group(2).lower().startswith("y") else n)
        for cat in _named_categories(text[start:m.end()]):
            out.setdefault(cat, months)
        start = m.end()
    return out


def required_months(parsed: ParsedRfp, line_no: int, category: str) -> tuple[int | None, str | None]:
    """Months of warranty the request requires for one line, and where that came from."""
    if category in HARDWARE_EXCLUDED:
        return None, None
    for r in parsed.requirements:
        if r.line_no == line_no and r.source == "table" and re.match(r"\s*warranty\b", r.text, re.I):
            months = months_in(r.text)
            if months:
                return months, f"clause {r.clause}" if r.clause else "specification"
    doc = parsed.document
    if doc is not None and doc.long_form:
        # In long tenders a general warranty clause applies only to the categories it names.
        for r in parsed.requirements:
            if r.category == "warranty" and "warrant" in r.text.lower() and months_in(r.text):
                per = months_by_category(r.text)
                if category in per:
                    return per[category], f"clause {r.clause}" if r.clause else "warranty clause"
        return None, None
    need = parsed.terms.warranty_months_required
    return (need, "warranty requirement") if need else (None, None)


_CATEGORY_WORDS = {
    "desktop": ("desktop",), "laptop": ("laptop", "notebook"), "monitor": ("monitor", "display"),
    "network_switch": ("switch",), "wireless": ("access point", "wireless"), "firewall": ("firewall",),
    "server": ("server",), "storage": ("storage", "nas"), "power": ("ups",), "printer": ("printer",),
    "workstation": ("workstation",), "peripheral": ("keyboard", "mouse", "webcam", "peripheral"),
    "audio": ("headset", "headphone"), "component": ("graphics card", "gpu", "processor"),
}


def _named_categories(text: str) -> set[str]:
    t = text.lower()
    if re.search(r"end[- ]user (?:devices|computing|equipment)", t):
        return {"desktop", "laptop", "monitor", "workstation", "peripheral", "audio", "printer"}
    if re.search(r"\ball (?:the )?(?:hardware|equipment|items|goods|devices)\b", t):
        return set(_CATEGORY_WORDS)
    return {cat for cat, words in _CATEGORY_WORDS.items() if any(w in t for w in words)}


def extension_for(options: list[ValueAddOption], have: int, need: int) -> ValueAddOption | None:
    """Smallest warranty extension that closes the gap between ``have`` and ``need`` months."""
    fits = [o for o in options if o.kind == "warranty" and o.warranty_extension_months and have + o.warranty_extension_months >= need]
    return min(fits, key=lambda o: (o.warranty_extension_months, o.unit_cost)) if fits else None
