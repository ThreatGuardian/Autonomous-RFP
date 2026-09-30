"""Report editing assistant — turns typed instructions into precise document edits.

No language model is involved. An instruction is understood in two layers:

1. **Grammar.** Ordered patterns for each supported edit extract the operation
   and its arguments ("rename *risks* to *Key risks*", "move *delivery* above
   *risks*", "replace *30 days* with *21 days*", "add a next step: …").
2. **Intent model.** A TF-IDF + logistic-regression classifier trained here on
   generated command phrasings recognises what the user meant when the wording
   is outside the grammar, and the assistant answers with the exact phrasing it
   can act on.

Section names are resolved by synonyms and token overlap ("timeline" →
"Delivery roadmap"). Facts can be pulled from the pipeline's figures ("add the
total price to the summary") or from the knowledge base by retrieval ("mention
our ISO 27001 certification in risks"). Every edit is undoable, and the reply
lists exactly which sections and blocks changed so the editor can highlight
them.
"""

from __future__ import annotations

import copy
import random
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.nlp.text import analyze, fold, split_sentences
from app.report.builder import block, new_id, section

HISTORY_LIMIT = 40

SYNONYMS: dict[str, list[str]] = {
    "summary": ["summary", "overview", "executive summary", "introduction", "intro", "headline"],
    "award": ["award", "award position", "l1", "bid position", "qcbs", "evaluation", "ranking"],
    "lines": ["win probability", "probability", "lines", "per line", "line chances", "win chances"],
    "decisions": ["pricing decisions", "key decisions", "decisions", "pricing"],
    "economics": ["margin", "margin structure", "economics", "costs", "cost structure"],
    "compliance": ["compliance", "tender compliance", "eligibility", "deviations"],
    "delivery": ["delivery", "roadmap", "timeline", "schedule", "milestones", "delivery plan"],
    "risks": ["risk", "risks", "risks to weigh", "concerns"],
    "next": ["next steps", "next", "actions", "action items", "to do", "todo", "steps"],
    "method": ["method", "methodology", "method note", "how", "footnote", "assumptions"],
}
FIGURE_WORDS: dict[str, list[str]] = {
    "total price": ["total", "total price", "total value", "quote value", "offer value", "grand total", "price"],
    "net price": ["net price", "net value", "subtotal"],
    "tax": ["tax", "gst", "vat", "taxes"],
    "margin": ["margin", "gross margin"],
    "win probability": ["win probability", "chance of winning", "win chance", "odds", "probability"],
    "expected profit": ["expected profit", "profit"],
    "services": ["services", "free services", "bundled services", "inclusions"],
    "deadline": ["deadline", "due date", "submission date"],
    "competitors": ["competitors", "competition", "rivals", "market"],
    "l1": ["l1", "lowest bid", "lowest rival", "gap to l1"],
    "compliance": ["compliance", "mandatory clauses"],
    "eligibility": ["eligibility", "eligibility verdict"],
}
BULLET_SECTION_HINTS = {"risk": "risks", "next step": "next", "step": "next", "action": "next", "decision": "decisions"}
QUOTE = r"[\"'“”‘’]"

HELP = ("I can edit this report for you. Try:\n"
        "• “Rename risks to Key risks”\n"
        "• “Move delivery above risks” or “move compliance to the top”\n"
        "• “Replace 'Stretch bid' with 'Competitive bid'”\n"
        "• “Add a next step: confirm OEM authorisation letters by Friday”\n"
        "• “Add a paragraph to the summary: …”\n"
        "• “Remove the bullet about currency” · “Shorten the risks section”\n"
        "• “Hide the method section” · “Delete the award section”\n"
        "• “Add the total price to the summary” · “Mention our ISO 27001 certification in risks”\n"
        "• “Refresh the pricing decisions with the latest figures” · “Undo”")


@dataclass
class Result:
    reply: str
    changed: bool = False
    changes: list[dict[str, Any]] = field(default_factory=list)
    intent: str = "none"
    confidence: float = 1.0
    suggestions: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- intent model

_TEMPLATES: dict[str, list[str]] = {
    "rename_section": ["rename {s} to {t}", "call the {s} section {t}", "change the heading of {s} to {t}",
                       "retitle {s} as {t}", "can you rename the {s} heading", "i want a different name for {s}"],
    "set_title": ["change the title to {t}", "set the report title to {t}", "make the title {t}", "rename the report to {t}",
                  "the document title should say {t}"],
    "replace_text": ["replace {x} with {y}", "change {x} to {y}", "swap {x} for {y}", "use {y} instead of {x}",
                     "everywhere it says {x} write {y}", "correct {x} to {y}"],
    "delete_section": ["remove the {s} section", "delete {s} section", "drop the {s} part", "get rid of the {s} section",
                       "i don't need the {s} section"],
    "hide_section": ["hide {s}", "hide the {s} section", "don't show {s} in the export", "leave {s} out of the pdf"],
    "show_section": ["show {s} again", "unhide {s}", "bring back the {s} section", "restore {s}"],
    "move_section": ["move {s} above {s2}", "put {s} before {s2}", "move {s} to the top", "move {s} to the end",
                     "place {s} after {s2}", "reorder so {s} comes first"],
    "add_bullet": ["add a point to {s}: {y}", "add a risk: {y}", "add a next step: {y}", "add '{y}' to {s}",
                   "include a bullet in {s} saying {y}", "append to {s} that {y}"],
    "add_paragraph": ["add a paragraph to {s}: {y}", "write under {s}: {y}", "insert a note in {s} saying {y}",
                      "add text to the {s} section: {y}"],
    "add_section": ["add a section called {t}", "create a new section named {t}", "insert a section titled {t} with {y}"],
    "delete_text": ["remove the bullet about {x}", "delete the sentence mentioning {x}", "drop the point on {x}",
                    "take out the line about {x}"],
    "shorten": ["shorten {s}", "make {s} shorter", "condense the {s} section", "summarise {s}", "trim {s}",
                "make {s} more concise"],
    "refresh": ["refresh {s}", "update {s} with the latest figures", "regenerate {s}", "recalculate {s}",
                "rebuild the {s} section", "refresh everything"],
    "insert_fact": ["add the {f} to {s}", "mention the {f} in {s}", "include our {f} in {s}", "cite our {f} under {s}",
                    "put the {f} in the {s}"],
    "undo": ["undo", "undo that", "revert the last change", "go back", "that was wrong, revert"],
    "redo": ["redo", "redo that", "put it back"],
    "help": ["help", "what can you do", "how do i edit this", "what commands are there", "show me examples"],
    "list_sections": ["list the sections", "what sections are there", "show the outline", "which sections exist"],
}
_FILL = {
    "s": ["risks", "summary", "delivery", "next steps", "pricing decisions", "compliance", "award", "margin", "timeline"],
    "s2": ["risks", "summary", "delivery", "next steps", "compliance"],
    "t": ["Key risks", "Executive summary", "Our recommendation", "Delivery plan", "Bid decision"],
    "x": ["30 days", "stretch bid", "currency", "the old price", "Dell"],
    "y": ["confirm stock with distribution", "we will submit by Friday", "21 days", "the client prefers phased delivery"],
    "f": ["total price", "margin", "ISO 27001 certification", "warranty programme", "win probability", "deadline"],
}

_model: Pipeline | None = None
_lock = threading.Lock()


def intent_model() -> Pipeline:
    global _model
    with _lock:
        if _model is None:
            rng = random.Random(7)
            texts, labels = [], []
            for intent, templates in _TEMPLATES.items():
                for _ in range(60):
                    t = rng.choice(templates)
                    texts.append(re.sub(r"\{(\w+)\}", lambda m: rng.choice(_FILL[m.group(1)]), t))
                    labels.append(intent)
            pipe = Pipeline([("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)),
                             ("clf", LogisticRegression(C=6.0, max_iter=2000))])
            pipe.fit(texts, labels)
            _model = pipe
        return _model


# --------------------------------------------------------------------------- helpers


def _clean(arg: str) -> str:
    return re.sub(rf"^{QUOTE}|{QUOTE}$", "", arg.strip().rstrip(".!")).strip()


def _snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    return {"title": doc["title"], "sections": copy.deepcopy(doc["sections"])}


def resolve_section(doc: dict[str, Any], name: str) -> dict[str, Any] | None:
    name_f = fold(_clean(name))
    name_f = re.sub(r"\b(the|section|part|block)\b", " ", name_f).strip()
    if not name_f:
        return None
    best, best_score = None, 0.0
    want = set(analyze(name_f))
    for sec in doc["sections"]:
        title_f = fold(sec["title"])
        score = 0.0
        if name_f == title_f:
            score = 3.0
        elif name_f in title_f:
            score = 2.0
        for syn in SYNONYMS.get(sec.get("key", ""), []):
            if name_f == syn:
                score = max(score, 2.5)
            elif re.search(rf"\b{re.escape(syn)}\b", name_f):
                score = max(score, 1.5 + len(syn) / 100)
        have = set(analyze(title_f))
        if want and have:
            score = max(score, len(want & have) / len(want | have) * 1.6)
        if score > best_score:
            best, best_score = sec, score
    return best if best_score >= 0.5 else None


def _texts(b: dict[str, Any]) -> list[str]:
    out = []
    if "text" in b:
        out.append(b["text"])
    for i in b.get("items", []):
        out.append(i if isinstance(i, str) else " ".join(str(v) for v in i.values()))
    for r in b.get("rows", []):
        out.append(" ".join(r))
    return out


def _shorten_text(text: str, keep: float = 0.5) -> str:
    sentences = split_sentences(text)
    if len(sentences) <= 1:
        words = text.split()
        return text if len(words) <= 24 else " ".join(words[:24]).rstrip(",;") + "…"
    freq: dict[str, int] = {}
    for s in sentences:
        for t in set(analyze(s)):
            freq[t] = freq.get(t, 0) + 1
    scored = [(sum(freq.get(t, 0) for t in set(analyze(s))) / (1 + len(analyze(s)) ** 0.5) + (1.0 if i == 0 else 0.0), i, s)
              for i, s in enumerate(sentences)]
    n = max(1, round(len(sentences) * keep))
    chosen = sorted(sorted(scored, reverse=True)[:n], key=lambda t: t[1])
    return " ".join(s for _, _, s in chosen)


# --------------------------------------------------------------------------- assistant


class ReportAssistant:
    def __init__(self, figures: dict[str, str], regenerate: Callable[[str | None], list[dict[str, Any]]],
                 retrieve: Callable[[str], list[Any]]) -> None:
        self.figures = figures
        self.regenerate = regenerate
        self.retrieve = retrieve

    # ------------------------------------------------------------------ entry point

    def handle(self, doc: dict[str, Any], message: str) -> Result:
        text = message.strip()
        low = fold(text)
        before = _snapshot(doc)
        if re.fullmatch(r"(please\s+)?(undo|undo that|revert( that| the last change)?|go back)[.!]?", low):
            return self._undo(doc)
        if re.fullmatch(r"(please\s+)?(redo|redo that|put it back)[.!]?", low):
            return self._redo(doc)
        for pattern, handler in self._rules():
            m = re.search(pattern, text, re.I)
            if m:
                result = handler(doc, m)
                if result.changed:
                    doc.setdefault("history", []).append(before)
                    doc["history"] = doc["history"][-HISTORY_LIMIT:]
                    doc["redo"] = []
                    doc["edited"] = True
                result.suggestions = result.suggestions or self._suggest(doc)
                return result
        return self._fallback(doc, text)

    def _rules(self) -> list[tuple[str, Callable[[dict[str, Any], re.Match[str]], Result]]]:
        q = QUOTE
        return [
            (r"^(?:please\s+)?(?:help|what can you do|how (?:do|can) i\b.*|show (?:me )?examples|commands)\??$", self._help),
            (r"^(?:list|show|what are)\s+(?:the\s+|all\s+)?(?:sections|outline|headings)|which sections", self._list),
            (r"(?:change|set|rename|make|update)\s+(?:the\s+)?(?:report\s+|document\s+|main\s+)?title\s+(?:to|as|into)\s+(.+)$", self._set_title),
            (r"(?:rename|retitle)\s+(?:the\s+)?(.+?)(?:\s+section|\s+heading)?\s+(?:to|as|into)\s+(.+)$", self._rename),
            (r"change\s+the\s+(?:heading|title|name)\s+of\s+(?:the\s+)?(.+?)(?:\s+section)?\s+to\s+(.+)$", self._rename),
            (r"call\s+the\s+(.+?)\s+section\s+(.+)$", self._rename),
            (r"^(?:please\s+)?(?:hide|collapse)\s+(?:the\s+)?(.+?)(?:\s+section)?(?:\s+from the (?:export|pdf|report))?$", self._hide),
            (r"^(?:please\s+)?(?:show|unhide|restore|bring back)\s+(?:the\s+)?(.+?)(?:\s+section)?(?:\s+again)?$", self._show),
            (r"(?:remove|delete|drop|take out)\s+(?:the\s+|all\s+)?(?:bullets?|points?|lines?|sentences?|paragraphs?|rows?|items?|steps?|risks?)"
             r"\s+(?:about|mentioning|on|containing|that mentions?|with|referring to)\s+(.+)$", self._delete_text),
            (r"(?:remove|delete|drop|get rid of)\s+(?:the\s+)?(.+?)\s+section$", self._delete_section),
            (r"(?:remove|delete|drop)\s+(?:the\s+)?section\s+(?:on|about|called|named)?\s*(.+)$", self._delete_section),
            (r"(?:move|put|place)\s+(?:the\s+)?(.+?)(?:\s+section)?\s+(to the top|at the top|to the start|first|to the beginning|"
             r"to the end|at the end|to the bottom|last)$", self._move_edge),
            (r"(?:move|put|place)\s+(?:the\s+)?(.+?)(?:\s+section)?\s+(above|before|below|after|under|beneath)\s+(?:the\s+)?(.+?)(?:\s+section)?$",
             self._move_relative),
            (r"(?:add|create|insert)\s+(?:a\s+)?(?:new\s+)?section\s+(?:called|named|titled|on)\s+(.+?)(?:\s*(?:with|saying|:)\s+(.+))?$",
             self._add_section),
            (rf"(?:replace|swap)\s+{q}?(.+?){q}?\s+(?:with|by|for)\s+{q}?(.+?){q}?$", self._replace),
            (rf"(?:change|correct|update)\s+{q}(.+?){q}\s+(?:to|into)\s+{q}?(.+?){q}?$", self._replace),
            (rf"use\s+{q}?(.+?){q}?\s+instead of\s+{q}?(.+?){q}?$", self._replace_reversed),
            (r"(?:add|write|insert|append)\s+(?:a\s+)?(?:paragraph|note|sentence|text)(?:\s+(?:to|under|in|into)\s+(?:the\s+)?(.+?))?(?:\s+section)?"
             r"\s*(?::|saying|that says|reading)\s*(.+)$", self._add_paragraph),
            (r"(?:add|append|include|insert)\s+(?:a\s+|another\s+)?(point|bullet|item|line|risk|next step|step|action|decision)"
             r"(?:\s+(?:to|under|in|into)\s+(?:the\s+)?(.+?))?(?:\s+section)?\s*(?::|saying|that says|that)\s*(.+)$", self._add_bullet),
            (rf"(?:add|append|include|insert)\s+{q}(.+?){q}\s+(?:to|under|in|into)\s+(?:the\s+)?(.+?)(?:\s+section)?$", self._add_quoted),
            (r"(shorten|condense|summari[sz]e|trim|tighten)\s+(?:the\s+)?(.+?)(?:\s+section)?$", self._shorten),
            (r"make\s+(?:the\s+)?(.+?)(?:\s+section)?\s+(?:shorter|more concise|briefer|tighter)$", self._shorten_alt),
            (r"(?:refresh|update|regenerate|recalculate|rebuild|recompute)\s+(?:the\s+)?(.+?)(?:\s+section)?"
             r"(?:\s+with\s+(?:the\s+)?(?:latest|current|new)\s+(?:figures|numbers|data|prices))?$", self._refresh),
            (r"(?:add|mention|include|insert|cite|put)\s+(?:the\s+|our\s+)?(.+?)\s+(?:to|in|into|under|on)\s+(?:the\s+)?(.+?)(?:\s+section)?$",
             self._insert_fact),
        ]

    # ------------------------------------------------------------------ handlers

    def _help(self, doc: dict[str, Any], _m: re.Match[str]) -> Result:
        return Result(HELP, intent="help")

    def _list(self, doc: dict[str, Any], _m: re.Match[str]) -> Result:
        lines = [f"{i + 1}. {s['title']}{' (hidden)' if s.get('hidden') else ''}" for i, s in enumerate(doc["sections"])]
        return Result("The report has these sections:\n" + "\n".join(lines), intent="list_sections")

    def _set_title(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        new = _clean(m.group(1))
        old, doc["title"] = doc["title"], new
        return Result(f"Changed the report title from “{old}” to “{new}”.", True, [{"section": None, "block": None, "action": "title"}],
                      intent="set_title")

    def _rename(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(1))
        if sec is None:
            return self._no_section(doc, m.group(1))
        old, sec["title"] = sec["title"], _clean(m.group(2))
        return Result(f"Renamed “{old}” to “{sec['title']}”.", True, [{"section": sec["id"], "block": None, "action": "renamed"}],
                      intent="rename_section")

    def _hide(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(1))
        if sec is None:
            return self._no_section(doc, m.group(1))
        sec["hidden"] = True
        return Result(f"Hid “{sec['title']}”. It stays in the editor but is left out of the PDF and Word exports.", True,
                      [{"section": sec["id"], "block": None, "action": "hidden"}], intent="hide_section")

    def _show(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(1))
        if sec is None:
            return self._no_section(doc, m.group(1))
        sec["hidden"] = False
        return Result(f"“{sec['title']}” is visible again.", True, [{"section": sec["id"], "block": None, "action": "shown"}],
                      intent="show_section")

    def _delete_section(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(1))
        if sec is None:
            return self._no_section(doc, m.group(1))
        doc["sections"] = [s for s in doc["sections"] if s["id"] != sec["id"]]
        return Result(f"Deleted the “{sec['title']}” section. Say “undo” to bring it back.", True,
                      [{"section": sec["id"], "block": None, "action": "deleted"}], intent="delete_section")

    def _move_edge(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(1))
        if sec is None:
            return self._no_section(doc, m.group(1))
        rest = [s for s in doc["sections"] if s["id"] != sec["id"]]
        top = re.search(r"top|start|first|beginning", m.group(2), re.I)
        doc["sections"] = [sec, *rest] if top else [*rest, sec]
        return Result(f"Moved “{sec['title']}” to the {'top' if top else 'end'} of the report.", True,
                      [{"section": sec["id"], "block": None, "action": "moved"}], intent="move_section")

    def _move_relative(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec, anchor = resolve_section(doc, m.group(1)), resolve_section(doc, m.group(3))
        if sec is None:
            return self._no_section(doc, m.group(1))
        if anchor is None:
            return self._no_section(doc, m.group(3))
        if sec["id"] == anchor["id"]:
            return Result("Those are the same section, so nothing moved.", intent="move_section")
        rest = [s for s in doc["sections"] if s["id"] != sec["id"]]
        i = next(k for k, s in enumerate(rest) if s["id"] == anchor["id"])
        before = m.group(2).lower() in ("above", "before")
        rest.insert(i if before else i + 1, sec)
        doc["sections"] = rest
        return Result(f"Moved “{sec['title']}” {'above' if before else 'below'} “{anchor['title']}”.", True,
                      [{"section": sec["id"], "block": None, "action": "moved"}], intent="move_section")

    def _add_section(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        title = _clean(m.group(1))
        body = _clean(m.group(2)) if m.group(2) else "Add the content for this section here."
        sec = section("custom", title, [block("paragraph", text=body)])
        nxt = next((k for k, s in enumerate(doc["sections"]) if s.get("key") in ("next", "method")), len(doc["sections"]))
        doc["sections"].insert(nxt, sec)
        return Result(f"Added a new section “{title}”" + (" with your text." if m.group(2) else ". Type into it or tell me what to write."),
                      True, [{"section": sec["id"], "block": sec["blocks"][0]["id"], "action": "added"}], intent="add_section")

    def _replace(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        return self._do_replace(doc, _clean(m.group(1)), _clean(m.group(2)))

    def _replace_reversed(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        return self._do_replace(doc, _clean(m.group(2)), _clean(m.group(1)))

    def _do_replace(self, doc: dict[str, Any], old: str, new: str) -> Result:
        # "Change the risks section to Key risks" is a rename, not a text replacement.
        sec = resolve_section(doc, old) if re.search(r"\bsection\b|\bheading\b", old, re.I) else None
        if sec is not None:
            prev, sec["title"] = sec["title"], new
            return Result(f"Renamed “{prev}” to “{new}”.", True, [{"section": sec["id"], "block": None, "action": "renamed"}],
                          intent="rename_section")
        pattern = re.compile(re.escape(old), re.I)
        changes, count = [], 0

        def sub(value: str) -> str:
            nonlocal count
            out, n = pattern.subn(new, value)
            count += n
            return out

        for s in doc["sections"]:
            if pattern.search(s["title"]):
                s["title"] = sub(s["title"])
                changes.append({"section": s["id"], "block": None, "action": "edited"})
            for b in s["blocks"]:
                hit = False
                if "text" in b and pattern.search(b["text"]):
                    b["text"], hit = sub(b["text"]), True
                if b.get("items"):
                    for i, it in enumerate(b["items"]):
                        if isinstance(it, str) and pattern.search(it):
                            b["items"][i], hit = sub(it), True
                        elif isinstance(it, dict):
                            for k in ("label", "value", "note", "display"):
                                if isinstance(it.get(k), str) and pattern.search(it[k]):
                                    it[k], hit = sub(it[k]), True
                for r in b.get("rows", []):
                    for j, c in enumerate(r):
                        if pattern.search(c):
                            r[j], hit = sub(c), True
                if hit:
                    changes.append({"section": s["id"], "block": b["id"], "action": "edited"})
        if pattern.search(doc["title"]):
            doc["title"] = sub(doc["title"])
        if not count:
            return Result(f"I couldn't find “{old}” in the report. Check the exact wording, or select the text in the document "
                          "and type over it.", intent="replace_text")
        return Result(f"Replaced “{old}” with “{new}” in {count} place{'s' if count != 1 else ''}.", True, changes,
                      intent="replace_text")

    def _delete_text(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        needle = _clean(m.group(1))
        want = set(analyze(needle)) or {fold(needle)}
        changes, removed = [], []
        for s in doc["sections"]:
            for b in list(s["blocks"]):
                if b.get("items") and all(isinstance(i, str) for i in b["items"]):
                    keep = [i for i in b["items"] if not self._mentions(i, needle, want)]
                    if len(keep) != len(b["items"]):
                        removed += [i for i in b["items"] if i not in keep]
                        b["items"] = keep
                        changes.append({"section": s["id"], "block": b["id"], "action": "edited"})
                    if not b["items"]:
                        s["blocks"].remove(b)
                elif b.get("rows"):
                    keep = [r for r in b["rows"] if not self._mentions(" ".join(r), needle, want)]
                    if len(keep) != len(b["rows"]):
                        removed += [" · ".join(r) for r in b["rows"] if r not in keep]
                        b["rows"] = keep
                        changes.append({"section": s["id"], "block": b["id"], "action": "edited"})
                elif "text" in b and b["type"] in ("paragraph", "note", "lead", "callout"):
                    sentences = split_sentences(b["text"])
                    keep = [x for x in sentences if not self._mentions(x, needle, want)]
                    if len(keep) != len(sentences):
                        removed += [x for x in sentences if x not in keep]
                        if keep:
                            b["text"] = " ".join(keep)
                            changes.append({"section": s["id"], "block": b["id"], "action": "edited"})
                        else:
                            s["blocks"].remove(b)
                            changes.append({"section": s["id"], "block": b["id"], "action": "deleted"})
        if not removed:
            return Result(f"Nothing in the report mentions “{needle}”.", intent="delete_text")
        preview = removed[0][:90] + ("…" if len(removed[0]) > 90 else "")
        return Result(f"Removed {len(removed)} item{'s' if len(removed) != 1 else ''} mentioning “{needle}”, e.g. “{preview}”.",
                      True, changes, intent="delete_text")

    @staticmethod
    def _mentions(text: str, needle: str, want: set[str]) -> bool:
        if fold(needle) in fold(text):
            return True
        have = set(analyze(text))
        return bool(want) and len(want & have) / len(want) >= 0.75

    def _add_paragraph(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(1)) if m.group(1) else doc["sections"][0]
        if sec is None:
            return self._no_section(doc, m.group(1))
        text = _clean(m.group(2))
        b = block("paragraph", text=text[:1].upper() + text[1:])
        sec["blocks"].append(b)
        return Result(f"Added a paragraph to “{sec['title']}”.", True, [{"section": sec["id"], "block": b["id"], "action": "added"}],
                      intent="add_paragraph")

    def _add_bullet(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        kind, where, text = m.group(1).lower(), m.group(2), _clean(m.group(3))
        target = resolve_section(doc, where) if where else None
        if target is None:
            hint = next((key for word, key in BULLET_SECTION_HINTS.items() if word in kind), None)
            target = next((s for s in doc["sections"] if s.get("key") == hint), None) if hint else None
        if target is None and where:
            return self._no_section(doc, where)
        if target is None:
            return Result("Which section should the point go into? For example: “add a point to risks: …”.",
                          intent="add_bullet")
        return self._append_item(target, text[:1].upper() + text[1:], "add_bullet")

    def _add_quoted(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        sec = resolve_section(doc, m.group(2))
        if sec is None:
            return self._no_section(doc, m.group(2))
        text = _clean(m.group(1))
        return self._append_item(sec, text[:1].upper() + text[1:], "add_bullet")

    @staticmethod
    def _append_item(sec: dict[str, Any], text: str, intent: str) -> Result:
        text = text if text.endswith((".", "!", "?")) else text + "."
        target = next((b for b in reversed(sec["blocks"]) if b["type"] == "bullets"), None)
        if target is None:
            target = block("bullets", items=[])
            sec["blocks"].append(target)
        target["items"].append(text)
        return Result(f"Added to “{sec['title']}”: “{text}”", True, [{"section": sec["id"], "block": target["id"], "action": "added"}],
                      intent=intent)

    def _shorten(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        return self._do_shorten(doc, m.group(2))

    def _shorten_alt(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        return self._do_shorten(doc, m.group(1))

    def _do_shorten(self, doc: dict[str, Any], name: str) -> Result:
        sec = resolve_section(doc, name)
        if sec is None:
            return self._no_section(doc, name)
        before = sum(len(" ".join(_texts(b)).split()) for b in sec["blocks"])
        changes = []
        for b in sec["blocks"]:
            if b["type"] in ("paragraph", "lead", "note") and len(b["text"].split()) > 20:
                b["text"] = _shorten_text(b["text"])
                changes.append({"section": sec["id"], "block": b["id"], "action": "edited"})
            elif b["type"] == "bullets" and len(b.get("items", [])) > 3:
                ranked = sorted(b["items"], key=lambda i: -len(set(analyze(i))))[:3]
                b["items"] = [i for i in b["items"] if i in ranked]
                changes.append({"section": sec["id"], "block": b["id"], "action": "edited"})
            elif b["type"] == "bullets":
                shortened = [_shorten_text(i, 0.5) if len(i.split()) > 28 else i for i in b.get("items", [])]
                if shortened != b.get("items"):
                    b["items"] = shortened
                    changes.append({"section": sec["id"], "block": b["id"], "action": "edited"})
        after = sum(len(" ".join(_texts(b)).split()) for b in sec["blocks"])
        if not changes:
            return Result(f"“{sec['title']}” is already concise.", intent="shorten")
        return Result(f"Shortened “{sec['title']}” from {before} to {after} words, keeping the most informative sentences and points.",
                      True, changes, intent="shorten")

    def _refresh(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        name = m.group(1)
        if re.fullmatch(r"(?:all|everything|the whole report|whole report|report|all sections|the report)", name.strip(), re.I):
            fresh = self.regenerate(None)
            by_key = {s["key"]: s for s in fresh}
            changes = []
            for i, s in enumerate(doc["sections"]):
                if s.get("key") in by_key:
                    new = by_key[s["key"]]
                    new["title"], new["hidden"], new["id"] = s["title"], s.get("hidden", False), s["id"]
                    doc["sections"][i] = new
                    changes.append({"section": s["id"], "block": None, "action": "refreshed"})
            doc["stale"] = False
            return Result(f"Refreshed {len(changes)} generated sections with the latest figures. Sections you added are unchanged.",
                          True, changes, intent="refresh")
        sec = resolve_section(doc, name)
        if sec is None:
            return self._no_section(doc, name)
        if sec.get("key") in (None, "custom"):
            return Result(f"“{sec['title']}” is a section you wrote, so there is nothing to regenerate.", intent="refresh")
        fresh = self.regenerate(sec["key"])
        if not fresh:
            return Result(f"“{sec['title']}” has no generated content for this request.", intent="refresh")
        sec["blocks"] = fresh[0]["blocks"]
        return Result(f"Refreshed “{sec['title']}” from the latest pricing and compliance results.", True,
                      [{"section": sec["id"], "block": None, "action": "refreshed"}], intent="refresh")

    def _insert_fact(self, doc: dict[str, Any], m: re.Match[str]) -> Result:
        what, where = _clean(m.group(1)), m.group(2)
        sec = resolve_section(doc, where)
        if sec is None:
            return self._no_section(doc, where)
        key = self._figure_key(what)
        if key:
            text = self.figures[key]
            b = block("paragraph", text=text)
            sec["blocks"].append(b)
            return Result(f"Added the {key} to “{sec['title']}”: “{text}”", True,
                          [{"section": sec["id"], "block": b["id"], "action": "added"}], intent="insert_fact")
        hits = self.retrieve(what)
        if not hits:
            return Result(f"I couldn't find anything about “{what}” in the company knowledge base or the bid figures.",
                          intent="insert_fact")
        text = hits[0].text
        result = self._append_item(sec, text, "insert_fact")
        result.reply = f"Added from the knowledge base ({hits[0].section}) to “{sec['title']}”: “{text}”"
        return result

    def _figure_key(self, what: str) -> str | None:
        w = fold(what)
        best, best_len = None, 0
        for key, words in FIGURE_WORDS.items():
            if key not in self.figures:
                continue
            for word in words:
                if re.search(rf"\b{re.escape(word)}\b", w) and len(word) > best_len:
                    best, best_len = key, len(word)
        # Knowledge-base phrases ("ISO 27001 certification") should not be mistaken for figures.
        if best and len(w.split()) > len(best.split()) + 2:
            return None
        return best

    # ------------------------------------------------------------------ undo / fallback

    def _undo(self, doc: dict[str, Any]) -> Result:
        if not doc.get("history"):
            return Result("There is nothing to undo.", intent="undo")
        doc.setdefault("redo", []).append(_snapshot(doc))
        prev = doc["history"].pop()
        doc["title"], doc["sections"] = prev["title"], prev["sections"]
        return Result("Undid the last change.", True, [], intent="undo", suggestions=["Redo", "List the sections"])

    def _redo(self, doc: dict[str, Any]) -> Result:
        if not doc.get("redo"):
            return Result("There is nothing to redo.", intent="redo")
        doc.setdefault("history", []).append(_snapshot(doc))
        nxt = doc["redo"].pop()
        doc["title"], doc["sections"] = nxt["title"], nxt["sections"]
        return Result("Redid the change.", True, [], intent="redo")

    def _no_section(self, doc: dict[str, Any], name: str | None) -> Result:
        titles = ", ".join(f"“{s['title']}”" for s in doc["sections"][:8])
        return Result(f"I couldn't tell which section “{_clean(name or '')}” refers to. The sections are {titles}.",
                      intent="clarify", suggestions=[f"Shorten {doc['sections'][0]['title'].lower()}"] if doc["sections"] else [])

    def _fallback(self, doc: dict[str, Any], text: str) -> Result:
        model = intent_model()
        proba = model.predict_proba([text])[0]
        classes = list(model.classes_)
        i = int(proba.argmax())
        intent, conf = classes[i], float(proba[i])
        examples = {
            "rename_section": "rename risks to Key risks", "set_title": "change the title to Bid decision — Godavari tender",
            "replace_text": "replace '30 days' with '21 days'", "delete_section": "delete the method section",
            "hide_section": "hide the method section", "show_section": "show the method section",
            "move_section": "move delivery above risks", "add_bullet": "add a next step: confirm stock with distribution",
            "add_paragraph": "add a paragraph to the summary: …", "add_section": "add a section called Client relationship",
            "delete_text": "remove the bullet about currency", "shorten": "shorten the risks section",
            "refresh": "refresh the pricing decisions", "insert_fact": "add the total price to the summary",
            "undo": "undo", "redo": "redo", "help": "help", "list_sections": "list the sections",
        }
        if conf >= 0.35 and intent in examples:
            return Result(f"It sounds like you want to {intent.replace('_', ' ')}, but I need it phrased a little more precisely. "
                          f"For example: “{examples[intent]}”.", intent=intent, confidence=round(conf, 3),
                          suggestions=[examples[intent].replace("…", "").strip(), "Help"])
        return Result("I didn't understand that instruction. " + HELP, intent="unknown", confidence=round(conf, 3),
                      suggestions=["Help", "List the sections"])

    def _suggest(self, doc: dict[str, Any]) -> list[str]:
        keys = {s.get("key") for s in doc["sections"]}
        out = []
        if "risks" in keys:
            out.append("Shorten the risks section")
        if "delivery" in keys and "risks" in keys:
            out.append("Move delivery above risks")
        if "next" in keys:
            out.append("Add a next step: ")
        out.append("Undo")
        return out[:4]


def ensure_ids(doc: dict[str, Any]) -> dict[str, Any]:
    """Give ids to sections and blocks created by the editor without one."""
    for s in doc["sections"]:
        s.setdefault("id", new_id())
        s.setdefault("key", "custom")
        s.setdefault("hidden", False)
        for b in s.get("blocks", []):
            b.setdefault("id", new_id())
    return doc
