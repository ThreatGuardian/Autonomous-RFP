"""Tender-level understanding: obligations, key data, dates, evaluation method and eligibility.

All extraction is rule-based and returns the clause, section and page it came
from, so every value shown to a reviewer can be traced to the document.
Amounts follow Indian conventions (``Rs. 4,50,000``, ``Rs. 2.25 crore``,
``₹ 50 lakh``) and are normalised to rupees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents.messages import EligibilityCriterion, EvaluationMethod, KeyDate, TenderFact
from app.nlp.extractors import find_dates
from app.nlp.gazetteer import find_places
from app.nlp.text import fold, parse_number


@dataclass
class Unit:
    """One sentence, list item or table row, with where it came from."""

    text: str
    section: str | None
    kind: str  # section kind
    page: int | None
    clause: str | None
    source: str = "text"  # "text" | "table"
    table: int | None = None
    cells: list[str] | None = None
    header: list[str] | None = None


# --------------------------------------------------------------------------- amounts

_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹)\s*([\d][\d,]*(?:\.\d+)?)\s*(crores?|cr\b\.?|lakhs?|lacs?|million)?"
    r"|([\d][\d,]*(?:\.\d+)?)\s*(crores?|cr\b\.?|lakhs?|lacs?)", re.I)


def parse_inr(text: str) -> float | None:
    m = _AMOUNT.search(text)
    if not m:
        return None
    num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    value = float(num.replace(",", ""))
    unit = (unit or "").lower().rstrip(".")
    if unit.startswith(("crore", "cr")):
        value *= 1e7
    elif unit.startswith(("lakh", "lac")):
        value *= 1e5
    elif unit == "million":
        value *= 1e6
    return value


def fmt_inr(value: float) -> str:
    if value >= 1e7:
        return f"Rs. {value / 1e7:,.2f} crore"
    if value >= 1e5:
        return f"Rs. {value / 1e5:,.2f} lakh"
    return f"Rs. {value:,.0f}"


_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _num(token: str) -> int | None:
    token = token.lower()
    if token in _WORD_NUM:
        return _WORD_NUM[token]
    n = parse_number(token)
    return int(n) if n is not None else None


# --------------------------------------------------------------------------- modality

_PROHIBIT = re.compile(r"\b(?:shall|must|will|should|may)\s+not\b|\bnot (?:be )?(?:permitted|allowed|accepted|entertained|considered)\b|"
                       r"\bare not permitted\b|\bis not allowed\b|^\s*no\s+[a-z -]{1,40}\s+(?:will|shall) be (?:allowed|made|accepted|"
                       r"entertained|paid)", re.I)
_MANDATORY = re.compile(r"\b(shall|must|is required to|are required to|required to|will be required|mandatory|has to|have to|"
                        r"needs? to|should|is to be|are to be|will be (?:levied|forfeited|rejected|treated))\b", re.I)
_DESIRABLE = re.compile(r"\b(preferabl[ey]|preferred|desirable|preference will be given|is encouraged|optional|advantage|"
                        r"additional marks|may (?:also )?(?:offer|propose|quote|include))\b", re.I)
_BUYER = re.compile(r"^\s*(?:\(?[a-z0-9.]{1,6}\)?\s+)?(?:the\s+)?(purchaser|buyer|university|corporation|department|authority|institute|"
                    r"client|owner|employer|committee|tender inviting authority|competent authority|hospital|council|board|"
                    r"ministry|government|we|our)\b(?!'s)", re.I)
_INFO = re.compile(r"reserves? the right|at (?:its|their) (?:sole )?discretion|hereinafter referred|is (?:hereby )?invit|"
                   r"purchase preference|following (?:criteria|conditions)|are given below|as detailed below", re.I)


def modality(text: str) -> tuple[str, str]:
    """(modality, actor) of a clause: who must do what, and how strongly."""
    if _INFO.search(text):
        return "information", "buyer"
    head = " ".join(text.split()[:8])
    buyer = bool(_BUYER.match(text)) and "bidder" not in fold(head) and "supplier" not in fold(head)
    if _DESIRABLE.search(text):
        return "desirable", "buyer" if buyer and "preference" not in text.lower() else "bidder"
    if _PROHIBIT.search(text) or _MANDATORY.search(text):
        return ("mandatory", "buyer") if buyer else ("mandatory", "bidder")
    return "information", "buyer" if buyer else "bidder"


# --------------------------------------------------------------------------- categories

CATEGORY_LABELS = {
    "eligibility": "Eligibility", "technical": "Technical", "scope": "Scope of work", "delivery": "Delivery",
    "warranty": "Warranty & support", "commercial": "Commercial", "standards": "Standards & certification",
    "legal": "Legal & contractual", "submission": "Bid submission", "evaluation": "Evaluation",
}
_KIND_CATEGORY = {"eligibility": "eligibility", "technical": "technical", "boq": "technical", "conditions": "legal",
                  "evaluation": "evaluation", "instructions": "submission", "notice": "submission", "forms": "submission"}
_CLAUSE_CATEGORY = {"delivery": "delivery", "payment": "commercial", "warranty_support": "warranty", "compliance": "standards",
                    "submission": "submission", "evaluation": "evaluation", "scope": "scope", "line_item": "technical"}


def categorise(text: str, section_kind: str, clause_type: str, clause_conf: float, long_form: bool) -> str:
    t = fold(text)
    if long_form and section_kind in ("eligibility", "technical", "boq", "evaluation", "forms"):
        return _KIND_CATEGORY[section_kind]
    if re.search(r"liquidated damages|performance (?:security|bank guarantee)|\bemd\b|earnest money|price variation|"
                 r"prices? (?:shall|will) be firm|\bgst\b|advance (?:payment|bank guarantee)|\bpayment", t):
        return "commercial"
    if re.search(r"\biso\b|certif(?:ied|ication)|e-waste|energy star|epeat|\bbis\b|data protection|dpdp|gdpr", t):
        return "standards"
    if re.search(r"\bwarrant|helpdesk|help desk|complaints?\b|standby|response time|resolved within|responded to within|"
                 r"onsite engineer|resident engineer|support\b", t):
        return "warranty"
    if long_form and section_kind in ("instructions", "notice", "conditions"):
        return _KIND_CATEGORY[section_kind]
    if re.search(r"\bdeliver(?:y|ed)?\b|commission|install", t) and clause_type in ("delivery", "scope", "line_item"):
        return "delivery"
    if clause_conf >= 0.45:
        return _CLAUSE_CATEGORY.get(clause_type, "scope")
    return "scope"


# --------------------------------------------------------------------------- facts and dates

_TIME = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(hrs|hours|am|pm|a\.m\.|p\.m\.)?", re.I)
_DATE_ROLES: list[tuple[str, str, re.Pattern[str]]] = [
    ("queries", "Last date for queries", re.compile(r"quer(?:y|ies)|clarifications?", re.I)),
    ("prebid", "Pre-bid meeting", re.compile(r"pre-?(?:bid|proposal)\s+(?:meeting|conference)", re.I)),
    ("opening", "Bid opening", re.compile(r"\bopening\b", re.I)),
    ("submission", "Bid submission deadline", re.compile(
        r"(?:last|closing|end|due)\s+date.*(?:submission|receipt)|submission of (?:bids?|proposals?|offers?|tenders?)|"
        r"bid (?:submission )?(?:end|due|closing)|bids? due|proposals? (?:are )?due", re.I)),
    ("publication", "Date of publication", re.compile(r"publi(?:cation|shed)|date of issue|issue date|\bissued\b", re.I)),
]


def _pairs(units: list[Unit]) -> list[tuple[str, str, Unit]]:
    """(label, value, unit) pairs from key-data table rows and ``Label: value`` lines."""
    out: list[tuple[str, str, Unit]] = []
    for u in units:
        if u.source == "table" and u.cells:
            cells = [c for c in u.cells if c]
            if len(cells) >= 2 and not re.fullmatch(r"\d{1,3}\.?", cells[-2]):
                out.append((cells[-2], cells[-1], u))
            elif len(cells) >= 3:
                out.append((cells[-2], cells[-1], u))
        else:
            m = re.match(r"^([A-Z][A-Za-z ()./'&-]{2,60}?)\s*[:–-]\s+(.{2,200})$", u.text)
            if m:
                out.append((m.group(1), m.group(2), u))
    return out


def extract_key_dates(units: list[Unit], month_first: bool = False) -> list[KeyDate]:
    found: dict[str, KeyDate] = {}
    candidates = _pairs(units) + [(u.text, u.text, u) for u in units if u.source in ("text", "field")]
    for label, value, u in candidates:
        dates = find_dates(value, month_first)
        if not dates:
            continue
        for key, name, pattern in _DATE_ROLES:
            if key in found or not pattern.search(label if label != value else value[:max(0, dates[0][1]) + 1] or value):
                continue
            tm = _TIME.search(value[dates[0][2]:])
            time = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm and int(tm.group(1)) < 24 else None
            found[key] = KeyDate(key=key, label=name, date=dates[0][0].isoformat(), time=time, section=u.section,
                                 page=u.page, evidence=(f"{label}: {value}" if label != value else value)[:220])
            break
    order = [k for k, _, _ in _DATE_ROLES]
    return sorted(found.values(), key=lambda d: (d.date, order.index(d.key)))


_FACT_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("estimated_value", "Estimated value", re.compile(r"estimated (?:cost|value)|tender value|project value|approximate (?:cost|value)", re.I)),
    ("emd", "Earnest money (EMD)", re.compile(r"\bemd\b|earnest money|bid security", re.I)),
    ("tender_fee", "Tender fee", re.compile(r"tender (?:document )?fee|document fee|cost of (?:tender|bid) document", re.I)),
    ("bid_validity", "Bid validity", re.compile(r"(?:bid|proposal|offer|tender)s? validity|valid(?:ity)? for\b|shall remain valid", re.I)),
    ("completion", "Completion period", re.compile(r"completion period|period of completion|contract period|go live within", re.I)),
]


def extract_facts(units: list[Unit], reference: str | None) -> list[TenderFact]:
    facts: dict[str, TenderFact] = {}

    def add(key: str, label: str, value: str, u: Unit | None, amount: float | None = None, evidence: str | None = None) -> None:
        if key not in facts:
            facts[key] = TenderFact(key=key, label=label, value=value, amount=amount, section=u.section if u else None,
                                    page=u.page if u else None, evidence=(evidence or (u.text if u else None) or "")[:260] or None)

    if reference:
        add("reference", "Tender reference", reference, None)
    for label, value, u in _pairs(units):
        for key, name, pattern in _FACT_RULES:
            if pattern.search(label):
                amount = parse_inr(value) if key in ("estimated_value", "emd", "tender_fee") else None
                add(key, name, value, u, amount, f"{label}: {value}")
    body = [u for u in units if u.source in ("text", "field")]
    for u in body:
        t = u.text
        if "estimated_value" not in facts and re.search(r"estimated (?:cost|value)", t, re.I) and parse_inr(t):
            add("estimated_value", "Estimated value", fmt_inr(parse_inr(t)), u, parse_inr(t))
        if "emd" not in facts and re.search(r"\bemd\b|earnest money|bid security", t, re.I) and parse_inr(t):
            add("emd", "Earnest money (EMD)", fmt_inr(parse_inr(t)), u, parse_inr(t))
        m = re.search(r"(?:bids?|proposals?|offers?|tenders?)\s+(?:shall|will|must)\s+(?:remain\s+)?valid[^.]{0,40}?(\d{2,3})\s*days", t, re.I)
        if m and "bid_validity" not in facts:
            add("bid_validity", "Bid validity", f"{m.group(1)} days", u)
        m = re.search(r"performance (?:security|bank guarantee|guarantee)[^.]{0,80}?(\d{1,2}(?:\.\d+)?)\s*%", t, re.I)
        if m and "performance_security" not in facts:
            add("performance_security", "Performance security", f"{m.group(1)}% of contract value", u, float(m.group(1)))
        m = re.search(r"liquidated damages[^.]{0,80}?(\d(?:\.\d+)?)\s*%[^.]{0,80}?(week|day|month)[^.]{0,120}?maximum (?:of )?(\d{1,2})\s*%", t, re.I)
        if m and "ld" not in facts:
            add("ld", "Liquidated damages", f"{m.group(1)}% per {m.group(2).lower()}, capped at {m.group(3)}%", u,
                float(m.group(3)))
        if "payment" not in facts and re.search(r"\d{1,3}\s*%[^.]{0,60}(?:on|against|after)\s+(?:delivery|installation|go-live|"
                                                r"commissioning|acceptance|supply)", t, re.I):
            add("payment", "Payment milestones", t, u)
        if "msme" not in facts and re.search(r"\b(?:mses?|micro and small|msme|udyam|nsic)\b", t, re.I) and \
                re.search(r"exempt|preference", t, re.I):
            add("msme", "MSE benefits", "EMD/fee exemption" if re.search(r"exempt", t, re.I) else "Purchase preference", u)
        if "local_content" not in facts and re.search(r"make in india|local supplier|local content", t, re.I):
            add("local_content", "Make in India", "Local-content preference applies", u)
        if "submission_mode" not in facts:
            m = re.search(r"(gem portal|government e-?marketplace|cppp|eprocure\.gov\.in|mahatenders|e-?tendering portal|"
                          r"online through (?:the )?[^,;()]{3,60}?(?=\s*[(,;]|$)|sealed (?:envelope|cover)s?)", t, re.I)
            if m:
                add("submission_mode", "Submission", m.group(1)[:1].upper() + m.group(1)[1:], u)
        if "reverse_auction" not in facts and re.search(r"reverse auction", t, re.I):
            add("reverse_auction", "Reverse auction", "Price discovery by reverse auction", u)
    if "emd" in facts and facts["emd"].amount and "msme" in facts and facts["msme"].value.startswith("EMD"):
        facts["emd"].value = f"{fmt_inr(facts['emd'].amount)} (MSEs exempt)"
    order = ["reference", "estimated_value", "emd", "tender_fee", "bid_validity", "completion", "performance_security", "ld",
             "payment", "msme", "local_content", "submission_mode", "reverse_auction"]
    return sorted(facts.values(), key=lambda f: order.index(f.key) if f.key in order else 99)


# --------------------------------------------------------------------------- evaluation


def extract_evaluation(units: list[Unit]) -> EvaluationMethod:
    scoped = [u for u in units if u.kind == "evaluation"] or units
    text = " ".join(u.text for u in scoped)
    ev = EvaluationMethod()
    m = (re.search(r"(\d{2})\s*:\s*(\d{2})[^.]{0,80}?technical[^.]{0,30}financial", text, re.I)
         or re.search(r"technical[^.]{0,60}?(\d{2})\s*%[^.]{0,60}?financial[^.]{0,40}?(\d{2})\s*%", text, re.I))
    qcbs = re.search(r"\bqcbs\b|quality and cost based", text, re.I)
    if m or qcbs:
        ev.method = "QCBS"
        if m:
            ev.technical_weight, ev.financial_weight = float(m.group(1)), float(m.group(2))
        ev.evidence = next((u.text for u in scoped if re.search(r"qcbs|quality and cost|\d{2}\s*:\s*\d{2}", u.text, re.I)), None)
    elif re.search(r"\bl-?1\b|lowest (?:evaluated|compliant|quoted|priced|responsive|bid)", text, re.I):
        ev.method = "L1"
        ev.evidence = next((u.text for u in scoped if re.search(r"\bl-?1\b|lowest", u.text, re.I)), None)
    elif re.search(r"weight(?:age|ed)?|marks|points", text, re.I):
        ev.method = "Weighted"
    m = re.search(r"minimum (?:of )?(\d{2,3})\s*(?:marks|points|%)|(\d{2,3})\s*marks out of|qualifying (?:marks|score) of (\d{2,3})", text, re.I)
    if m:
        ev.min_technical_score = float(next(g for g in m.groups() if g))
    for u in scoped:
        if u.source == "table" and u.cells and u.header and re.search(r"marks|points|weight", " ".join(u.header), re.I):
            cells = [c for c in u.cells if c]
            if len(cells) >= 2 and re.fullmatch(r"\d{1,3}(?:\.\d+)?", cells[-1]):
                ev.criteria.append({"criterion": cells[-2], "marks": float(cells[-1])})
    if re.search(r"reverse auction", text, re.I):
        ev.notes.append("Final prices discovered by reverse auction.")
    if re.search(r"purchase preference", text, re.I):
        ev.notes.append("Purchase preference for MSEs / local suppliers applies.")
    if re.search(r"vary the quantit", text, re.I):
        ev.notes.append("Quantities may be varied at award at the quoted unit rates.")
    return ev


# --------------------------------------------------------------------------- eligibility

_ELIG_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("turnover", "Annual turnover", re.compile(r"turnover", re.I)),
    ("net_worth", "Net worth", re.compile(r"net worth", re.I)),
    ("similar_works", "Similar work experience", re.compile(r"\bsimilar\b[^.]{0,40}(?:works?|projects?|orders?|contracts?|suppl)", re.I)),
    ("supplied_quantity", "Supply volume", re.compile(r"supplied\s+(?:at least|a minimum of|not less than|minimum)?\s*\d[\d,]*\s+[a-z]", re.I)),
    ("certification", "Certifications", re.compile(r"\biso\b|\bcmmi\b|certificat(?:e|ion)s?\b(?![^.]{0,20}engineer)", re.I)),
    ("oem_authorisation", "OEM authorisation", re.compile(r"authori[sz]ation form|\bmaf\b|authori[sz]ed (?:partner|dealer|distributor|reseller)|"
                                                         r"original equipment manufacturer", re.I)),
    ("engineers", "Technical manpower", re.compile(r"\d+\s+(?:oem[- ])?(?:certified|qualified|trained)\s+(?:engineers|professionals|staff)", re.I)),
    ("local_content", "Make in India local content", re.compile(r"local supplier|local content|make in india", re.I)),
    ("local_presence", "Local office / service centre", re.compile(r"(?:office|service cent(?:re|er)|branch|support cent(?:re|er))\s+(?:or [a-z ]+ )?(?:in|at|within)\b", re.I)),
    ("blacklisting", "Not blacklisted", re.compile(r"blacklist|debar|ineligib\w*|banned|fraudulent", re.I)),
    ("experience_years", "Years in business", re.compile(
        r"(?:in (?:existence|operation|business)|operating|experience)[^.]{0,60}?(?:\d+|one|two|three|four|five|six|seven|eight|"
        r"nine|ten|fifteen|twenty)\s+years", re.I)),
    ("registration", "Registration", re.compile(r"registered under|companies act|partnership|gst registration|\bpan\b|incorporat", re.I)),
    ("msme", "MSE registration", re.compile(r"udyam|nsic|\bmses?\b|msme", re.I)),
]
_PRODUCT_WORDS = {"laptop": "laptop", "notebook": "laptop", "desktop": "desktop", "computer": "desktop", "pc": "desktop",
                  "server": "server", "switch": "network_switch", "printer": "printer", "monitor": "monitor",
                  "access point": "wireless", "ups": "power", "device": None}


def _window_years(t: str) -> int | None:
    m = re.search(r"(?:last|preceding|past|previous)\s+(\w+)\s+(?:financial\s+)?years", t, re.I)
    return _num(m.group(1)) if m else None


def _sectors(t: str) -> list[str]:
    out = []
    for key, pattern in (("education", r"universit|college|educational|school|academic"),
                         ("government", r"government|\bpsu\b|public sector|municipal|state|central"),
                         ("healthcare", r"hospital|health")):
        if re.search(pattern, t, re.I):
            out.append(key)
    return out


def parse_criterion(kind: str, text: str) -> dict[str, Any]:
    t = text
    p: dict[str, Any] = {}
    if kind == "turnover":
        p["amount"] = parse_inr(t)
        p["years"] = _window_years(t) or 3
        p["basis"] = "each year" if re.search(r"each (?:of the )?(?:last|preceding|financial)", t, re.I) else "average"
        fys = re.findall(r"20(\d{2})-(\d{2})", t)
        if fys:
            p["financial_years"] = [f"20{a}-{b}" for a, b in fys]
        m = re.search(r"of which[^.]*?(\d{1,3})\s*%[^.]*?(?:from|in)\s+([a-z ]{3,40})", t, re.I)
        if m:
            p["segment_share_pct"], p["segment"] = float(m.group(1)), m.group(2).strip()
        else:
            m = re.search(r"from\s+((?:it|ict)?\s*[a-z ]{3,40}?(?:supply|business|services|integration))", t, re.I)
            if m:
                p["segment"] = m.group(1).strip()
    elif kind == "net_worth":
        p["positive"] = bool(re.search(r"positive", t, re.I))
        p["amount"] = parse_inr(t)
    elif kind == "similar_works":
        options = []
        for m in re.finditer(r"\b(one|two|three|four|five|\d)\s+(?:similar\s+)?(?:completed\s+)?(?:works?|projects?|orders?|contracts?|"
                             r"supplies)[^;]*?(?:not less than|at least|minimum of|value of|each costing|costing)\s*"
                             r"(?:(\d{1,3})\s*%|((?:rs\.?|inr|₹)\s*[\d][\d,]*(?:\.\d+)?\s*(?:crores?|cr\b\.?|lakhs?|lacs?)?))", t, re.I):
            count = _num(m.group(1))
            if m.group(2):
                options.append({"count": count, "pct_of_estimate": float(m.group(2))})
            else:
                options.append({"count": count, "value": parse_inr(m.group(3))})
        p["options"] = options
        p["years"] = _window_years(t) or 7
        p["sectors"] = _sectors(t)
    elif kind == "supplied_quantity":
        m = re.search(r"supplied\s+(?:at least|a minimum of|not less than|minimum)?\s*(\d[\d,]*)\s+([a-z ]{3,30})", t, re.I)
        if m:
            p["quantity"] = int(m.group(1).replace(",", ""))
            word = m.group(2).lower()
            p["item"] = word.split(" to ")[0].strip()
            p["category"] = next((c for w, c in _PRODUCT_WORDS.items() if w in word), None)
        p["years"] = _window_years(t) or 3
        p["sectors"] = _sectors(t)
    elif kind == "certification":
        stds = []
        for m in re.finditer(r"iso\s*/?\s*(?:iec\s*)?(\d{4,5}(?:-\d)?)(?::\s*(\d{4}))?|cmmi\s*(?:level|l|ml)?\s*(\d)", t, re.I):
            if m.group(1):
                stds.append(f"ISO {m.group(1)}")
            else:
                stds.append(f"CMMI Level {m.group(3)}")
        p["standards"] = list(dict.fromkeys(stds))
    elif kind == "engineers":
        m = re.search(r"(\d+)\s+(?:oem[- ])?(?:certified|qualified|trained)", t, re.I)
        p["count"] = int(m.group(1)) if m else None
    elif kind == "local_presence":
        places = find_places(t)
        p["places"] = list(dict.fromkeys(pl.region or pl.alias.title() for pl in places if pl.country == "IN"))
        m = re.search(r"within\s+(\d+)\s*km", t, re.I)
        if m:
            p["radius_km"] = int(m.group(1))
    elif kind == "experience_years":
        m = re.search(r"(?:at least|minimum(?: of)?|not less than|min\.?)?\s*(\w+)\s+years", t, re.I)
        p["years"] = _num(m.group(1)) if m else None
    return p


def extract_eligibility(units: list[Unit], long_form: bool) -> list[EligibilityCriterion]:
    """Criteria from eligibility / pre-qualification sections (tables and clauses)."""
    scoped = [u for u in units if u.kind == "eligibility"] if long_form else []
    out: list[EligibilityCriterion] = []
    for u in scoped:
        text = u.text
        documents = None
        if u.source == "table" and u.cells and u.header:
            header = [h.lower() for h in u.header]
            ci = next((i for i, h in enumerate(header) if re.search(r"criteri|requirement|eligib|condition|particular", h)), None)
            di = next((i for i, h in enumerate(header) if re.search(r"document|proof|evidence|submitted", h)), None)
            if ci is None or ci >= len(u.cells) or u.cells == u.header:
                continue
            text = u.cells[ci]
            documents = u.cells[di] if di is not None and di < len(u.cells) else None
        if len(text.split()) < 5 or not re.search(r"\b(shall|must|should|required|minimum|at least|not less than|only)\b", text, re.I):
            continue
        if re.search(r"following\s+(?:[\w-]+\s+)?(?:criteria|conditions)|criteria (?:given|listed) below", text, re.I):
            continue
        kind, label = "other", "Other requirement"
        for k, name, pattern in _ELIG_RULES:
            if pattern.search(text):
                kind, label = k, name
                break
        out.append(EligibilityCriterion(
            id=f"EC{len(out) + 1:02d}", kind=kind, label=label, text=text, clause=u.clause, section=u.section, page=u.page,
            params=parse_criterion(kind, text), documents=documents,
        ))
    return out
