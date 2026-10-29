"""Token-length statistics of the chunks, per strategy and per model.

Run:  .venv\\Scripts\\python eval\\experiments\\token_stats.py

Only the TOKENIZERS are downloaded (a few MB each), never the model weights.
Token counts include the special tokens ([CLS]/[SEP] or <s>/</s>) and, for
e5, the "passage: " prefix, i.e. exactly what the model would receive.
"""

import sys
from pathlib import Path

import numpy as np
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ingest.chunking import STRATEGIES, load_articles, make_chunks, word_count  # noqa: E402

# Pinned revisions (commit hashes on the Hugging Face Hub).
MODELS = {
    "e5-small": {
        "name": "intfloat/multilingual-e5-small",
        "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        "max_seq_length": 512,
        "passage_prefix": "passage: ",
    },
    "minilm": {
        "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        "max_seq_length": 128,
        "passage_prefix": "",
    },
}

HYBRID_THRESHOLDS = (100, 150, 200, 250, 300)   # words


def token_lengths(tokenizer, texts, prefix):
    return np.array([len(tokenizer(prefix + t)["input_ids"]) for t in texts])


def describe(lengths, limit):
    over = int((lengths > limit).sum())
    return (f"{lengths.min():5d} {int(np.median(lengths)):7d} "
            f"{int(np.percentile(lengths, 95)):6d} {lengths.max():5d}   "
            f"{over:4d} ({100 * over / len(lengths):4.1f}%)")


def main():
    articles = load_articles()
    tokenizers = {key: AutoTokenizer.from_pretrained(m["name"], revision=m["revision"])
                  for key, m in MODELS.items()}

    print(f"{'strategy':10s} {'model':9s} {'chunks':>6s}   "
          f"{'min':>5s} {'median':>7s} {'p95':>6s} {'max':>5s}   over max_seq_length")
    for strategy in STRATEGIES:
        texts = [c["text"] for c in make_chunks(articles, strategy)]
        for key, m in MODELS.items():
            lengths = token_lengths(tokenizers[key], texts, m["passage_prefix"])
            print(f"{strategy:10s} {key:9s} {len(texts):6d}   "
                  f"{describe(lengths, m['max_seq_length'])}   (limit {m['max_seq_length']})")

    # Which chunks are too long even for e5 under each strategy?
    e5 = MODELS["e5-small"]
    for strategy in ("article", "paragraph"):
        chunks = make_chunks(articles, strategy)
        lengths = token_lengths(tokenizers["e5-small"], [c["text"] for c in chunks],
                                e5["passage_prefix"])
        long_ids = [(c["chunk_id"], int(n)) for c, n in zip(chunks, lengths)
                    if n > e5["max_seq_length"]]
        print(f"\nOver 512 tokens with e5, strategy {strategy!r}: {long_ids}")

    # Hybrid threshold sweep (e5 tokenizer).
    print("\nHybrid threshold sweep (e5-small):")
    print(f"{'max_words':>9s} {'chunks':>6s}   {'min':>5s} {'median':>7s} {'p95':>6s} "
          f"{'max':>5s}   over 512")
    for t in HYBRID_THRESHOLDS:
        texts = [c["text"] for c in make_chunks(articles, "hybrid", max_words=t)]
        lengths = token_lengths(tokenizers["e5-small"], texts, e5["passage_prefix"])
        print(f"{t:9d} {len(texts):6d}   {describe(lengths, 512)}")

    # Rough words -> tokens ratio, to translate a word threshold into tokens.
    texts = [a["full_text"] for a in articles]
    ratio = (token_lengths(tokenizers["e5-small"], texts, "").sum()
             / sum(word_count(t) for t in texts))
    print(f"\ne5 tokens per word (whole Constitution): {ratio:.2f}")


if __name__ == "__main__":
    main()
