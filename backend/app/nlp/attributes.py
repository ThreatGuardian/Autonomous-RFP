"""Check one technical-specification row against a product's catalogue attributes.

Spec tables in tenders mix measurable limits ("Minimum 1000 DPI", "Minimum 30 mm
drivers", "Minimum 6 hours") with descriptive requirements ("Noise-cancelling
boom microphone", "HDMI and VGA", "Spill resistant, low-profile keys").

* **Measurable limits** are parsed into (value, unit, direction) and compared with
  the product attribute for that unit, when the product records it.
* **Descriptive requirements** are split into conjuncts (",", "and") and
  alternatives ("or"); a conjunct is met when every significant word of one
  alternative appears in the product's specifications, description or keywords.

The result is ``True`` (met), ``False`` (a measurable limit is not met) or
``None`` (the catalogue does not say), with a short explanation.
"""

from __future__ import annotations

import re
from app.nlp.text import fold

# (unit pattern, product attribute, hint that must appear in the row for the rule to apply)
_MEASURES: list[tuple[str, str, str | None, str]] = [
    (r"dpi", "dpi", None, "DPI"),
    (r"fps", "fps", None, "fps"),
    (r"mm\b", "driver_mm", r"driver", "mm drivers"),
    (r"m\b", "cable_m", r"cable", "m cable"),
    (r"hours?|hrs", "battery_hours", r"battery", "hours battery"),
    (r"min(?:ute)?s?\b", "backup_minutes", r"backup", "minutes backup"),
    (r"(?:indian\s+)?(?:sockets?|outlets?)", "outlets", None, "outlets"),
    (r"usb\s*ports?", "usb_ports", None, "USB ports"),
]
_MAX = re.compile(r"\b(?:max(?:imum)?|not more than|up to|at most)\b")
_DROP = re.compile(r"\b(?:or (?:higher|above|better|equivalent|more)|minimum|min\.?|at least|not less than|"
                   r"pre-?installed|supported|with|the|for|of|a|an|in|to|including|type|design)\b")
_SYN = {"noise-cancelling": "noise cancelling", "noise-canceling": "noise cancelling", "anti-glare": "anti glare",
        "line interactive": "line interactive", "pci express": "pcie", "pci-e": "pcie", "display port": "displayport",
        "low-profile": "low profile", "plug-and-play": "plug and play", "full-size": "full size", "over-ear": "over ear",
        "on-ear": "on ear", "3.5mm": "3.5 mm"}


def _norm(text: str) -> str:
    t = fold(text)
    for a, b in _SYN.items():
        t = t.replace(a, b)
    return t


def _stem(w: str) -> str:
    w = {"laboratory": "lab", "laboratories": "lab", "labs": "lab"}.get(w, w)
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z][a-z0-9.+]*|\d+[a-z]+", _norm(text).replace("-", " ")) if len(w) > 1}


def product_blob(product) -> set[str]:
    specs = product.specs or {}
    parts = [product.name, product.brand, product.description, " ".join(product.keywords or [])]
    for k, v in specs.items():
        parts.append(k.replace("_", " "))
        parts.append(str(v) if not isinstance(v, bool) else (k.replace("_", " ") if v else ""))
    return _tokens(" ".join(parts))


def check(param: str, want: str, product) -> tuple[bool | None, str]:
    """Return (met, explanation) for one spec row, or (None, reason) when the catalogue is silent."""
    specs = product.specs or {}
    row = _norm(f"{param} {want}")
    measured: list[str] = []
    for pattern, key, hint, label in _MEASURES:
        m = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{pattern})", row)
        if not m or (hint and not re.search(hint, row)):
            continue
        need = float(m.group(1))
        have = specs.get(key)
        if not isinstance(have, (int, float)) or isinstance(have, bool):
            return None, f"{label} not recorded in the catalogue"
        ok = have <= need if _MAX.search(row) else have >= need
        if not ok:
            return False, f"{have:g} {label} against {need:g} required"
        measured.append(f"{have:g} {label} meets {need:g}")
    text = re.sub(r"\(.*?\)", " ", _norm(want))
    # Purpose phrases ("for the language laboratory", "for one desktop") describe use, not the product.
    text = re.sub(r"\bfor\b[^,;]*", " ", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:dpi|fps|mm|m|hours?|hrs|minutes?|mins?|w|va|gb|tb)\b", " ", text)
    text = _DROP.sub(" ", text)
    blob = product_blob(product)
    missing: list[str] = []
    wanted: set[str] = set()
    for conjunct in re.split(r",|;|\band\b|&", text):
        options = [o for o in re.split(r"\bor\b|/", conjunct) if _tokens(o)]
        if not options:
            continue
        hit = next((o for o in options if _tokens(o) <= blob), None)
        if hit is None:
            missing.append(" or ".join(o.strip() for o in options))
        else:
            wanted |= _tokens(hit)
    if missing:
        return None, f"catalogue data does not mention {missing[0]}"
    if not measured and not _tokens(text):
        return None, "nothing to compare"
    # Quote the catalogue attributes that carry the matched words, so the reader sees the evidence.
    shown = [str(v) for k, v in specs.items() if isinstance(v, str) and _tokens(v) & wanted]
    return True, "; ".join(measured + shown[:2]) if (measured or shown) else "matches catalogue data"
