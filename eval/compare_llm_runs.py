"""Compare two run_eval.py runs on the same cases (e.g. k=8 vs k=10, prompt v1 vs v2).

Run:  .venv\\Scripts\\python eval\\compare_llm_runs.py BEFORE AFTER --out NAME [--show 51 ...]

Writes eval/results/<NAME>.md: config differences, metrics side by side,
average tokens per call, safety checks (compatible<->conflict confusions,
likely_compatible where it is not acceptable, compatible-expected cases that
turned unclear), per-case IMPROVEMENTS / REGRESSIONS at the label + reason
level, other changes, and the full answer for the cases given in --show.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
SHORT = {"likely_compatible": "compatible", "potential_conflict": "conflict", "unclear": "unclear"}
OPPOSITE = {"likely_compatible": "potential_conflict", "potential_conflict": "likely_compatible"}
CONFIG_KEYS = ("strategy", "k", "prefix_version", "prompt_version", "llm_model",
               "llm_model_version", "temperature", "query_rewriting")


def load(name):
    with open(RESULTS_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def ids(xs):
    return ", ".join(map(str, xs)) or "none"


def confusions(run):
    """Labelled compatible when conflict was expected, or the other way round."""
    return [c["id"] for c in run["cases"]
            if not c["label_ok"] and c["label"] in OPPOSITE
            and OPPOSITE[c["label"]] in c["acceptable_labels"]]


def compatible_not_acceptable(run):
    """likely_compatible given where it is not an acceptable label (the harmful error)."""
    return [c["id"] for c in run["cases"]
            if c["label"] == "likely_compatible" and "likely_compatible" not in c["acceptable_labels"]]


def compatible_expected_unclear(run):
    """Cases whose only acceptable label is likely_compatible, answered unclear."""
    return [c["id"] for c in run["cases"]
            if c["acceptable_labels"] == ["likely_compatible"] and c["label"] == "unclear"]


def cited(c):
    out = []
    for x in c["citations"]:
        out.append(str(x["article"]) + (f"/{x['n']}" if x.get("n") else "")
                   + (f"/{x['alinea']}" if x.get("alinea") else ""))
    return ", ".join(out) or "–"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--out", required=True)
    parser.add_argument("--show", type=int, nargs="*", default=[],
                        help="case ids to print in full (label, citations, summary, missing info)")
    args = parser.parse_args()
    a, b = load(args.before), load(args.after)
    sets = [s for s in a["metrics"] if s in b["metrics"]]
    ids_a, ids_b = [c["id"] for c in a["cases"]], [c["id"] for c in b["cases"]]
    if sorted(ids_a) != sorted(ids_b):
        sys.exit(f"Runs have different cases: {sorted(set(ids_a) ^ set(ids_b))}")
    by_id = {c["id"]: (c, next(x for x in b["cases"] if x["id"] == c["id"])) for c in a["cases"]}
    diffs = {k: (a["config"].get(k), b["config"].get(k)) for k in CONFIG_KEYS
             if a["config"].get(k) != b["config"].get(k)}

    L = [f"# Comparison: {args.before} → {args.after}", ""]
    for tag, name, run in (("before", args.before, a), ("after", args.after, b)):
        c = run["config"]
        L.append(f"- **{tag}** `{name}`: git `{run['git']['commit']}`"
                 f"{' (dirty)' if run['git']['dirty'] else ''}, {run['created_at']}, "
                 f"{c['strategy']} k={c['k']}, prompt `{c['prompt_version']}`, "
                 f"`{c['llm_model']}` ({c['llm_model_version']})")
    L.append("- Config differences: " + ("; ".join(f"{k}: {x} → {y}" for k, (x, y) in diffs.items())
                                         or "none"))
    L.append(f"- Sets compared: {', '.join(sets)} · {len(ids_a)} cases")
    L += ["", "## Metrics", "", "| Metric | before | after | Δ |", "|---|---|---|---|"]
    for s in sets:
        ma, mb = a["metrics"][s], b["metrics"][s]
        for label, key in (("Label accuracy", "label_accuracy"),
                           ("Label + reason accuracy", "label_and_reason_accuracy"),
                           ("Citation accuracy (conflict cases)", "citation_accuracy_conflict"),
                           ("Citation accuracy (all with expected art.)", "citation_accuracy_all"),
                           ("Unclear rate", "unclear_rate")):
            delta = (mb[key] - ma[key]) * 100 if None not in (ma[key], mb[key]) else None
            L.append(f"| {label} ({s}) | {pct(ma[key])} | {pct(mb[key])} | "
                     f"{'–' if delta is None else f'{delta:+.0f} pp'} |")
        L.append(f"| Rejected citations + references ({s}) | {ma['rejected_items']} | "
                 f"{mb['rejected_items']} | |")
    L.append(f"| compatible↔conflict confusions | {ids(confusions(a))} | {ids(confusions(b))} | |")
    L.append(f"| likely_compatible where not acceptable | {ids(compatible_not_acceptable(a))} | "
             f"{ids(compatible_not_acceptable(b))} | |")
    L.append(f"| compatible-expected cases answered unclear | {ids(compatible_expected_unclear(a))} | "
             f"{ids(compatible_expected_unclear(b))} | |")
    for field, label in (("input_tokens", "Avg input tokens / call"),
                         ("output_tokens", "Avg output tokens / call"),
                         ("total_tokens", "Avg total tokens / call")):
        ta = statistics.mean(c["usage"][field] for c in a["cases"])
        tb = statistics.mean(c["usage"][field] for c in b["cases"])
        L.append(f"| {label} | {ta:.0f} | {tb:.0f} | {100 * (tb - ta) / ta:+.0f}% |")

    imp = [i for i, (x, y) in by_id.items() if not x["label_and_reason_ok"] and y["label_and_reason_ok"]]
    reg = [i for i, (x, y) in by_id.items() if x["label_and_reason_ok"] and not y["label_and_reason_ok"]]
    L += ["", "## Improvements (label + reason wrong before, right after)", ""]
    for i in imp:
        x, y = by_id[i]
        L.append(f"- **{i}** {x['proposal']} — expected {x['expected_articles'] or '–'}: "
                 f"{SHORT[x['label']]} [{cited(x)}] → {SHORT[y['label']]} [{cited(y)}]")
    L.append("None." if not imp else "")
    L += ["## Regressions (label + reason right before, wrong after)", ""]
    for i in reg:
        x, y = by_id[i]
        L.append(f"- **{i}** {x['proposal']} — expected {x['expected_articles'] or '–'} "
                 f"(acceptable {[SHORT[l] for l in x['acceptable_labels']]}): "
                 f"{SHORT[x['label']]} [{cited(x)}] → {SHORT[y['label']]} [{cited(y)}]")
        L.append(f"  - after, summary: {y['summary']}")
        if y["missing_information"]:
            L.append(f"  - after, missing info: {y['missing_information']}")
    L.append("None." if not reg else "")

    other = [i for i, (x, y) in by_id.items()
             if i not in imp + reg and (x["label"] != y["label"] or cited(x) != cited(y))]
    L += ["## Other changes (same label + reason verdict; label or citations differ)", "",
          "| id | label before | label after | cited before | cited after |", "|---|---|---|---|---|"]
    for i in other:
        x, y = by_id[i]
        L.append(f"| {i} | {SHORT[x['label']]} | {SHORT[y['label']]} | {cited(x)} | {cited(y)} |")
    if not other:
        L.append("| – | | | | |")

    for i in args.show:
        x, y = by_id[i]
        L += ["", f"## Case {i}: {x['proposal']}", "",
              f"- Expected: {x['expected_articles'] or '–'}; acceptable: "
              f"{[SHORT[l] for l in x['acceptable_labels']]}"]
        for tag, c in (("before", x), ("after", y)):
            L.append(f"- **{tag}**: {SHORT[c['label']]} [{cited(c)}]")
            L.append(f"  - summary: {c['summary']}")
            L.append(f"  - missing info: {c['missing_information'] or '–'}")

    path = RESULTS_DIR / f"{args.out}.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
