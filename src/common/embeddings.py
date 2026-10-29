"""The embedding model, shared by index building (ingest) and retrieval (rag).

Both stages must use exactly the same model, so its settings and loader live
here instead of in either stage.

Safety: weights are loaded only from .safetensors at a pinned commit, and
trust_remote_code is never enabled.
"""

from pathlib import Path

MODEL = {
    "name": "intfloat/multilingual-e5-small",
    "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    "short": "e5small",
    "passage_prefix": "passage: ",   # e5 needs these prefixes:
    "query_prefix": "query: ",       # "passage: " for documents, "query: " for questions
    "max_seq_length": 512,
}


def load_model():
    """Download (once) only the files we need, then load from that folder."""
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer

    local_dir = snapshot_download(
        MODEL["name"],
        revision=MODEL["revision"],
        allow_patterns=["*.json", "model.safetensors", "sentencepiece.bpe.model"],
        ignore_patterns=["onnx/*", "openvino/*"],   # skip other weight formats
    )
    model = SentenceTransformer(
        local_dir,
        device="cpu",
        trust_remote_code=False,
        model_kwargs={"use_safetensors": True},
    )
    model.max_seq_length = MODEL["max_seq_length"]
    # Record what was actually loaded: the snapshot folder name is the commit hash.
    model.hf_name = MODEL["name"]
    model.hf_revision = Path(local_dir).name
    return model
