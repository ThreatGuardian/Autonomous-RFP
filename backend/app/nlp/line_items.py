"""Line-item extraction: tables, bullet lists and free-text requests.

The extractor is deliberately conservative about what counts as a quantity:
numbers attached to specification units (``16GB``, ``48-port``, ``27"``,
``3 years``) are never read as quantities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.nlp.text import NUMBER_WORD_RE, fold, words_to_number

SPEC_UNIT = (
    r"(?:gb|tb|mb|ghz|mhz|hz|w|watts?|va|kva|v|mm|cm|m|meters?|metres?|inch(?:es)?|in\b|\"|''|"
    r"ports?|port|u\b|core|cores|bays?|years?|yrs?|months?|days?|hours?|hrs?|%|ppm|mp|k\b|fps|x\d)(?![a-z])"
)
UNIT_WORDS = r"(?:nos?\.?|numbers|units?|pcs\.?|pieces?|sets?|licen[cs]es?|users?|seats?|boxes|box|kits?|lots?|devices?|days?|packs?|rolls?|each|ea)"
BRANDS = ["dell", "hp", "hpe", "lenovo", "apple", "cisco", "meraki", "aruba", "ubiquiti", "fortinet", "fortigate", "tp-link",
          "synology", "seagate", "samsung", "lg", "apc", "logitech", "jabra", "poly", "microsoft", "veeam", "sophos",
          "commscope", "netrack", "asus", "acer", "juniper", "netgear"]

_HEADER_HINT = re.compile(r"\b(qty|quantity|description|item|specification|units?|no\.?)\b", re.I)
_QTY_LABEL = re.compile(r"\b(?:qty|quantity|quantities|nos? required|count)\s*[:=\-–]?\s*(\d[\d,]*)", re.I)
_QTY_X = re.compile(
    r"(?:^|[\s(])(\d[\d,]*)\s*(?:x|×|\*)\s+"
    r"(?=[A-Za-z]|\d{1,2}(?:\.\d)?\s*(?:\"|''|-?\s*inch|in\b|-?\s*port|u\b|tb|gb|kva|va\b))",
    re.I,
)
_QTY_UNIT = re.compile(rf"\b(\d[\d,]*)\s*{UNIT_WORDS}(?=[\s.,;:)\-]|$)", re.I)
_QTY_UNIT_OF = re.compile(rf"\b(\d[\d,]*)\s*{UNIT_WORDS}\s+of\b", re.I)
_LEADING_QTY = re.compile(rf"^(?:\d+[.)]\s+)?(?:supply of |provide |procure(?:ment of)? |need |require |we require )?(\d[\d,]*)(?!\s*{SPEC_UNIT})(?![\d.,\-/])\s+(?=[A-Za-z])", re.I)
_TRAILING_QTY = re.compile(r"(?:\s[-–]|[:,(])\s*(\d[\d,]*)\s*\)?\s*$")
_BULLET = re.compile(r"^\s*(?:[-*•▪◦]|\(?[a-z0-9]{1,3}[.)]|item\s*\d+\s*[:.)-]|lot\s*\d+\s*[:.)-])\s*", re.I)


@dataclass
class RawItem:
    text: str
    description: str
    quantity: int
    quantity_source: str
    unit: str | None = None
    specs: dict[str, Any] = field(default_factory=dict)
    brand: str | None = None


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


def extract_quantity(text: str) -> tuple[int, str, tuple[int, int]] | None:
    """Return (quantity, rule, span) for the most reliable quantity cue in ``text``."""
    for pattern, rule in ((_QTY_LABEL, "labelled quantity"), (_QTY_X, "'N x item'"), (_QTY_UNIT_OF, "'N units of'"),
                          (_QTY_UNIT, "'N units'"), (_LEADING_QTY, "leading count")):
        m = pattern.search(text)
        if m:
            q = _to_int(m.group(1))
            if 0 < q < 100000:
                # Leading counts keep the verb ("supply of") out of the removed span.
                return q, rule, m.span(1) if rule == "leading count" else m.span()
    m = _TRAILING_QTY.search(text)
    if m and not re.search(SPEC_UNIT + r"\s*$", text[: m.start(1)], re.I):
        q = _to_int(m.group(1))
        if 0 < q < 100000:
            return q, "trailing count", m.span(1)
    for m in NUMBER_WORD_RE.finditer(text):
        phrase = m.group(0).strip()
        if phrase.lower() in {"a", "an", "one"}:
            continue
        after = text[m.end(): m.end() + 12]
        if re.match(rf"\s*{SPEC_UNIT}", after, re.I):
            continue
        n = words_to_number(phrase)
        if n and n > 1:
            return n, "number words", m.span()
    return None


_UNIT_OF = re.compile(UNIT_WORDS, re.I)


def extract_unit(text: str) -> str | None:
    m = re.search(rf"\b\d[\d,]*\s*({UNIT_WORDS})(?=[\s.,;:)]|$)", text, re.I)
    if not m:
        return None
    u = m.group(1).lower().rstrip(".")
    mapped = {"no": "unit", "nos": "unit", "numbers": "unit", "pcs": "piece", "ea": "unit", "each": "unit", "boxes": "box",
              "licences": "licence", "licenses": "licence", "sets": "set", "pieces": "piece"}
    return mapped.get(u, u[:-1] if u.endswith("s") and len(u) > 3 else u)


def extract_specs(text: str) -> dict[str, Any]:
    t = fold(text)
    specs: dict[str, Any] = {}
    m = re.search(r"(\d{1,3})\s*gb\s*(?:of\s*)?(?:ddr\d\s*)?(?:ram|memory)", t) or re.search(r"(?:ram|memory)\s*[:\-]?\s*(?:min(?:imum)?\.?\s*)?(\d{1,3})\s*gb", t)
    if m:
        specs["ram_gb"] = int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(gb|tb)\s*(?:nvme\s*|m\.2\s*|sata\s*)?(ssd|hdd|storage|disk|nvme|drive)", t)
    if m:
        size = float(m.group(1)) * (1000 if m.group(2) == "tb" else 1)
        specs["storage_gb"] = int(size)
        if m.group(3) in {"ssd", "nvme"}:
            specs["storage_type"] = "SSD"
        elif m.group(3) == "hdd":
            specs["storage_type"] = "HDD"
    m = re.search(r"(\d{2}(?:\.\d)?)\s*(?:\"|''|-?\s*inch(?:es)?|in\b)", t)
    if m:
        specs["screen_in"] = float(m.group(1))
    m = re.search(r"(\d{1,2})[\s-]*port", t)
    if m:
        specs["ports"] = int(m.group(1))
    if re.search(r"\bpoe\+?|power over ethernet", t):
        specs["poe"] = True
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kva|va)\b", t)
    if m:
        specs["capacity_va"] = int(float(m.group(1)) * (1000 if m.group(2) == "kva" else 1))
    m = re.search(r"\b(?:core\s*)?(i[3579])\b|core\s*ultra\s*([579])", t)
    if m:
        specs["cpu_tier"] = int((m.group(1) or "i" + m.group(2))[1])
    if re.search(r"\bxeon\b", t):
        specs["cpu_family"] = "xeon"
    if re.search(r"\b(4k|uhd|3840\s*x\s*2160)\b", t):
        specs["resolution"] = "4K"
    elif re.search(r"\b(fhd|full hd|1080p|1920\s*x\s*1080)\b", t):
        specs["resolution"] = "FHD"
    m = re.search(r"wi-?fi\s*(6e|6|7)", t)
    if m:
        specs["wifi"] = f"Wi-Fi {m.group(1).upper()}"
    if re.search(r"\b(online|double[- ]conversion)\b", t):
        specs["topology"] = "online"
    m = re.search(r"(\d{1,2})\s*(?:-?\s*)?bays?", t)
    if m:
        specs["bays"] = int(m.group(1))
    return specs


def extract_brand(text: str) -> str | None:
    t = fold(text)
    for b in BRANDS:
        if re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", t):
            return b
    return None


def _clean_description(text: str, span: tuple[int, int] | None) -> str:
    desc = text
    if span:
        desc = (text[: span[0]] + " " + text[span[1]:]).strip()
    desc = _BULLET.sub("", desc)
    desc = re.sub(rf"^\s*(?:x|×|\*)\s+", "", desc, flags=re.I)
    desc = re.sub(r"\b(?:qty|quantity)\s*[:=\-–]?\s*$", "", desc, flags=re.I)
    desc = re.sub(rf"^\s*{UNIT_WORDS}\s+(?:of\s+)?", "", desc, flags=re.I)
    desc = re.sub(r"^(?:supply of|provide|procurement of|procure|we require|we need|need|require)\s+", "", desc, flags=re.I)
    desc = re.sub(r"\(\s*\)", "", desc)
    desc = re.sub(r"\s+\b(?:for|of|with|x)\s*(?=\(|$)", " ", desc, flags=re.I)
    desc = re.sub(r"\s*[-–:,(]\s*\)?\s*$", "", desc)
    desc = re.sub(r"\s{2,}", " ", desc).strip(" -–:;,.")
    return desc[:1].upper() + desc[1:] if desc else desc


# --------------------------------------------------------------------------- tables


def _split_row(line: str) -> list[str] | None:
    if "|" in line:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
    elif "\t" in line:
        cells = [c.strip() for c in line.split("\t")]
    else:
        cells = [c.strip() for c in re.split(r"\s{3,}", line.strip())]
    cells = [c for c in cells if c != ""]
    return cells if len(cells) >= 2 else None


def extract_table_items(lines: list[str]) -> tuple[list[RawItem], set[int]]:
    """Find header-led tables and map their columns to description and quantity."""
    items: list[RawItem] = []
    consumed: set[int] = set()
    i = 0
    while i < len(lines):
        header = _split_row(lines[i])
        if not header or not _HEADER_HINT.search(" ".join(header)):
            i += 1
            continue
        lower = [h.lower() for h in header]
        qty_col = next((j for j, h in enumerate(lower) if re.search(r"\b(qty|quantity|nos|count)\b", h)), None)
        desc_col = next((j for j, h in enumerate(lower) if re.search(r"(description|product|requirement|equipment)", h) and j != qty_col), None)
        if desc_col is None:
            desc_col = next((j for j, h in enumerate(lower) if re.search(r"(item|specification)", h) and j != qty_col), None)
        spec_col = next((j for j, h in enumerate(lower) if re.search(r"(spec|minimum|technical)", h) and j not in (qty_col, desc_col)), None)
        unit_col = next((j for j, h in enumerate(lower) if re.fullmatch(r"(unit|uom|units)", h)), None)
        if qty_col is None or desc_col is None:
            i += 1
            continue
        consumed.add(i)
        j = i + 1
        while j < len(lines):
            if re.fullmatch(r"[\s|:\-+=]+", lines[j] or " "):
                consumed.add(j)
                j += 1
                continue
            row = _split_row(lines[j])
            if not row or len(row) < max(qty_col, desc_col) + 1:
                break
            m = re.search(r"\d[\d,]*", row[qty_col])
            if not m:
                break
            desc = row[desc_col]
            if spec_col is not None and spec_col < len(row):
                desc = f"{desc} {row[spec_col]}"
            unit = row[unit_col].lower() if unit_col is not None and unit_col < len(row) else None
            items.append(
                RawItem(
                    text=lines[j].strip(),
                    description=_clean_description(desc, None),
                    quantity=_to_int(m.group(0)),
                    quantity_source="table column",
                    unit=unit,
                    specs=extract_specs(desc),
                    brand=extract_brand(desc),
                )
            )
            consumed.add(j)
            j += 1
        i = j
    return items, consumed


def build_item(text: str) -> RawItem | None:
    text = _BULLET.sub("", text, count=1) if re.match(r"^\s*[-*•▪◦]", text) else text
    found = extract_quantity(text)
    if not found:
        return None
    qty, rule, span = found
    description = _clean_description(text, span)
    if len(re.findall(r"[A-Za-z]{3,}", description)) < 1:
        return None
    return RawItem(
        text=text.strip(),
        description=description,
        quantity=qty,
        quantity_source=rule,
        unit=extract_unit(text),
        specs=extract_specs(text),
        brand=extract_brand(text),
    )
