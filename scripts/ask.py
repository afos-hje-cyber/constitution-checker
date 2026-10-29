"""Ask the Constitution Checker from the command line.

    .venv\\Scripts\\python scripts\\ask.py "Reintroduzir a pena de morte"
    .venv\\Scripts\\python scripts\\ask.py "..." --retrieval-only     # offline, 0 quota
    .venv\\Scripts\\python scripts\\ask.py "..." --strategy paragraph --k 5
    .venv\\Scripts\\python scripts\\ask.py "..." --show-prompt        # exact LLM prompt
    .venv\\Scripts\\python scripts\\ask.py "..." --json               # full result

Exit codes: 0 ok, 1 invalid input, 2 LLM unavailable.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# The embedding model is already in the local Hugging Face cache: never go
# online for it, and keep download/progress noise out of the output.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from common import config  # noqa: E402
from ingest.chunking import STRATEGIES  # noqa: E402

DISCLAIMER = "Ferramenta educativa, não constitui aconselhamento jurídico."


def cite_label(c):
    """{"article": 24, "n": 2, "alinea": None} -> 'Artigo 24.º, n.º 2'."""
    text = f"Artigo {c['article']}.º"
    if c.get("n"):
        text += f", n.º {c['n']}"
    if c.get("alinea"):
        text += f", alínea {c['alinea']})"
    return text


def print_hits(hits, strategy, k):
    print(f"\nRetrieved chunks ({strategy}, k={k}):")
    for i, h in enumerate(hits, start=1):
        print(f"  {i}. {h['score']:.3f}  {h['chunk_id']:15s} {h['title']}")


def print_prompt(user_prompt):
    path = config.PROMPTS_DIR / f"{config.PROMPT_VERSION}.md"
    print(f"\n----- SYSTEM PROMPT ({path.relative_to(ROOT)}) -----")
    print(path.read_text(encoding="utf-8"))
    print("----- USER PROMPT -----")
    print(user_prompt)
    print("----- END OF PROMPT -----")


def retrieval_only(args):
    """Retrieve and (optionally) show the prompt; no LLM client is created."""
    from rag.assess import build_user_prompt
    from rag.retrieve import load_index, retrieve

    hits = retrieve(args.proposal, args.strategy, args.k)
    if args.json:
        print(json.dumps({"proposal": args.proposal, "strategy": args.strategy, "k": args.k,
                          "retrieved": hits}, ensure_ascii=False, indent=2))
        return
    print(f"Proposal: {args.proposal}")
    print("Mode: retrieval only (no LLM call)")
    print_hits(hits, args.strategy, args.k)
    if args.show_prompt:
        prefix_version = load_index(args.strategy)[2]["prefix_version"]
        print_prompt(build_user_prompt(args.proposal, hits, prefix_version))


def full(args):
    from rag.assess import assess
    from rag.llm import LLMUnavailableError

    try:
        out = assess(args.proposal, args.strategy, args.k)
    except LLMUnavailableError as error:
        print(f"LLM unavailable: {error}\nTry again later, or use --retrieval-only.")
        sys.exit(2)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    r = out["result"]
    print(f"Proposal: {out['proposal']}")
    print(f"\nLabel:   {out['label_display']}  ({r['label']})")
    print(f"Summary: {r['summary']}")
    print(f"\nReasoning: {r['reasoning']}")
    print("\nCitations:")
    for c in r["citations"] or [{"article": None}]:
        if c["article"] is None:
            print("  (none)")
        else:
            print(f"  - {cite_label(c)}: {c['explanation']}")
    if r["missing_information"]:
        print(f"\nMissing information: {r['missing_information']}")
    for key in ("rejected_citations", "rejected_references"):
        for item in out[key]:
            print(f"  ! {key}: {cite_label(item)} — {item['reason']}")
    for note in out["validation_notes"]:
        print(f"  * {note}")

    print_hits(out["retrieved"], out["retrieval"]["strategy"], out["retrieval"]["k"])

    u = out["usage"]
    print(f"\nTokens: in {u['input_tokens']}, out {u['output_tokens']}, total {u['total_tokens']}"
          f"   Cache hit: {'yes (no API call)' if out['cached'] else 'no'}"
          f"   Time: {out['seconds']}s")
    print(f"Model: {out['model']} ({out['model_version']}), prompt {out['prompt_version']}")
    if args.show_prompt:
        print_prompt(out["user_prompt"])
    print(f"\n{DISCLAIMER}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description="Constitution Checker CLI")
    parser.add_argument("proposal", help="policy proposal, in Portuguese")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="only retrieve chunks; no LLM call (offline, 0 quota)")
    parser.add_argument("--strategy", choices=STRATEGIES, default=config.RETRIEVAL_STRATEGY)
    parser.add_argument("--k", type=int, default=config.RETRIEVAL_K)
    parser.add_argument("--show-prompt", action="store_true",
                        help="print the exact prompt sent to the LLM")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()

    args.proposal = args.proposal.strip()
    if not args.proposal or len(args.proposal) > config.MAX_PROPOSAL_CHARS:
        print(f"The proposal must have 1 to {config.MAX_PROPOSAL_CHARS} characters.")
        sys.exit(1)
    if args.k < 1:
        print("--k must be at least 1.")
        sys.exit(1)

    (retrieval_only if args.retrieval_only else full)(args)


if __name__ == "__main__":
    main()
