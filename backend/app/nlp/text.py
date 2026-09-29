"""Text normalisation, tokenisation and light stemming.

Everything here is deterministic and dependency-free so the same analyser can
be shared by the retrieval index, the trained classifiers and the parser.
"""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """
    a about above after again all also am an and any are as at be because been before being below between both
    but by can could did do does doing down during each few for from further had has have having he her here
    hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now
    of off on once only or other our ours ourselves out over own same she should so some such than that the
    their theirs them themselves then there these they this those through to too under until up very was we
    were what when where which while who whom why will with would you your yours yourself yourselves shall
    may must please kindly herewith hereby per via etc
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'])|\n{2,}|\n(?=\s*(?:[-*•▪◦]|\d+[.)])\s)")

_TRANSLATE = str.maketrans(
    {
        "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
        "−": "-", " ": " ", " ": " ", " ": " ", "×": "x", "•": "•",
    }
)


def normalize(text: str) -> str:
    """Unicode-normalise, unify punctuation and collapse horizontal whitespace."""
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r" *\n *", "\n", text).strip()


def fold(text: str) -> str:
    """Lower-case and strip accents (``Präzision`` -> ``prazision``)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# A compact suffix stripper in the spirit of Porter step 1: enough to conflate
# plural and verbal forms common in procurement text without over-stemming
# model numbers or units.
_SUFFIXES = (
    ("ational", "ate"), ("ization", "ize"), ("ations", "ate"), ("ation", "ate"), ("iveness", "ive"),
    ("fulness", "ful"), ("ousness", "ous"), ("ments", "ment"), ("ities", "ity"), ("ness", ""),
    ("ings", ""), ("ing", ""), ("ies", "y"), ("sses", "ss"), ("ed", ""), ("es", ""), ("s", ""),
)


def stem(token: str) -> str:
    if len(token) <= 3 or any(ch.isdigit() for ch in token):
        return token
    for suffix, repl in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            base = token[: -len(suffix)] + repl
            if suffix == "s" and token.endswith(("ss", "us", "is")):
                return token
            if suffix in ("ing", "ed") and len(base) >= 4 and base[-1] == base[-2] and base[-1] not in "lsz":
                base = base[:-1]  # shipping -> ship, planned -> plan
            return base
    return token


def tokenize(text: str, *, drop_stopwords: bool = True, stemmed: bool = False) -> list[str]:
    tokens = [t for t in _TOKEN_RE.findall(fold(text))]
    # Split glued number-unit tokens so "16gb" and "16 gb" index identically.
    expanded: list[str] = []
    for tok in tokens:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]{1,3})", tok)
        if m and m.group(2) in {"gb", "tb", "mb", "w", "va", "kva", "m", "mm", "in", "u", "hz", "ghz"}:
            expanded.extend([m.group(1), m.group(2)])
        elif "/" in tok or "-" in tok:
            # Keep the compound ("wi-fi", "iso/iec") and its parts ("iso", "iec").
            expanded.append(tok)
            expanded.extend(p for p in re.split(r"[/-]", tok) if p)
        else:
            expanded.append(tok)
    if drop_stopwords:
        expanded = [t for t in expanded if t not in STOPWORDS]
    if stemmed:
        expanded = [stem(t) for t in expanded]
    return expanded


def analyze(text: str) -> list[str]:
    """Analyser used by retrieval and classifiers: folded, stop-worded, stemmed."""
    return tokenize(text, drop_stopwords=True, stemmed=True)


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(normalize(text))
    out = []
    for part in parts:
        part = part.strip(" \n-*•▪◦")
        if len(part) >= 3:
            out.append(re.sub(r"\s*\n\s*", " ", part))
    return out


# --------------------------------------------------------------------------- numbers

_UNITS = {
    "zero": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100_000, "lakhs": 100_000}
_SPECIAL = {"dozen": 12, "score": 20, "pair": 2, "couple": 2}

NUMBER_WORD_RE = re.compile(
    r"\b(?:(?:"
    + "|".join(sorted(list(_UNITS) + list(_TENS) + list(_SCALES) + list(_SPECIAL), key=len, reverse=True))
    + r")(?:[\s-]+(?:and[\s-]+)?)?)+\b",
    re.IGNORECASE,
)


def words_to_number(phrase: str) -> int | None:
    """Parse English number words: ``"one hundred and twenty-five"`` -> 125."""
    words = [w for w in re.split(r"[\s-]+", phrase.lower().strip()) if w and w != "and"]
    if not words or all(w in {"a", "an"} for w in words):
        return None
    total, current, seen = 0, 0, False
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w in _SPECIAL:
            current = max(current, 1) * _SPECIAL[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w in _SCALES:
            total += max(current, 1) * _SCALES[w]
            current = 0
        else:
            return None
        seen = True
    return total + current if seen else None


def parse_number(text: str) -> float | None:
    """Parse ``"1,250"``, ``"1.5k"``, ``"2 lakh"`` or number words."""
    t = text.strip().lower().replace(",", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|m|million)?", t)
    if m:
        value = float(m.group(1))
        mult = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "m": 1e6, "million": 1e6}.get(m.group(2) or "", 1)
        return value * mult
    n = words_to_number(t)
    return float(n) if n is not None else None
