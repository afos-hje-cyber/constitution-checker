"""Optional rerank stage: rescore retrieved chunks with a cross-encoder.

The embedding search (bi-encoder) compares the query and each chunk
separately; a cross-encoder reads query and chunk TOGETHER, which is slower
but usually more precise. So we take the top N chunks from the embeddings
and let the cross-encoder reorder them.

Same safety rules as the embedding model: pinned revision, safetensors only
(the download fails if there is none), never trust_remote_code, and a check
that refuses a model whose revision differs from config.
"""

from pathlib import Path

from common import config


class RerankerMismatchError(RuntimeError):
    """The loaded reranker is not the one config expects (or has no safetensors)."""


# Only these files are downloaded: no pytorch_model.bin, no repo Python files.
ALLOWED_FILES = ["config.json", "model.safetensors", "sentencepiece.bpe.model",
                 "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json"]

_reranker = None


def load_reranker():
    """Download (once) and load the cross-encoder; check name + revision."""
    global _reranker
    if _reranker is not None:
        return _reranker

    from huggingface_hub import snapshot_download
    from sentence_transformers import CrossEncoder

    local_dir = Path(snapshot_download(config.RERANK_MODEL, revision=config.RERANK_REVISION,
                                       allow_patterns=ALLOWED_FILES))
    if local_dir.name != config.RERANK_REVISION:
        raise RerankerMismatchError(f"loaded revision {local_dir.name}, "
                                    f"config expects {config.RERANK_REVISION}")
    if not (local_dir / "model.safetensors").exists():
        raise RerankerMismatchError(f"{config.RERANK_MODEL} has no model.safetensors")

    model = CrossEncoder(str(local_dir), device="cpu", trust_remote_code=False,
                         model_kwargs={"use_safetensors": True})
    model.hf_name = config.RERANK_MODEL
    model.hf_revision = local_dir.name
    _reranker = model
    return model


def cross_encoder_scorer(query, texts):
    """Scores from the real cross-encoder (higher = more relevant)."""
    return [float(s) for s in load_reranker().predict([(query, t) for t in texts],
                                                      batch_size=16, show_progress_bar=False)]


def rerank_hits(query, hits, k, scorer=cross_encoder_scorer):
    """Reorder `hits` by scorer(query, texts) and keep the top k.

    Each returned hit keeps its fields and gains "rerank_score" and
    "retrieval_rank" (its 1-based position before reranking). Ties keep the
    original retrieval order.
    """
    scores = scorer(query, [h["text"] for h in hits])
    scored = [{**h, "rerank_score": s, "retrieval_rank": i}
              for i, (h, s) in enumerate(zip(hits, scores), start=1)]
    scored.sort(key=lambda h: (-h["rerank_score"], h["retrieval_rank"]))
    return scored[:k]
