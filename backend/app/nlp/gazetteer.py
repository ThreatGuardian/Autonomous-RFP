"""Country, region and currency lookup built from ``countries.json``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.db.seed import load_json
from app.nlp.text import fold


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    currency: str
    eu: bool
    aliases: tuple[str, ...]
    regions: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class PlaceMention:
    country: str
    region: str | None
    alias: str
    start: int


@lru_cache
def countries() -> dict[str, Country]:
    out = {}
    for row in load_json("countries.json"):
        out[row["code"]] = Country(
            code=row["code"],
            name=row["name"],
            currency=row["currency"],
            eu=row["eu"],
            aliases=tuple(fold(a) for a in row["aliases"]),
            regions={r: tuple(fold(a) for a in al) for r, al in row["regions"].items()},
        )
    return out


@lru_cache
def _alias_patterns() -> list[tuple[re.Pattern[str], str, str | None, str]]:
    pats: list[tuple[re.Pattern[str], str, str | None, str]] = []
    for c in countries().values():
        for alias in c.aliases:
            pats.append((re.compile(rf"(?<![\w.]){re.escape(alias)}(?![\w])"), c.code, None, alias))
        for region, aliases in c.regions.items():
            for alias in aliases:
                pats.append((re.compile(rf"(?<![\w.]){re.escape(alias)}(?![\w])"), c.code, region, alias))
    # Longest aliases first so "new south wales" beats "wales", "new delhi" beats "delhi".
    pats.sort(key=lambda p: -len(p[3]))
    return pats


def find_places(text: str) -> list[PlaceMention]:
    folded = fold(text)
    taken: list[tuple[int, int]] = []
    found: list[PlaceMention] = []
    for pattern, code, region, alias in _alias_patterns():
        for m in pattern.finditer(folded):
            if any(s <= m.start() < e or s < m.end() <= e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append(PlaceMention(code, region, alias, m.start()))
    return sorted(found, key=lambda p: p.start)


def country_currency(code: str | None) -> str | None:
    c = countries().get(code or "")
    return c.currency if c else None
