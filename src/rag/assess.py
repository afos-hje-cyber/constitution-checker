"""Assess a policy proposal against the retrieved constitutional articles.

    from rag.assess import assess
    out = assess("Reintroduzir a pena de morte")
    out["result"]["label"]        # likely_compatible | potential_conflict | unclear

Pipeline: retrieve (config: hybrid, k=10) -> user prompt with one labelled block per
chunk -> LLM (JSON) -> validation in code (see validation.py). Validation runs
after the cache, so changing it never costs API calls.
"""

import re

from common import config
from ingest.chunking import make_prefix
from rag.llm import LLMClient
from rag.retrieve import load_index, retrieve
from rag.validation import check_structure, validate_output

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": list(config.LABELS)},
        "summary": {"type": "string"},
        "reasoning": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article": {"type": "integer"},
                    "n": {"type": ["integer", "null"]},
                    "alinea": {"type": ["string", "null"]},
                    "explanation": {"type": "string"},
                },
                "required": ["article", "n", "alinea", "explanation"],
            },
        },
        "missing_information": {"type": ["string", "null"]},
    },
    "required": ["label", "summary", "reasoning", "citations", "missing_information"],
}

_clients = {}   # prompt version -> (LLMClient, system prompt text), created on first use


def _setup(prompt_version=None):
    """Client + system prompt for a prompt version (default: config.PROMPT_VERSION).

    The prompt version is part of the LLM cache key, so answers from one
    version are never reused for another.
    """
    version = prompt_version or config.PROMPT_VERSION
    if version not in _clients:
        path = config.PROMPTS_DIR / f"{version}.md"
        _clients[version] = (LLMClient.from_config(prompt_version=version),
                             path.read_text(encoding="utf-8"))
    return _clients[version]


def get_client(prompt_version=None):
    """The shared LLMClient for a prompt version (created on first use)."""
    return _setup(prompt_version)[0]


def get_system_prompt(prompt_version=None):
    """The system prompt text for a prompt version."""
    return _setup(prompt_version)[1]


# ---------------------------------------------------------------- prompt

def chunk_block(hit, prefix_version):
    """'[Artigo 24.º, n.º 2 — Direito à vida]\\n<text>' for one retrieved chunk."""
    alineas = tuple(hit["alineas"].split("-")) if hit["alineas"] else None
    prefix = make_prefix({"number": hit["article"], "title": hit["title"]},
                         hit["paragraph"], alineas, prefix_version)
    assert hit["text"].startswith(prefix), hit["chunk_id"]
    header = prefix.removesuffix(": ")
    return f"[{header}]\n{hit['text'][len(prefix):]}"


def build_user_prompt(proposal, hits, prefix_version):
    # The proposal is user data: remove anything that could close our tags.
    clean = re.sub(r"</?\s*proposta\s*>", "", proposal, flags=re.I).strip()
    blocks = "\n\n".join(chunk_block(h, prefix_version) for h in hits)
    return (f"Excertos da Constituição (usa apenas estes):\n\n{blocks}\n\n"
            f"<proposta>\n{clean}\n</proposta>")


# ---------------------------------------------------------------- assess

def assess(proposal, strategy=config.RETRIEVAL_STRATEGY, k=config.RETRIEVAL_K,
           before_api_call=None, prompt_version=None):
    """before_api_call: run before every real LLM request (not on cache hits);
    the app uses it to enforce the usage caps.
    prompt_version: system prompt file in src/rag/prompts/ (default config.PROMPT_VERSION)."""
    prompt_version = prompt_version or config.PROMPT_VERSION
    proposal = proposal.strip()
    if not proposal:
        raise ValueError("empty proposal")
    if len(proposal) > config.MAX_PROPOSAL_CHARS:
        raise ValueError(f"proposal longer than {config.MAX_PROPOSAL_CHARS} characters")

    client, system_prompt = _setup(prompt_version)
    meta = load_index(strategy)[2]
    hits = retrieve(proposal, strategy, k)
    user_prompt = build_user_prompt(proposal, hits, meta["prefix_version"])

    llm = client.generate_json(system_prompt, user_prompt, schema=SCHEMA,
                               validate=check_structure, before_api_call=before_api_call)
    result, rejected_citations, rejected_references, notes = validate_output(llm.data, hits)

    return {
        "proposal": proposal,
        "result": result,
        "label_display": config.LABELS[result["label"]],
        "rejected_citations": rejected_citations,
        "rejected_references": rejected_references,
        "validation_notes": notes,
        "raw_llm_output": llm.data,
        "user_prompt": user_prompt,   # exactly what was sent (system prompt: PROMPT_VERSION file)
        "retrieved": [{k_: h[k_] for k_ in ("chunk_id", "article", "paragraph", "alineas",
                                            "score", "title")}
                      for h in hits],
        "usage": llm.usage,
        "cached": llm.cached,
        "attempts": llm.attempts,
        "seconds": round(llm.seconds, 2),
        "provider": config.PROVIDER,
        "model": llm.model,
        "model_version": llm.model_version,
        "response_model_version": llm.response_model_version,
        "prompt_version": prompt_version,
        "retrieval": {"strategy": strategy, "k": k,
                      "prefix_version": meta["prefix_version"]},
    }
