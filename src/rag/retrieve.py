"""Retrieve the chunks most similar to a query.

Usage:
    from rag.retrieve import retrieve
    retrieve("Reintroduzir a pena de morte")            # config defaults (hybrid, k=10)
    retrieve("Reintroduzir a pena de morte", "paragraph", k=5)

The model and each index are loaded once and reused across calls.
Before an index is used, its metadata is checked against the loaded model
(name + revision): an index built with a different model would give
meaningless scores, so we refuse to use it.
"""

import json

import numpy as np

from common import config
from common.embeddings import MODEL, load_model

OUT_DIR = config.PROCESSED_DIR


class IndexMismatchError(RuntimeError):
    """The index on disk was not built with the model we have loaded."""


_model = None    # loaded on first use
_indexes = {}    # strategy -> (vectors, chunks, meta)


def get_model():
    global _model
    if _model is None:
        _model = load_model()
    return _model


def load_index(strategy):
    """Load (once) and check the vectors, chunks and metadata of a strategy."""
    if strategy in _indexes:
        return _indexes[strategy]

    model = get_model()
    stem = OUT_DIR / f"index_{strategy}_{MODEL['short']}"
    vectors = np.load(f"{stem}.npy")
    with open(OUT_DIR / f"chunks_{strategy}.json", encoding="utf-8") as f:
        chunks = json.load(f)
    with open(f"{stem}.meta.json", encoding="utf-8") as f:
        meta = json.load(f)

    loaded = (model.hf_name, model.hf_revision)
    expected = (meta["model"], meta["revision"])
    if loaded != expected:
        raise IndexMismatchError(f"index {strategy!r} was built with {expected}, "
                                 f"but the loaded model is {loaded}")
    if not meta["normalised"]:
        raise IndexMismatchError(f"index {strategy!r} is not normalised")
    if vectors.shape != (len(chunks), model.get_embedding_dimension()) \
            or len(chunks) != meta["chunk_count"]:
        raise IndexMismatchError(f"index {strategy!r}: vectors {vectors.shape}, "
                                 f"{len(chunks)} chunks, metadata {meta['chunk_count']}")

    _indexes[strategy] = (vectors, chunks, meta)
    return _indexes[strategy]


def retrieve(query, strategy=None, k=None, rerank=None, candidates=None):
    """Return the top-k chunks for `query`, best first.

    Vectors are normalised, so cosine similarity is just a dot product.
    strategy / k: None = config.RETRIEVAL_STRATEGY / config.RETRIEVAL_K.
    rerank: None = use config.RERANK_ENABLED (off by default). When on, the
    top `candidates` (default config.RERANK_CANDIDATES) chunks are reordered
    by the cross-encoder in rerank.py and the top k are returned.
    """
    strategy = strategy or config.RETRIEVAL_STRATEGY
    k = k or config.RETRIEVAL_K
    if rerank is None:
        rerank = config.RERANK_ENABLED
    if rerank:
        from rag.rerank import rerank_hits
        pool = retrieve(query, strategy, candidates or config.RERANK_CANDIDATES, rerank=False)
        return rerank_hits(query, pool, k)

    model = get_model()
    vectors, chunks, meta = load_index(strategy)
    q = model.encode(meta["query_prefix"] + query, normalize_embeddings=True)
    scores = vectors @ q
    top = np.argsort(-scores)[:k]
    return [
        {
            "score": float(scores[i]),
            "chunk_id": chunks[i]["chunk_id"],
            "article": chunks[i]["article"],
            "paragraph": chunks[i]["paragraph"],
            "alineas": chunks[i]["alineas"],
            "title": chunks[i]["title"],
            "text": chunks[i]["text"],
        }
        for i in top
    ]


if __name__ == "__main__":
    for hit in retrieve("Reintroduzir a pena de morte", "hybrid", 5):
        print(f"{hit['score']:.3f}  {hit['chunk_id']:15s} {hit['title']}")
