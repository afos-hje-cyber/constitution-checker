"""Reranker experiment on the dev set (retrieval only: no Gemini calls).

Run:  .venv\\Scripts\\python eval\\experiments\\rerank.py

Configs:
  A) hybrid k=8          (baseline)
  B) hybrid k=10
  C) hybrid top 30 -> cross-encoder rerank -> 8
  D) hybrid top 50 -> cross-encoder rerank -> 8

For each config: hit rate, mean rank / MRR of the first expected article,
latency per query on this CPU. Per case: the rank in each config, and
REGRESSIONS (hit in A, miss in the config). Also the process peak RAM with
e5 + the reranker loaded. Test cases are never loaded.
Output: eval/results/experiments/exp_rerank.{json,md}.
"""

import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
import psutil  # noqa: E402

from common import config  # noqa: E402
from rag.rerank import load_reranker, rerank_hits  # noqa: E402
from rag.retrieve import get_model, load_index, retrieve  # noqa: E402

CASES_PATH = ROOT / "eval" / "cases.json"
OUT = ROOT / "eval" / "results" / "experiments" / "exp_rerank"
DEPTH = 50          # hybrid candidates retrieved once per case
MISS_RANK = DEPTH + 1
CONFIGS = {
    "A": {"label": "hybrid k=8", "k": 8, "rerank_pool": None},
    "B": {"label": "hybrid k=10", "k": 10, "rerank_pool": None},
    "C": {"label": "rerank top 30 -> 8", "k": 8, "rerank_pool": 30},
    "D": {"label": "rerank top 50 -> 8", "k": 8, "rerank_pool": 50},
}


def mb(n_bytes):
    return round(n_bytes / 1e6)


def first_rank(hits, expected):
    return next((i for i, h in enumerate(hits, 1) if h["article"] in expected), None)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    proc = psutil.Process()
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = [c for c in json.load(f) if c["set"] == "dev" and c["expected_articles"]]

    # --- load models, measuring memory --------------------------------------
    ram = {"start": mb(proc.memory_info().rss)}
    get_model()
    load_index(config.RETRIEVAL_STRATEGY)
    ram["e5_loaded"] = mb(proc.memory_info().rss)
    reranker = load_reranker()
    ram["e5_and_reranker_loaded"] = mb(proc.memory_info().rss)

    # warm-up (first calls are slower: lazy initialisation)
    warm = retrieve("teste", config.RETRIEVAL_STRATEGY, DEPTH, rerank=False)
    rerank_hits("teste", warm, DEPTH)

    # --- run ---------------------------------------------------------------
    per_case, times = [], {"retrieve": [], "rerank30": [], "rerank50": []}
    for case in cases:
        t0 = time.perf_counter()
        pool = retrieve(case["proposal"], config.RETRIEVAL_STRATEGY, DEPTH, rerank=False)
        times["retrieve"].append(time.perf_counter() - t0)

        ranked = {}
        for name in ("30", "50"):
            n = int(name)
            t0 = time.perf_counter()
            ranked[name] = rerank_hits(case["proposal"], pool[:n], n)   # full reordering
            times[f"rerank{name}"].append(time.perf_counter() - t0)

        hybrid_rank = first_rank(pool, case["expected_articles"])
        ranks = {"A": hybrid_rank, "B": hybrid_rank,
                 "C": first_rank(ranked["30"], case["expected_articles"]),
                 "D": first_rank(ranked["50"], case["expected_articles"])}
        per_case.append({
            "id": case["id"], "proposal": case["proposal"],
            "expected_articles": case["expected_articles"], "ranks": ranks,
            "top8": {"A": [h["chunk_id"] for h in pool[:8]],
                     "C": [h["chunk_id"] for h in ranked["30"][:8]],
                     "D": [h["chunk_id"] for h in ranked["50"][:8]]},
        })
    ram["peak"] = mb(getattr(proc.memory_info(), "peak_wset", proc.memory_info().rss))

    # --- metrics -------------------------------------------------------------
    def hit(c, cfg):
        r = c["ranks"][cfg]
        return r is not None and r <= CONFIGS[cfg]["k"]

    mean_ms = {key: 1000 * statistics.mean(v) for key, v in times.items()}
    latency = {"A": mean_ms["retrieve"], "B": mean_ms["retrieve"],
               "C": mean_ms["retrieve"] + mean_ms["rerank30"],
               "D": mean_ms["retrieve"] + mean_ms["rerank50"]}
    added = {"A": 0.0, "B": 0.0, "C": mean_ms["rerank30"], "D": mean_ms["rerank50"]}
    summary = {}
    for cfg in CONFIGS:
        ranks = [c["ranks"][cfg] for c in per_case]
        summary[cfg] = {
            **CONFIGS[cfg],
            "hits": sum(hit(c, cfg) for c in per_case),
            "hit_rate": sum(hit(c, cfg) for c in per_case) / len(per_case),
            "hit_at_8": sum(1 for r in ranks if r is not None and r <= 8) / len(per_case),
            "mean_rank": statistics.mean(r or MISS_RANK for r in ranks),
            "mrr": statistics.mean(1 / r if r else 0 for r in ranks),
            "not_found": sum(r is None for r in ranks),
            "latency_ms": latency[cfg], "added_ms": added[cfg],
            "regressions": [c["id"] for c in per_case if hit(c, "A") and not hit(c, cfg)],
            "improvements": [c["id"] for c in per_case if not hit(c, "A") and hit(c, cfg)],
        }

    meta = {
        "experiment": "rerank",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": len(per_case), "set": "dev",
        "reranker": {"model": reranker.hf_name, "revision": reranker.hf_revision},
        "embedding_revision": load_index(config.RETRIEVAL_STRATEGY)[2]["revision"],
        "cpu": {"processor": platform.processor(), "logical_cores": os.cpu_count(),
                "torch_threads": __import__("torch").get_num_threads()},
        "ram_mb": ram,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(f"{OUT}.json", "w", encoding="utf-8") as f:
        json.dump({**meta, "summary": summary, "per_case": per_case}, f,
                  ensure_ascii=False, indent=2)
    write_report(meta, summary, per_case)
    print(Path(f"{OUT}.md").read_text(encoding="utf-8"))


def write_report(meta, summary, per_case):
    def r(x, cfg="A"):
        """Rank, or '>N' where N is how deep this config can see."""
        return str(x) if x else f">{CONFIGS[cfg]['rerank_pool'] or DEPTH}"

    L = ["# Experiment: cross-encoder reranking (dev, retrieval only)", "",
         f"- Date: {meta['created_at']} · {meta['cases']} dev cases · no Gemini calls",
         f"- Reranker: `{meta['reranker']['model']}` @ `{meta['reranker']['revision'][:12]}` "
         f"(safetensors, no remote code)",
         f"- CPU: {meta['cpu']['processor']} · {meta['cpu']['logical_cores']} logical cores · "
         f"torch threads {meta['cpu']['torch_threads']}",
         f"- RAM (process): start {meta['ram_mb']['start']} MB · e5 + index "
         f"{meta['ram_mb']['e5_loaded']} MB · + reranker {meta['ram_mb']['e5_and_reranker_loaded']} MB"
         f" · **peak {meta['ram_mb']['peak']} MB**", "",
         "## Summary", "",
         "| Config | Hit rate | Mean rank* | MRR | Not found | Latency / query | Added by rerank | Regressions vs A | Improvements vs A |",
         "|---|---|---|---|---|---|---|---|---|"]
    for cfg, s in summary.items():
        at = f"@{s['k']}"
        L.append(f"| {cfg}) {s['label']} | {s['hits']}/{meta['cases']} ({100 * s['hit_rate']:.0f}%) {at} "
                 f"| {s['mean_rank']:.1f} | {s['mrr']:.2f} | {s['not_found']} "
                 f"| {s['latency_ms']:.0f} ms | {s['added_ms']:.0f} ms "
                 f"| {', '.join(map(str, s['regressions'])) or '–'} "
                 f"| {', '.join(map(str, s['improvements'])) or '–'} |")
    L += ["", f"*Rank of the first expected article; not found counts as {MISS_RANK}. "
          f"A and B share the same hybrid ranking (top {DEPTH}; only k differs). C reorders "
          f"the hybrid top 30 and D the top 50, so they cannot find anything below that.", "",
          "## Regressions (hit in A, miss in the config)", ""]
    any_reg = False
    for cfg, s in summary.items():
        for cid in s["regressions"]:
            any_reg = True
            c = next(c for c in per_case if c["id"] == cid)
            L.append(f"- **{cfg}**, case {cid}: {c['proposal']} — expected "
                     f"{c['expected_articles']}, rank A={r(c['ranks']['A'])} → "
                     f"{cfg}={r(c['ranks'][cfg], cfg)}; {cfg} top 8: "
                     f"{', '.join(x.removeprefix('art') for x in c['top8'].get(cfg, []))}")
    if not any_reg:
        L.append("None.")
    L += ["", "## Per case (rank of the first expected article)", "",
          "| id | proposal | expected | A | B | C | D |", "|---|---|---|---|---|---|---|"]
    for c in per_case:
        prop = c["proposal"] if len(c["proposal"]) <= 45 else c["proposal"][:43] + "…"
        cells = []
        for cfg in CONFIGS:
            rank = c["ranks"][cfg]
            ok = rank is not None and rank <= CONFIGS[cfg]["k"]
            cells.append(f"{r(rank, cfg)}{'' if ok else ' ✘'}")
        L.append(f"| {c['id']} | {prop} | {','.join(map(str, c['expected_articles']))} | "
                 + " | ".join(cells) + " |")
    Path(f"{OUT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
