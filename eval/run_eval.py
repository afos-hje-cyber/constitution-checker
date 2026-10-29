"""Full evaluation: retrieval (free) + LLM assessment, with a Markdown report.

Run:  .venv\\Scripts\\python eval\\run_eval.py --run-name baseline_v1

  a) Retrieval: rank of the first expected article in the hybrid top 30;
     hit rate @5/@8/@10/@12, dev and test separately. No API.
  b) LLM: assess() on every case with the default config. Answers come from
     the cache when possible; if more than --max-api-calls real calls would
     be needed, the script stops before making any.
  c-d) Per-case results and metrics (label accuracy, citation accuracy,
     unclear rate, confusion table, API calls), dev and test separately.
  e) eval/results/<name>.json (everything) and eval/results/<name>.md
     (compact, for pasting into a chat).
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from common import config  # noqa: E402
from rag.assess import assess, build_user_prompt, get_client, get_system_prompt  # noqa: E402
from common.embeddings import MODEL as EMBEDDING_MODEL  # noqa: E402
from rag.retrieve import load_index, retrieve  # noqa: E402

CASES_PATH = ROOT / "eval" / "cases.json"
FREEZES_PATH = ROOT / "eval" / "freezes.json"
RESULTS_DIR = ROOT / "eval" / "results"
SETS = ("dev", "test")
RANK_DEPTH = 30
HIT_KS = (5, 8, 10, 12)
LABEL_ORDER = ("likely_compatible", "potential_conflict", "unclear")
SHORT = {"likely_compatible": "compatible", "potential_conflict": "conflict", "unclear": "unclear"}


# ------------------------------------------------------------------ helpers

def git_state():
    """Commit hash and whether the working tree had uncommitted changes."""
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip()
    return {"commit": run("rev-parse", "--short", "HEAD"),
            "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


def expected_row(case):
    """Row of the confusion table: the expected label, or 'borderline'."""
    labels = case["acceptable_labels"]
    return labels[0] if len(labels) == 1 else "borderline"


def cite_str(c):
    """24/2 = art. 24.º n.º 2; 81/m = art. 81.º alínea m); 227/1/a = both."""
    text = str(c["article"])
    if c.get("n"):
        text += f"/{c['n']}"
    if c.get("alinea"):
        text += f"/{c['alinea']}"
    return text


def freeze_times(cases, freezes):
    """{case id: frozen_at} from eval/freezes.json.

    Raises ValueError if a case is in no batch, in two batches, or a batch
    lists an id that is not in cases.json.
    """
    frozen_at = {}
    for batch in freezes:
        for cid in batch["ids"]:
            if cid in frozen_at:
                raise ValueError(f"case {cid} appears in two freeze batches")
            frozen_at[cid] = batch["frozen_at"].replace("Z", "+00:00")
    case_ids = {c["id"] for c in cases}
    missing = sorted(case_ids - frozen_at.keys())
    if missing:
        raise ValueError(f"cases missing from eval/freezes.json: {missing}")
    unknown = sorted(frozen_at.keys() - case_ids)
    if unknown:
        raise ValueError(f"eval/freezes.json lists unknown case ids: {unknown}")
    return frozen_at


def label_and_reason_ok(label, acceptable_labels, expected_articles, cited_articles):
    """Right label AND right reason: when articles are expected, at least one
    of them must be among the cited articles."""
    if label not in acceptable_labels:
        return False
    return not expected_articles or any(a in cited_articles for a in expected_articles)


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def ratio(num, den):
    return None if den == 0 else num / den


# ---------------------------------------------------------------- retrieval

def retrieval_ranks(cases):
    """{case id: rank of first expected article in top RANK_DEPTH, or None}."""
    ranks = {}
    for case in cases:
        if not case["expected_articles"]:
            continue
        hits = retrieve(case["proposal"], config.RETRIEVAL_STRATEGY, RANK_DEPTH)
        ranks[case["id"]] = next((i for i, h in enumerate(hits, 1)
                                  if h["article"] in case["expected_articles"]), None)
    return ranks


# ---------------------------------------------------------------------- LLM

def cache_paths(cases, k, prompt_version):
    """{case id: path of the LLM cache entry its assessment uses (may not exist yet)}."""
    client = get_client(prompt_version)
    system_prompt = get_system_prompt(prompt_version)
    prefix_version = load_index(config.RETRIEVAL_STRATEGY)[2]["prefix_version"]
    paths = {}
    for case in cases:
        hits = retrieve(case["proposal"], config.RETRIEVAL_STRATEGY, k)
        user_prompt = build_user_prompt(case["proposal"], hits, prefix_version)
        paths[case["id"]] = client.cache_dir / f"{client.cache_key(system_prompt, user_prompt)}.json"
    return paths


def answer_created_at(path):
    """When the cached answer was first produced by the API (provenance)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["created_at"]


def run_case(case, rank, guard, k, prompt_version):
    out = assess(case["proposal"], k=k, before_api_call=guard, prompt_version=prompt_version)
    r = out["result"]
    cited = sorted({c["article"] for c in r["citations"]})
    expected = case["expected_articles"]
    return {
        **case,
        "rank": rank,
        "label": r["label"],
        "label_ok": r["label"] in case["acceptable_labels"],
        "label_and_reason_ok": label_and_reason_ok(r["label"], case["acceptable_labels"],
                                                   expected, cited),
        "citations": r["citations"],
        "cited_articles": cited,
        "expected_cited": (any(a in cited for a in expected) if expected else None),
        "summary": r["summary"],
        "missing_information": r["missing_information"],
        "rejected_citations": out["rejected_citations"],
        "rejected_references": out["rejected_references"],
        "validation_notes": out["validation_notes"],
        "usage": out["usage"],
        "cached": out["cached"],
        "attempts": out["attempts"],   # >1 = answer re-requested after invalid JSON
        "top_retrieved": [{"chunk_id": h["chunk_id"], "article": h["article"],
                  "score": round(h["score"], 4)} for h in out["retrieved"]],
    }


# ------------------------------------------------------------------ metrics

def metrics_for(results, ranks, api_calls):
    with_expected = [r for r in results if r["expected_articles"]]
    conflict = [r for r in with_expected if r["acceptable_labels"] == ["potential_conflict"]]
    m = {
        "cases": len(results),
        "retrieval_cases": len(with_expected),
        "hit_rate": {f"@{k}": ratio(sum(1 for r in with_expected
                                         if ranks[r["id"]] is not None and ranks[r["id"]] <= k),
                                     len(with_expected)) for k in HIT_KS},
        "label_accuracy": ratio(sum(r["label_ok"] for r in results), len(results)),
        "label_and_reason_accuracy": ratio(sum(r["label_and_reason_ok"] for r in results),
                                           len(results)),
        "citation_accuracy_conflict": ratio(sum(r["expected_cited"] for r in conflict),
                                            len(conflict)),
        "conflict_cases": len(conflict),
        "citation_accuracy_all": ratio(sum(r["expected_cited"] for r in with_expected),
                                       len(with_expected)),
        "unclear_rate": ratio(sum(r["label"] == "unclear" for r in results), len(results)),
        "rejected_items": sum(len(r["rejected_citations"]) + len(r["rejected_references"])
                              for r in results),
        "api_calls": api_calls,
    }
    confusion = {}
    for r in results:
        row = confusion.setdefault(expected_row(r), {**{l: 0 for l in LABEL_ORDER}, "hits": 0})
        row[r["label"]] += 1
        row["hits"] += r["label_ok"]
    m["confusion"] = confusion
    return m


# ------------------------------------------------------------------- report

def is_failure(r, k):
    return (not r["label_ok"] or r["expected_cited"] is False
            or (r["expected_articles"] and (r["rank"] is None or r["rank"] > k)))


def write_report(path, meta, metrics, results):
    L = []
    L.append(f"# Evaluation report: {meta['run']}")
    L.append("")
    L.append(f"- Date: {meta['created_at']} · git `{meta['git']['commit']}`"
             f"{' (uncommitted changes)' if meta['git']['dirty'] else ''}")
    c = meta["config"]
    L.append(f"- Retrieval: {c['strategy']}, k={c['k']}, prefix `{c['prefix_version']}`, "
             f"embeddings `{c['embedding_model']}`")
    L.append(f"- LLM: `{c['llm_model']}` (version `{c['llm_model_version']}`), "
             f"temperature {c['temperature']}, prompt `{c['prompt_version']}`")
    L.append(f"- API calls in this invocation: {meta['api_calls_total']} "
             f"(cache hits: {meta['cache_hits_total']})")
    L.append("- Answers first produced by the API on: " + ", ".join(
        f"{day} ({n})" for day, n in meta["answer_provenance"].items()))
    L.append("- Answer key frozen (eval/freezes.json): " + "; ".join(
        f"batch {b['batch']} at {b['frozen_at']} ({len(b['ids'])} cases)" for b in meta["freezes"]))
    if meta["answers_before_freeze"]:
        L.append(f"- ⚠ Answers produced before their case was frozen (seen before the key was "
                 f"fixed): cases {', '.join(map(str, meta['answers_before_freeze']))}")
    L.append(f"- Sets in this run: {', '.join(meta['sets'])}")
    L.append("")
    L.append("## Metrics")
    L.append("")
    sets = meta["sets"]
    L.append("| Metric | " + " | ".join(sets) + " |")
    L.append("|---|" + "---|" * len(sets))

    def row(name, fn):
        L.append(f"| {name} | " + " | ".join(fn(metrics[s]) for s in sets) + " |")

    row("Cases", lambda m: str(m["cases"]))
    for k in HIT_KS:
        row(f"Retrieval hit @{k}", lambda m, k=k: pct(m["hit_rate"][f"@{k}"]))
    row("Label accuracy", lambda m: pct(m["label_accuracy"]))
    row("Label + reason accuracy", lambda m: pct(m["label_and_reason_accuracy"]))
    row("Citation accuracy (conflict cases)",
        lambda m: f"{pct(m['citation_accuracy_conflict'])} (n={m['conflict_cases']})")
    row("Citation accuracy (all with expected art.)", lambda m: pct(m["citation_accuracy_all"]))
    row("Unclear rate", lambda m: pct(m["unclear_rate"]))
    row("Rejected citations + references", lambda m: str(m["rejected_items"]))
    row("API calls (this invocation)", lambda m: str(m["api_calls"]))
    L.append("")
    L.append("Confusion (rows = expected, columns = given; hits = label in acceptable_labels):")
    L.append("")
    L.append("| set | expected | compatible | conflict | unclear | hits |")
    L.append("|---|---|---|---|---|---|")
    for s in sets:
        for row in (*LABEL_ORDER, "borderline"):
            if row in metrics[s]["confusion"]:
                x = metrics[s]["confusion"][row]
                total = sum(x[l] for l in LABEL_ORDER)
                L.append(f"| {s} | {SHORT.get(row, row)} | {x['likely_compatible']} | "
                         f"{x['potential_conflict']} | {x['unclear']} | {x['hits']}/{total} |")
    L.append("")
    L.append("## Cases")
    L.append("")
    L.append("Rank = first expected article in hybrid top 30 (– = none expected, >30 = miss). "
             "Cited: article/n.º/alínea.")
    L.append("")
    L.append("| id | set | proposal | exp. art. | rank | label | ok | cited |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        prop = r["proposal"] if len(r["proposal"]) <= 50 else r["proposal"][:48] + "…"
        exp = ",".join(map(str, r["expected_articles"])) or "–"
        rank = "–" if not r["expected_articles"] else (str(r["rank"]) if r["rank"] else ">30")
        ok = "✔" if r["label_ok"] else "✘"
        if r["expected_cited"] is False:
            ok += " (no exp. cit.)"
        cited = ", ".join(cite_str(c) for c in r["citations"]) or "–"
        L.append(f"| {r['id']} | {r['set']} | {prop} | {exp} | {rank} | "
                 f"{SHORT[r['label']]} | {ok} | {cited} |")
    L.append("")
    L.append("## Failures")
    L.append("")
    k = meta["config"]["k"]
    L.append(f"Wrong label, expected article not cited, or retrieval miss @{k}.")
    fails = [r for r in results if is_failure(r, k)]
    if not fails:
        L.append("")
        L.append("None.")
    for r in fails:
        why = []
        if not r["label_ok"]:
            why.append(f"label {SHORT[r['label']]} not in "
                       f"{[SHORT[l] for l in r['acceptable_labels']]}")
        if r["expected_cited"] is False:
            why.append("expected article not cited")
        if r["expected_articles"] and (r["rank"] is None or r["rank"] > k):
            why.append(f"retrieval miss @{k} (rank {r['rank'] or '>30'})")
        L.append("")
        L.append(f"### {r['id']} ({r['set']}): {r['proposal']}")
        L.append(f"- Why: {'; '.join(why)}. Expected art.: "
                 f"{', '.join(map(str, r['expected_articles'])) or '–'}")
        L.append(f"- Top {k}: " + ", ".join(f"{h['chunk_id'].removeprefix('art')} "
                                            f"({h['score']:.3f})" for h in r["top_retrieved"]))
        L.append(f"- Summary: {r['summary']}")
        if r["missing_information"]:
            L.append(f"- Missing info: {r['missing_information']}")
        if r["rejected_citations"] or r["rejected_references"]:
            rej = [f"{x['article']}" + (f"/{x['n']}" if x.get('n') else "")
                   for x in r["rejected_citations"] + r["rejected_references"]]
            L.append(f"- Rejected: {', '.join(rej)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return len(L)


# --------------------------------------------------------------------- main

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--max-api-calls", type=int, default=60)
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing run with the same name")
    parser.add_argument("--k", type=int, default=config.RETRIEVAL_K,
                        help="number of chunks given to the LLM (default: config.RETRIEVAL_K)")
    parser.add_argument("--prompt", default=config.PROMPT_VERSION,
                        help="system prompt version in src/prompts/ (default: config.PROMPT_VERSION)")
    parser.add_argument("--set", choices=("dev", "test", "all"), default="all",
                        help="evaluate only this set (the other is not run or printed)")
    args = parser.parse_args()

    if (RESULTS_DIR / f"{args.run_name}.json").exists() and not args.overwrite:
        sys.exit(f"Run {args.run_name!r} already exists; pick a new name or pass --overwrite.")

    with open(CASES_PATH, encoding="utf-8") as f:
        all_cases = json.load(f)
    with open(FREEZES_PATH, encoding="utf-8") as f:
        freezes = json.load(f)
    frozen_at = freeze_times(all_cases, freezes)   # fails if any case is not frozen exactly once
    sets = SETS if args.set == "all" else (args.set,)
    cases = sorted((c for c in all_cases if c["set"] in sets),
                   key=lambda c: (SETS.index(c["set"]), c["id"]))

    print("a) Retrieval ranks (no API)…")
    ranks = retrieval_ranks(cases)

    paths = cache_paths(cases, args.k, args.prompt)
    missing = [cid for cid, p in paths.items() if not p.exists()]
    print(f"b) LLM: {len(cases) - len(missing)} cases cached, {len(missing)} need an API call")
    if len(missing) > args.max_api_calls:
        sys.exit(f"STOP: {len(missing)} real API calls needed, more than "
                 f"--max-api-calls={args.max_api_calls}. Nothing was sent.")

    client = get_client(args.prompt)
    calls_by_set = Counter()
    results = []
    for case in cases:
        def guard(case=case):   # hard stop, in case the estimate was wrong
            if client.stats["api_calls"] >= args.max_api_calls:
                raise RuntimeError(f"more than {args.max_api_calls} API calls")
            calls_by_set[case["set"]] += 1
        r = run_case(case, ranks.get(case["id"]), guard, args.k, args.prompt)
        r["answer_created_at"] = answer_created_at(paths[case["id"]])
        # Answer produced before this case was frozen = seen before its key was fixed.
        r["frozen_at"] = frozen_at[case["id"]]
        r["answer_before_freeze"] = (datetime.fromisoformat(r["answer_created_at"])
                                     < datetime.fromisoformat(r["frozen_at"]))
        results.append(r)
        print(f"   {r['id']:>2} {r['set']:4s} {SHORT[r['label']]:10s} "
              f"{'ok ' if r['label_ok'] else 'BAD'} {'cache' if r['cached'] else 'API'}")

    metrics = {s: metrics_for([r for r in results if r["set"] == s], ranks, calls_by_set[s])
               for s in sets}
    meta_index = load_index(config.RETRIEVAL_STRATEGY)[2]
    meta = {
        "run": args.run_name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "config": {
            "strategy": config.RETRIEVAL_STRATEGY, "k": args.k,
            "rank_depth": RANK_DEPTH, "prefix_version": meta_index["prefix_version"],
            "embedding_model": EMBEDDING_MODEL["name"],
            "embedding_revision": meta_index["revision"],
            "llm_provider": config.PROVIDER, "llm_model": config.MODEL,
            "llm_model_version": config.MODEL_VERSION, "temperature": config.TEMPERATURE,
            "prompt_version": args.prompt, "query_rewriting": None,
        },
        "api_calls_total": client.stats["api_calls"],
        "cache_hits_total": client.stats["cache_hits"],
        "transport_retries": client.stats["transport_retries"],
        "output_retries": client.stats["output_retries"],
        "sets": list(sets),
        "freezes": [{"batch": b["batch"], "frozen_at": b["frozen_at"], "ids": b["ids"]}
                    for b in freezes],
        "answer_provenance": dict(sorted(Counter(r["answer_created_at"][:10]
                                                 for r in results).items())),
        "answers_before_freeze": [r["id"] for r in results if r["answer_before_freeze"]],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / f"{args.run_name}.json", "w", encoding="utf-8") as f:
        json.dump({**meta, "metrics": metrics, "cases": results}, f, ensure_ascii=False, indent=2)
    n_lines = write_report(RESULTS_DIR / f"{args.run_name}.md", meta, metrics, results)
    print(f"Saved eval/results/{args.run_name}.json and eval/results/{args.run_name}.md "
          f"({n_lines} lines). API calls: {meta['api_calls_total']}")


if __name__ == "__main__":
    main()
