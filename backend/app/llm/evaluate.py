"""Evaluate the parser on reference tenders, with and without the language model.

    cd backend
    python -m app.llm.evaluate                 # rules only (no API calls)
    ANTHROPIC_API_KEY=... python -m app.llm.evaluate --llm   # rules + Claude (makes paid API calls)

For every sample in ``evals/parser_gold.json`` it compares the items found with the
expected ones: an expected item counts as **found** when a parsed item has the same
quantity and overlapping wording, and as **correctly matched** when the parser also
selected the expected catalogue SKU. Use it before and after changing a prompt, the
examples or the rules; keep the change only when the scores do not drop.

Samples belong to different companies' catalogues, so each company is evaluated in its
own process.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evals" / "parser_gold.json"
SAMPLES = ROOT.parent / "samples"


def _overlap(a: str, b: str) -> float:
    from app.nlp.text import analyze

    x, y = set(analyze(a)), set(analyze(b))
    return len(x & y) / len(x | y) if x and y else 0.0


def score(expected: list[dict], parsed: list[dict]) -> dict[str, float | int]:
    used: set[int] = set()
    found = matched = 0
    for e in expected:
        best, best_score = None, 0.25
        for i, p in enumerate(parsed):
            if i in used or p["quantity"] != e["quantity"]:
                continue
            s = _overlap(e["description"], p["description"])
            if s > best_score:
                best, best_score = i, s
        if best is not None:
            used.add(best)
            found += 1
            matched += parsed[best]["sku"] == e["sku"]
    return {"expected": len(expected), "parsed": len(parsed), "found": found, "matched": matched,
            "extra": len(parsed) - len(used)}


def _run_company(company: str, files: list[str], use_llm: bool) -> list[dict]:
    """Parse ``files`` as ``company`` (called in a child process)."""
    from app.agents.base import PipelineContext, StageLog
    from app.agents.parser_agent import RfpParserAgent
    from app.db.seed import load_json, seed_all
    from app.services.documents import extract_text

    seed_all()
    out = []
    for name in files:
        path = SAMPLES / name
        text = extract_text(name, path.read_bytes())
        ctx = PipelineContext(1, "EVAL", text, load_json("company.json"), source_filename=name,
                              source_path=path if path.suffix in (".pdf", ".docx") else None)
        parsed = RfpParserAgent().run(ctx, StageLog())
        out.append({"file": name, "engine": parsed.stats.get("engine"),
                    "items": [{"description": i.description, "quantity": i.quantity, "sku": i.selected_sku}
                              for i in parsed.line_items]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="store_true", help="use the language model (requires ANTHROPIC_API_KEY; paid calls)")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.child:  # child process: one company
        print(json.dumps(_run_company(args.child[0], args.child[1:], args.llm)))
        return

    gold = json.loads(GOLD.read_text())["samples"]
    by_company: dict[str, list[dict]] = {}
    for s in gold:
        by_company.setdefault(s["company"], []).append(s)
    results: dict[str, dict] = {}
    for company, samples in by_company.items():
        env = {**os.environ, "TD_COMPANY": company, "TD_VAR_DIR": str(ROOT / "var" / f"eval-{company}"),
               "TD_LLM": "on" if args.llm else "off", "TD_FX_MODE": "offline"}
        cmd = [sys.executable, "-m", "app.llm.evaluate", "--child", company, *[s["file"] for s in samples]]
        if args.llm:
            cmd.insert(3, "--llm")
        done = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        for row in json.loads(done.stdout.strip().splitlines()[-1]):
            results[row["file"]] = row

    totals = {"expected": 0, "found": 0, "matched": 0, "extra": 0}
    print(f"{'sample':44} {'engine':28} {'found':>9} {'matched':>9} {'extra':>6}")
    for s in gold:
        r = results[s["file"]]
        sc = score(s["items"], r["items"])
        for k in totals:
            totals[k] += sc[k]
        print(f"{s['file'][:44]:44} {str(r['engine'])[:28]:28} {sc['found']:>4}/{sc['expected']:<4} "
              f"{sc['matched']:>4}/{sc['expected']:<4} {sc['extra']:>6}")
    n = totals["expected"] or 1
    print(f"\nItems found {totals['found']}/{totals['expected']} ({100 * totals['found'] / n:.1f}%), "
          f"correct product {totals['matched']}/{totals['expected']} ({100 * totals['matched'] / n:.1f}%), "
          f"extra items {totals['extra']}")


if __name__ == "__main__":
    main()
