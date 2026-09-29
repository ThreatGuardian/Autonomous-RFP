"""Rule-based extractors for RFP header entities and commercial terms."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from app.nlp.gazetteer import countries, find_places
from app.nlp.text import fold, parse_number

# --------------------------------------------------------------------------- generic helpers

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,}\d")
ORG_SUFFIX_RE = re.compile(
    r"\b(?:Pvt\.?\s*Ltd\.?|Private Limited|Limited|Ltd\.?|LLC|L\.L\.C\.|Inc\.?|Incorporated|Corp\.?|Corporation|GmbH|AG|"
    r"S\.A\.|SAS|B\.V\.|Pte\.?\s*Ltd\.?|Pty\.?\s*Ltd\.?|PLC|LLP|University|Institute|College|School District|"
    r"Hospital|Health(?: Systems)?|Medical Group|Council|Authority|Municipal(?:ity)?|Ministry|Department|Group|Services|Partners)\b",
    re.IGNORECASE,
)
LABELLED = {
    "client": r"(?:issued by|issuing (?:organi[sz]ation|authority)|organi[sz]ation(?: name)?|client|buyer|purchaser|"
              r"customer|company(?: name)?|procuring entity|from|on behalf of)",
    "contact": r"(?:contact(?: person)?|attn\.?|attention|point of contact|procurement officer|contact name)",
    "reference": r"(?:rfp|rfq|rft|tender|bid|enquiry|inquiry)\s*(?:no\.?|number|ref(?:erence)?\.?|id|#)",
    "title": r"(?:subject|title|re|project(?: name)?)",
    "tax_id": r"(?:gstin|gst no\.?|vat(?: reg(?:istration)?)?(?: no\.?| number| id)?|trn|abn|uen|ein|tax id)",
    "address": r"(?:delivery (?:address|location|site)|ship(?:ping)? to|deliver to|consignee address|site address|address)",
}


def labelled_value(text: str, key: str) -> str | None:
    """Value of the first ``Label: value`` line for a semantic label."""
    pattern = re.compile(
        rf"(?:^|(?<=[.;] ))\s*(?:[-*•]\s*)?{LABELLED[key]}\s*[:\-–]\s*(.+)$", re.IGNORECASE | re.MULTILINE
    )
    m = pattern.search(text)
    return m.group(1).strip().rstrip(".") if m else None


# --------------------------------------------------------------------------- client


def extract_client_name(text: str) -> tuple[str | None, str]:
    value = labelled_value(text, "client")
    if value:
        value = EMAIL_RE.sub("", value).split(",")[0].strip(" -")
        if 2 < len(value) < 120:
            return value, "labelled field"
    # Otherwise the first line in the document header carrying an organisation suffix.
    for line in text.splitlines()[:25]:
        line = line.strip()
        if 3 < len(line) < 110 and ORG_SUFFIX_RE.search(line) and not re.search(r"request for|rfp|rfq|tender", line, re.I):
            return line.rstrip(".,"), "organisation header line"
    return None, "not found"


def extract_contact(text: str) -> dict[str, str | None]:
    contact = labelled_value(text, "contact")
    name = None
    if contact:
        name = EMAIL_RE.sub("", contact).split(",")[0].strip(" -()") or None
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    return {"name": name, "email": email.group(0) if email else None, "phone": phone.group(0).strip() if phone else None}


def extract_title(text: str) -> str:
    value = labelled_value(text, "title")
    if value and len(value) > 6:
        return value[:200]
    m = re.search(r"(request for (?:proposal|quotation|quote|tender|bid)s?|rf[pqt])\s*(?:for|:|-|–)\s*(.+)", text, re.I)
    if m:
        return m.group(2).strip().split("\n")[0].rstrip(".")[:200]
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return "Untitled request"


def extract_reference(text: str) -> str | None:
    m = re.search(rf"{LABELLED['reference']}\s*[:\-–]?\s*([A-Z0-9][A-Z0-9/\-_.]{{2,40}})", text, re.I) or re.search(
        r"^\s*(?:our\s+)?ref(?:erence)?\.?\s*(?:no\.?)?\s*[:#]\s*([A-Z0-9][A-Z0-9/\-_.]{2,40})", text, re.I | re.M
    )
    return m.group(1).rstrip(".") if m else None


def extract_tax_id(text: str) -> str | None:
    m = re.search(rf"{LABELLED['tax_id']}\s*[:\-–]\s*([A-Z0-9 ]{{6,24}})", text, re.I)
    return m.group(1).strip() if m else None


# --------------------------------------------------------------------------- location


@dataclass
class LocationResult:
    country: str | None
    region: str | None
    evidence: str
    delivery_location: str | None


def extract_location(text: str) -> LocationResult:
    """Resolve the delivery jurisdiction.

    Mentions inside a delivery/address field dominate; otherwise the most
    frequently mentioned country (region mentions vote for their country) wins,
    with earlier mentions breaking ties.
    """
    address = labelled_value(text, "address")
    if address:
        places = find_places(address)
        if places:
            best = next((p for p in places if p.region), places[0])
            region = best.region or next((p.region for p in places if p.country == best.country and p.region), None)
            return LocationResult(best.country, region, f"delivery address mentions '{best.alias}'", address)
    places = find_places(text)
    if not places:
        return LocationResult(None, None, "no place names found", address)
    votes: Counter[str] = Counter(p.country for p in places)
    first_seen = {}
    for p in places:
        first_seen.setdefault(p.country, p.start)
    country = max(votes, key=lambda c: (votes[c], -first_seen[c]))
    regions = Counter(p.region for p in places if p.country == country and p.region)
    region = regions.most_common(1)[0][0] if regions else None
    return LocationResult(country, region, f"{votes[country]} mention(s) of {countries()[country].name}", address)


# --------------------------------------------------------------------------- currency

_CURRENCY_WORDS = {
    "inr": "INR", "rupee": "INR", "rupees": "INR", "rs": "INR", "₹": "INR",
    "usd": "USD", "us dollar": "USD", "us dollars": "USD", "us$": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
    "gbp": "GBP", "pound sterling": "GBP", "pounds sterling": "GBP", "£": "GBP",
    "aed": "AED", "dirham": "AED", "dirhams": "AED", "sgd": "SGD", "s$": "SGD", "singapore dollar": "SGD",
    "aud": "AUD", "a$": "AUD", "australian dollar": "AUD", "cad": "CAD", "c$": "CAD", "canadian dollar": "CAD",
    "jpy": "JPY", "yen": "JPY", "sar": "SAR", "riyal": "SAR", "chf": "CHF", "swiss franc": "CHF",
    "nzd": "NZD", "zar": "ZAR", "rand": "ZAR", "sek": "SEK", "nok": "NOK", "dkk": "DKK", "qar": "QAR",
    "omr": "OMR", "bhd": "BHD", "kes": "KES", "lkr": "LKR", "myr": "MYR", "ringgit": "MYR", "pln": "PLN",
}
_DOLLAR_COUNTRIES = {"US": "USD", "SG": "SGD", "AU": "AUD", "CA": "CAD", "NZ": "NZD"}
_CUR_RE = re.compile(
    r"(?<![\w])(" + "|".join(re.escape(k) for k in sorted(_CURRENCY_WORDS, key=len, reverse=True)) + r")(?![\w])"
)
_CUR_CONTEXT = re.compile(r"\b(quot\w*|price\w*|currency|denominat\w*|invoice\w*|commercial offer|bid\w* in)\b", re.I)


def extract_currency(text: str, country: str | None) -> tuple[str | None, str | None]:
    """Explicit currency instruction, preferring sentences about pricing/quoting."""
    best: tuple[int, str, str] | None = None
    for line in re.split(r"(?<=[.!?])\s+|\n", text):
        folded = fold(line)
        in_context = bool(_CUR_CONTEXT.search(line))
        for m in _CUR_RE.finditer(folded):
            code = _CURRENCY_WORDS[m.group(1)]
            weight = 2 if in_context else 1
            if best is None or weight > best[0]:
                best = (weight, code, line.strip()[:160])
        if "$" in line and not _CUR_RE.search(folded):
            code = _DOLLAR_COUNTRIES.get(country or "", "USD")
            weight = 2 if in_context else 1
            if best is None or weight > best[0]:
                best = (weight, code, line.strip()[:160])
    if best and best[0] == 2:
        return best[1], best[2]
    return None, None


# --------------------------------------------------------------------------- dates

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"), "dMy"),
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), "Mdy"),
    (re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"), "numeric"),
]
_DATE_ROLES = [
    ("due", re.compile(
        r"(submi\w*|closing|deadline|due|last date|no later than|received by|(?:sent|send|returned|e-?mailed) to|"
        r"(?:responses?|bids?|quotations?|proposals?|offers?)\b(?! will be (?:scored|evaluated)))", re.I)),
    ("delivery", re.compile(r"(deliver\w*|install\w*|arriv\w*|go[- ]live|commission\w*)", re.I)),
    ("issued", re.compile(r"(issue\w*|dated|date of (?:rfp|release)|published|release date)", re.I)),
]


def _mk_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str, month_first: bool = False) -> list[tuple[date, int, int]]:
    out = []
    for pattern, kind in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            dt = None
            if kind == "ymd":
                dt = _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif kind == "dMy":
                mon = _MONTHS.get(m.group(2)[:3].lower())
                dt = _mk_date(int(m.group(3)), mon, int(m.group(1))) if mon else None
            elif kind == "Mdy":
                mon = _MONTHS.get(m.group(1)[:3].lower())
                dt = _mk_date(int(m.group(3)), mon, int(m.group(2))) if mon else None
            else:
                a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if a > 12:
                    month_first_here = False
                elif b > 12:
                    month_first_here = True
                else:
                    month_first_here = month_first
                dt = _mk_date(y, a, b) if month_first_here else _mk_date(y, b, a)
            if dt and not any(s <= m.start() < e for _, s, e in out):
                out.append((dt, m.start(), m.end()))
    return sorted(out, key=lambda t: t[1])


def extract_dates(text: str, month_first: bool = False) -> dict[str, str | None]:
    roles: dict[str, str | None] = {"due": None, "delivery": None, "issued": None}
    for dt, start, _ in find_dates(text, month_first):
        line_start = text.rfind("\n", 0, start) + 1
        context = text[max(line_start, start - 90): start]
        for role, pattern in _DATE_ROLES:
            if roles[role] is None and pattern.search(context):
                roles[role] = dt.isoformat()
                break
    return roles


# --------------------------------------------------------------------------- commercial terms

INCOTERMS = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP")
_NUM = r"(\d+|[a-z]+(?:[- ][a-z]+)?)"


def _duration_days(value: str, unit: str) -> int | None:
    n = parse_number(value)
    if n is None:
        return None
    unit = unit.lower()
    if unit.startswith("week"):
        return int(n * 7)
    if unit.startswith("month"):
        return int(n * 30)
    return int(n)


def extract_terms(text: str) -> dict[str, object]:
    folded = fold(text)
    terms: dict[str, object] = {}
    m = re.search(r"\b(" + "|".join(INCOTERMS) + r")\b", text)
    if m:
        terms["incoterm"] = m.group(1)
    elif re.search(r"delivered duty paid", folded):
        terms["incoterm"] = "DDP"

    m = re.search(rf"deliver\w*[^.\n]{{0,60}}?within\s+{_NUM}\s+(business days|working days|days|weeks|months)", folded)
    if not m:
        m = re.search(rf"lead time[^.\n]{{0,40}}?{_NUM}\s+(business days|working days|days|weeks|months)", folded)
    if m:
        terms["delivery_days"] = _duration_days(m.group(1), m.group(2))

    m = re.search(rf"(?:net\s+{_NUM}\b)|(?:payment[^.\n]{{0,60}}?within\s+{_NUM}\s+days)|(?:{_NUM}\s+days\s+(?:of|from|after)\s+(?:receipt of\s+)?(?:a\s+)?(?:valid\s+)?invoice)", folded)
    if m:
        value = next(g for g in m.groups() if g)
        n = parse_number(value)
        if n:
            terms["payment_days"] = int(n)

    m = re.search(r"(\d{1,3})\s*%\s*(?:advance|upfront|in advance)", folded)
    if m:
        terms["advance_pct"] = float(m.group(1))
    elif re.search(r"no advance", folded):
        terms["advance_pct"] = 0.0

    m = re.search(rf"(?:minimum|at least|min\.?)?\s*{_NUM}[- ]?(years?|months?|yrs?)[^.\n]{{0,30}}?warranty", folded) or \
        re.search(rf"warranty[^.\n]{{0,40}}?(?:of|for|minimum|at least)\s+{_NUM}\s*(years?|months?|yrs?)", folded)
    if m:
        n = parse_number(m.group(1))
        if n:
            terms["warranty_months_required"] = int(n * 12 if m.group(2).startswith("y") else n)

    m = re.search(r"price[^.\n]{0,20}?\(?\s*(\d{1,3})\s*%", folded) or re.search(r"(\d{1,3})\s*%\s*(?:weight\w*\s*)?(?:for|on)\s*price", folded)
    if m:
        terms["price_weight_pct"] = float(m.group(1))
    if re.search(r"lowest (?:compliant |evaluated |priced )?(?:bid|bidder|offer|quotation)|\bl1\b", folded):
        terms["lowest_price_award"] = True
    return terms


# --------------------------------------------------------------------------- segment

_SEGMENT_CUES = [
    ("education", r"\b(universit\w*|college|school|institute of technology|academy|campus|students?)\b"),
    ("healthcare", r"\b(hospital|health\w*|medical|clinic\w*|patients?)\b"),
    ("public", r"\b(municipal\w*|city of|council|ministry|government|authority|public sector|department of|district)\b"),
    ("enterprise", r"\b(enterprise|group|corporation|multinational|global operations|\d{4,}\s+employees)\b"),
]


def infer_segment(text: str, client_name: str | None) -> tuple[str, str]:
    """Segment from the client name first, then document cues."""
    for source, haystack in (("client name", client_name or ""), ("document cues", text[:4000])):
        for segment, pattern in _SEGMENT_CUES:
            if re.search(pattern, haystack, re.I):
                return segment, source
    return "smb", "default"


_HEADER_FIELD = re.compile(
    r"^\s*(?:date(?: of issue)?|dated|issued(?: on)?|release date|subject|title|re|contact(?: person)?|attn\.?|"
    r"from|to|gstin|trn|vat(?: id| no\.?)?|abn|uen|tel(?:ephone)?|phone|e-?mail|page \d+|"
    + LABELLED["reference"] + r")\s*[:\-–#]", re.IGNORECASE,
)
_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[A-Z]\.|[IVX]+\.)?\s*[A-Za-z][\w &/,()'-]{0,60}$")


_ADDRESS = re.compile(
    r"\b(road|rd\.|street|st\.|avenue|ave\.?|lane|boulevard|blvd|floor|suite|building|tower [a-z]|stra(?:ss|ß)e|"
    r"industriestra\w+|free zone|p\.?\s?o\.? box|survey no\.?|plot no\.?|sector \d+)\b",
    re.IGNORECASE,
)
_POSTCODE = re.compile(r"\b(?:\d{6}|\d{5}(?:-\d{4})?|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}|\d{4})\b")
_TITLE_LINE = re.compile(r"\b(request for (?:proposal|quotation|quote|tender|bid)s?|^rf[pqt]\b)", re.IGNORECASE)


def is_header_field(line: str) -> bool:
    """``Label: value`` lines from the document header (dates, references, contacts)."""
    return bool(_HEADER_FIELD.match(line))


def is_address_line(line: str) -> bool:
    return bool(_ADDRESS.search(line) and (_POSTCODE.search(line) or "," in line) and len(line) < 140)


def is_title_line(line: str) -> bool:
    return bool(_TITLE_LINE.search(line)) and len(line) < 160


def is_heading(line: str) -> bool:
    """Short title-like lines without sentence punctuation ("3. Delivery and installation")."""
    stripped = line.strip()
    if stripped.endswith((".", ";", "?", "!")) or len(stripped.split()) > 7:
        return False
    return bool(_HEADING.match(stripped))
