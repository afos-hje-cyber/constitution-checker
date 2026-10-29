"""Embed the chunks of each strategy with multilingual-e5-small and save them.

Run:  .venv\\Scripts\\python scripts\\build_index.py                 (all strategies)
      .venv\\Scripts\\python scripts\\build_index.py --strategy hybrid

For each strategy this writes, in data/processed/:
  index_<strategy>_e5small.npy        float32 matrix, one normalised row per chunk
  chunks_<strategy>.json              the chunks, in the same order as the rows
  index_<strategy>_e5small.meta.json  model, revision, prefixes, counts, ...
The app must refuse to start if its model does not match the metadata.

The embedding model itself (pinned revision, safetensors only, never
trust_remote_code) is defined in common/embeddings.py, shared with retrieval.
"""

import argparse
import json
import random
import time
from datetime import datetime, timezone

import numpy as np
import sentence_transformers

from common import config
from common.embeddings import MODEL, load_model
from ingest.chunking import (DEFAULT_MAX_WORDS, DEFAULT_PREFIX_VERSION, PREFIX_VERSIONS,
                             STRATEGIES, load_articles, make_chunks)

OUT_DIR = config.PROCESSED_DIR


def token_counter(model):
    """Count tokens exactly as the model sees them (prefix + special tokens)."""
    def count(text):
        return len(model.tokenizer(MODEL["passage_prefix"] + text)["input_ids"])
    return count


def embed(model, texts):
    return model.encode(
        [MODEL["passage_prefix"] + t for t in texts],
        batch_size=32,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).astype(np.float32)


def build(model, articles, strategy, prefix_version):
    count_tokens = token_counter(model)
    chunks = make_chunks(articles, strategy, length_fn=count_tokens,
                         prefix_version=prefix_version)
    for c in chunks:
        c["tokens"] = count_tokens(c["text"])

    start = time.perf_counter()
    vectors = embed(model, [c["text"] for c in chunks])
    seconds = time.perf_counter() - start

    truncated = [{"chunk_id": c["chunk_id"], "tokens": c["tokens"]}
                 for c in chunks if c["tokens"] > MODEL["max_seq_length"]]
    meta = {
        "model": model.hf_name,
        "revision": model.hf_revision,
        "strategy": strategy,
        "prefix_version": prefix_version,
        "passage_prefix": MODEL["passage_prefix"],
        "query_prefix": MODEL["query_prefix"],
        "normalised": True,
        "chunk_count": len(chunks),
        "dimension": int(vectors.shape[1]),
        "max_seq_length": MODEL["max_seq_length"],
        "hybrid_max_words": DEFAULT_MAX_WORDS if strategy == "hybrid" else None,
        "truncated_chunks": truncated,
        "sentence_transformers_version": sentence_transformers.__version__,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    stem = f"index_{strategy}_{MODEL['short']}"
    np.save(OUT_DIR / f"{stem}.npy", vectors)
    with open(OUT_DIR / f"chunks_{strategy}.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / f"{stem}.meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return seconds


def validate(model, strategy):
    """Reload the saved files and check them. Raises AssertionError on failure."""
    stem = f"index_{strategy}_{MODEL['short']}"
    vectors = np.load(OUT_DIR / f"{stem}.npy")
    with open(OUT_DIR / f"chunks_{strategy}.json", encoding="utf-8") as f:
        chunks = json.load(f)
    with open(OUT_DIR / f"{stem}.meta.json", encoding="utf-8") as f:
        meta = json.load(f)

    over = [c["chunk_id"] for c in chunks if c["tokens"] > MODEL["max_seq_length"]]
    if strategy != "article":
        assert not over, f"chunks over {MODEL['max_seq_length']} tokens: {over}"
    assert [t["chunk_id"] for t in meta["truncated_chunks"]] == over

    assert vectors.shape[0] == len(chunks) == meta["chunk_count"], "count mismatch"
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "duplicate chunk ids"

    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4), f"norms in [{norms.min()}, {norms.max()}]"

    sample = random.Random(42).sample(range(len(chunks)), 3)
    fresh = embed(model, [chunks[i]["text"] for i in sample])
    cosines = (fresh * vectors[sample]).sum(axis=1)   # both normalised -> dot = cosine
    assert np.all(cosines > 0.9999), f"re-embed cosines {cosines}"

    return {
        "vectors": vectors.shape,
        "max_tokens": max(c["tokens"] for c in chunks),
        "truncated": over,
        "norm_range": (float(norms.min()), float(norms.max())),
        "reembed": {chunks[i]["chunk_id"]: round(float(c), 6) for i, c in zip(sample, cosines)},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=STRATEGIES, help="default: all")
    parser.add_argument("--prefix-version", choices=PREFIX_VERSIONS,
                        default=DEFAULT_PREFIX_VERSION)
    args = parser.parse_args()
    strategies = [args.strategy] if args.strategy else list(STRATEGIES)

    start = time.perf_counter()
    model = load_model()
    print(f"Model loaded in {time.perf_counter() - start:.1f}s")

    articles = load_articles()
    for strategy in strategies:
        seconds = build(model, articles, strategy, args.prefix_version)
        report = validate(model, strategy)
        print(f"\n[{strategy}] embedded in {seconds:.1f}s")
        for key, value in report.items():
            print(f"  {key}: {value}")
        print("  validation: PASS")


if __name__ == "__main__":
    main()
