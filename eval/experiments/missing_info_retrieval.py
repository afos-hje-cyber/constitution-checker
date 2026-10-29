"""Feasibility check: can the LLM's own "missing_information" text find the
articles that retrieval missed? Retrieval only, no Gemini calls, dev only.

For dev cases 5, 20 and 35 the k=8 baseline answer said which articles were
missing. We retrieve (hybrid, top 30) with:
  (0) the proposal alone (reference: what the baseline did)
  (a) missing_information alone
  (b) proposal + missing_information
and report the rank of each expected article.

Run:  .venv\\Scripts\\python eval\\experiments\\missing_info_retrieval.py
Output: eval/results/experiments/exp_missing_info_retrieval.{md,json}
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
from common import config  # noqa: E402
from rag.retrieve import retrieve  # noqa: E402

SOURCE_RUN = ROOT / "eval" / "results" / "dev" / "baseline_v1_dev24.json"   # k=8 answers, dev only
CASE_IDS = (5, 20, 35)
DEPTH = 30
OUT = ROOT / "eval" / "results" / "experiments" / "exp_missing_info_retrieval"


def article_ranks(query, expected):
    """{article: rank of its first chunk in the top DEPTH, or None}, plus the top 5."""
    hits = retrieve(query, config.RETRIEVAL_STRATEGY, DEPTH, rerank=False)
    ranks = {a: next((i for i, h in enumerate(hits, 1) if h["article"] == a), None)
             for a in expected}
    return ranks, [h["chunk_id"].removeprefix("art") for h in hits[:5]]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(SOURCE_RUN, encoding="utf-8") as f:
        source = json.load(f)
    assert source["sets"] == ["dev"] and source["config"]["k"] == 8
    cases = {c["id"]: c for c in source["cases"] if c["id"] in CASE_IDS}

    results = []
    for cid in CASE_IDS:
        c = cases[cid]
        mi = c["missing_information"]
        queries = {"0_proposal": c["proposal"], "a_missing_info": mi,
                   "b_proposal_plus_missing_info": f"{c['proposal']} {mi}"}
        results.append({
            "id": cid, "proposal": c["proposal"], "missing_information": mi,
            "expected_articles": c["expected_articles"],
            "runs": {name: dict(zip(("ranks", "top5"), article_ranks(q, c["expected_articles"])))
                     for name, q in queries.items()},
        })

    meta = {"experiment": "missing_info_retrieval",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_run": SOURCE_RUN.name, "strategy": config.RETRIEVAL_STRATEGY,
            "depth": DEPTH, "gemini_calls": 0}
    with open(f"{OUT}.json", "w", encoding="utf-8") as f:
        json.dump({**meta, "cases": results}, f, ensure_ascii=False, indent=2)

    def fmt(ranks):
        return ", ".join(f"{a}: {r if r else f'>{DEPTH}'}" for a, r in ranks.items())

    L = ["# Experiment: retrieval with the LLM's missing_information (dev, retrieval only)", "",
         f"- Date: {meta['created_at']} · source: `{SOURCE_RUN.name}` (k=8 answers) · "
         f"hybrid top {DEPTH} · 0 Gemini calls", "",
         "Rank of each expected article (first chunk of that article) in the hybrid top 30.", "",
         "| case | expected | (0) proposal | (a) missing_info | (b) proposal + missing_info |",
         "|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['id']} | {', '.join(map(str, r['expected_articles']))} | "
                 + " | ".join(fmt(r["runs"][k]["ranks"]) for k in
                              ("0_proposal", "a_missing_info", "b_proposal_plus_missing_info"))
                 + " |")
    L += ["", "## Queries and top 5", ""]
    for r in results:
        L.append(f"### {r['id']}: {r['proposal']}")
        L.append(f"- missing_information: {r['missing_information']}")
        for k, label in (("0_proposal", "(0)"), ("a_missing_info", "(a)"),
                         ("b_proposal_plus_missing_info", "(b)")):
            L.append(f"- {label} top 5: {', '.join(r['runs'][k]['top5'])}")
        L.append("")
    Path(f"{OUT}.md").write_text("\n".join(L), encoding="utf-8")
    print(Path(f"{OUT}.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
