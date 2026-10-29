"""Retrieval test: does the expected article show up in the top k?

Run:  .venv\\Scripts\\python eval\\legacy\\retrieval_test.py --run-name v2_hierarchy_prefix

For each strategy and k in (5, 8) prints the hit rate (% of cases with at
least one expected article in the top k). A chunk counts for its article,
e.g. art227_n1_a-h counts for 227. Also prints the rank of the first
expected article per case (full ranking, so a miss still shows its rank),
and the top 8 returned for every miss at k=8.

Every run is saved to eval/results/experiments/retrieval_<run-name>.json (config, cases,
hit rates, ranks and the top 20 per case), to build the experiment table.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ingest.chunking import STRATEGIES  # noqa: E402
from rag.retrieve import load_index, retrieve  # noqa: E402

CASES_PATH = ROOT / "eval" / "legacy" / "retrieval_cases.json"
RESULTS_DIR = ROOT / "eval" / "results" / "experiments"
KS = (5, 8)
SAVED_TOP = 20   # results kept per case, enough to re-score if cases change


def first_rank(results, expected):
    """1-based rank of the first chunk whose article is expected, or None."""
    for rank, hit in enumerate(results, start=1):
        if hit["article"] in expected:
            return rank
    return None


def save_results(run_name, cases, ranks, tops, metas):
    """Write config + hit rates + per-case ranks + top results to JSON."""
    any_meta = next(iter(metas.values()))
    out = {
        "run": run_name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "model": any_meta["model"],
            "revision": any_meta["revision"],
            "prefix_version": {s: m.get("prefix_version", "v1_basic") for s, m in metas.items()},
            "chunk_count": {s: m["chunk_count"] for s, m in metas.items()},
            "hybrid_max_words": metas["hybrid"]["hybrid_max_words"],
            "query_prefix": any_meta["query_prefix"],
            "query_rewriting": None,
            "ks": list(KS),
        },
        "cases": cases,
        "hit_rate": {
            s: {f"k={k}": sum(ranks[c["id"], s] <= k for c in cases) / len(cases) for k in KS}
            for s in STRATEGIES
        },
        "ranks": {str(c["id"]): {s: ranks[c["id"], s] for s in STRATEGIES} for c in cases},
        "top": {
            str(c["id"]): {
                s: [{"chunk_id": h["chunk_id"], "article": h["article"],
                     "score": round(h["score"], 4)} for h in tops[c["id"], s]]
                for s in STRATEGIES
            }
            for c in cases
        },
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"retrieval_{run_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", required=True, help="e.g. v2_hierarchy_prefix")
    args = parser.parse_args()

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    ranks = {}      # (case id, strategy) -> rank in the full ranking
    tops = {}       # (case id, strategy) -> top SAVED_TOP results
    metas = {}      # strategy -> index metadata
    for strategy in STRATEGIES:
        _, chunks, metas[strategy] = load_index(strategy)
        for case in cases:
            results = retrieve(case["proposal"], strategy, k=len(chunks))
            ranks[case["id"], strategy] = first_rank(results, case["expected_articles"])
            tops[case["id"], strategy] = results[:SAVED_TOP]
    top8 = {key: value[:8] for key, value in tops.items()}

    print("Hit rate (at least one expected article in top k)")
    print(f"{'strategy':10s}" + "".join(f"{'k=' + str(k):>12s}" for k in KS))
    for strategy in STRATEGIES:
        row = f"{strategy:10s}"
        for k in KS:
            hits = sum(ranks[c["id"], strategy] <= k for c in cases)
            row += f"{f'{hits}/{len(cases)} ({100 * hits / len(cases):.0f}%)':>12s}"
        print(row)

    print("\nRank of first expected article (miss = not in top 8; full rank in brackets)")
    print(f"{'case':4s} {'expected':9s}" + "".join(f"{s:>14s}" for s in STRATEGIES) + "  proposal")
    for case in cases:
        cells = ""
        for strategy in STRATEGIES:
            r = ranks[case["id"], strategy]
            cells += f"{(str(r) if r <= 8 else f'miss ({r})'):>14s}"
        expected = ",".join(map(str, case["expected_articles"]))
        print(f"{case['id']:4d} {expected:9s}{cells}  {case['proposal']}")

    print("\nMisses at k=8: what was returned instead")
    for case in cases:
        for strategy in STRATEGIES:
            if ranks[case["id"], strategy] <= 8:
                continue
            print(f"\n  case {case['id']} [{strategy}] {case['proposal']!r}  "
                  f"expected {case['expected_articles']}")
            for i, hit in enumerate(top8[case["id"], strategy], start=1):
                print(f"    {i}. {hit['score']:.3f}  {hit['chunk_id']:15s} {hit['title']}")

    save_results(args.run_name, cases, ranks, tops, metas)


if __name__ == "__main__":
    main()
