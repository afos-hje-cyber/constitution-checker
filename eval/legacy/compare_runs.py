"""Compare saved retrieval runs against the CURRENT eval cases.

Run:  .venv\\Scripts\\python eval\\legacy\\compare_runs.py v1_basic_prefix v2_hierarchy_prefix

If a case's expected articles changed after a run was made, that run is
re-scored from its saved top-20 list (ranks beyond 20 show as ">20"), so all
runs are judged on the same cases.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "eval" / "legacy" / "retrieval_cases.json"
RESULTS_DIR = ROOT / "eval" / "results" / "experiments"
STRATEGIES = ("article", "paragraph", "hybrid")
KS = (5, 8)
BEYOND = 10**6   # stands for "not in the saved top 20"


def ranks_for(run, cases):
    """{(case id, strategy): rank} judged with the current expected articles."""
    stored_cases = {c["id"]: c for c in run["cases"]}
    out = {}
    for case in cases:
        cid = str(case["id"])
        same = stored_cases[case["id"]]["expected_articles"] == case["expected_articles"]
        for s in STRATEGIES:
            if same:
                out[case["id"], s] = run["ranks"][cid][s]
            else:
                top = run["top"][cid][s]
                hit = [i for i, h in enumerate(top, 1) if h["article"] in case["expected_articles"]]
                out[case["id"], s] = hit[0] if hit else BEYOND
    return out


def fmt(rank):
    return ">20" if rank == BEYOND else str(rank)


def main(names):
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    runs = {}
    for name in names:
        with open(RESULTS_DIR / f"retrieval_{name}.json", encoding="utf-8") as f:
            runs[name] = ranks_for(json.load(f), cases)

    print("Hit rate (current cases)")
    header = f"{'strategy':10s} {'k':>3s}" + "".join(f"{n:>22s}" for n in names)
    print(header)
    for s in STRATEGIES:
        for k in KS:
            row = f"{s:10s} {k:3d}"
            for n in names:
                hits = sum(runs[n][c["id"], s] <= k for c in cases)
                row += f"{f'{hits}/{len(cases)} ({100 * hits / len(cases):.0f}%)':>22s}"
            print(row)

    print("\nRank of first expected article (" + " -> ".join(names) + ")")
    print(f"{'case':4s}" + "".join(f"{s:>18s}" for s in STRATEGIES))
    for c in cases:
        cells = ""
        for s in STRATEGIES:
            cells += f"{' -> '.join(fmt(runs[n][c['id'], s]) for n in names):>18s}"
        print(f"{c['id']:4d}{cells}")


if __name__ == "__main__":
    main(sys.argv[1:])
