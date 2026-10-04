"""Proposal Drafting Agent — the language-model step.

Claude writes the cover letter, executive summary and highlights from client-safe
facts only (the scope, totals, dates and included services) and from knowledge-base
passages retrieved for this request. Internal figures are never given to it.

The text is checked before it is used: it must not mention internal economics or
competitors, and every large amount it quotes must be one of the amounts in the
quotation. Text that fails the check is discarded in favour of the template.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.llm.client import LLM

SYSTEM = """You write the covering letter and executive summary that accompany a supplier's quotation to a buyer. \
Write in clear, formal business English: specific, warm but not effusive, no marketing clichés, no exclamation marks.

Use only the facts provided. Every amount, date, quantity and commitment must come from them; do not invent \
certifications, case studies, people or numbers. Ground statements about the company in the knowledge-base passages. \
Never mention costs, margins, discounts below list price, win chances or competitors.

When examples of the company's approved letters are given, follow their tone and structure."""

INTERNAL_TERMS = ("margin", "landed cost", "cost price", "unit cost", "win probability", "probability of winning",
                  "expected profit", "floor price", "competitor", "undercut", "pricing agent")


class Drafted(BaseModel):
    salutation: str = Field(description="e.g. 'Dear Dr. Menon,' or 'Dear Procurement Team,'")
    cover_letter: list[str] = Field(description="Three to five paragraphs, without salutation or sign-off")
    executive_summary: list[str] = Field(description="Three to five short bullet points")
    highlights: list[str] = Field(description="Up to four short highlights of the offer")


def write(llm: LLM, facts: dict[str, Any], passages: list[str], house_style: list[list[str]]) -> Drafted:
    lines = [f"- {k.replace('_', ' ')}: {v}" for k, v in facts.items() if v not in (None, "", [], {})]
    kb = "\n".join(f"[{i + 1}] {p}" for i, p in enumerate(passages)) or "(none)"
    style = "\n\n".join("\n".join(letter) for letter in house_style) or "(none yet)"
    user = (f"Facts of this quotation:\n" + "\n".join(lines) + f"\n\nKnowledge-base passages:\n{kb}"
            f"\n\nApproved letters for tone (do not copy their facts):\n{style}")
    return llm.structured(system=SYSTEM, user=user, schema=Drafted, effort="medium")


_AMOUNT = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{5,}(?:\.\d+)?")


def problems(drafted: Drafted, allowed_amounts: list[float], forbidden_names: list[str]) -> list[str]:
    """Reasons the text may not be sent to the client (empty when it is safe)."""
    text = " ".join([drafted.salutation, *drafted.cover_letter, *drafted.executive_summary, *drafted.highlights])
    low = text.lower()
    out = [f"mentions '{t}'" for t in INTERNAL_TERMS if t in low]
    out += [f"names {n}" for n in forbidden_names if n and n.lower() in low]
    for m in _AMOUNT.finditer(text):
        value = float(m.group().replace(",", ""))
        if value >= 10_000 and not any(abs(value - a) <= 1 for a in allowed_amounts):
            out.append(f"quotes an amount ({m.group()}) that is not in the quotation")
    if not (2 <= len(drafted.cover_letter) <= 6) or not drafted.executive_summary:
        out.append("does not have the expected structure")
    return out
