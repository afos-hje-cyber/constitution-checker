"""The LLM cache must never serve a k=8 answer for a k=10 request.

The cache key hashes the full user prompt, and the prompt contains every
retrieved chunk, so a different k (or different chunks) gives a different key.
No model or API is used: chunks come from chunks_hybrid.json, the provider is fake.

Run:  .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rag.assess import build_user_prompt  # noqa: E402
from rag.llm import LLMClient, ProviderResponse  # noqa: E402

with open(ROOT / "data" / "processed" / "chunks_hybrid.json", encoding="utf-8") as f:
    CHUNKS = json.load(f)[1:13]   # 12 real chunks (skip the Preâmbulo)
HITS = [{**c, "score": 0.9} for c in CHUNKS]


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def call(self, system_prompt, user_prompt, schema=None):
        self.calls += 1
        return ProviderResponse('{"ok": true}', {"input_tokens": 1, "output_tokens": 1,
                                                 "thinking_tokens": 0, "total_tokens": 2})

    def is_retryable(self, error):
        return False


def client(tmp, provider):
    return LLMClient(provider, "fake-model", "v1", "assess_v1", cache_dir=Path(tmp),
                     rpm_limit=1000)


class CacheKeyTest(unittest.TestCase):
    def test_k8_and_k10_prompts_have_different_keys(self):
        p8 = build_user_prompt("Proposta", HITS[:8], "v1_basic")
        p10 = build_user_prompt("Proposta", HITS[:10], "v1_basic")
        self.assertNotEqual(p8, p10)
        with tempfile.TemporaryDirectory() as tmp:
            c = client(tmp, FakeProvider())
            self.assertNotEqual(c.cache_key("sys", p8), c.cache_key("sys", p10))

    def test_same_chunks_give_same_key(self):
        p_a = build_user_prompt("Proposta", HITS[:8], "v1_basic")
        p_b = build_user_prompt("Proposta", HITS[:8], "v1_basic")
        with tempfile.TemporaryDirectory() as tmp:
            c = client(tmp, FakeProvider())
            self.assertEqual(c.cache_key("sys", p_a), c.cache_key("sys", p_b))

    def test_different_chunks_same_k_give_different_keys(self):
        p_a = build_user_prompt("Proposta", HITS[:8], "v1_basic")
        p_b = build_user_prompt("Proposta", HITS[1:9], "v1_basic")
        with tempfile.TemporaryDirectory() as tmp:
            c = client(tmp, FakeProvider())
            self.assertNotEqual(c.cache_key("sys", p_a), c.cache_key("sys", p_b))

    def test_k10_request_is_not_served_from_k8_cache(self):
        p8 = build_user_prompt("Proposta", HITS[:8], "v1_basic")
        p10 = build_user_prompt("Proposta", HITS[:10], "v1_basic")
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeProvider()
            c = client(tmp, provider)
            self.assertFalse(c.generate_json("sys", p8).cached)
            self.assertFalse(c.generate_json("sys", p10).cached)   # new API call
            self.assertTrue(c.generate_json("sys", p8).cached)
            self.assertEqual(provider.calls, 2)


if __name__ == "__main__":
    unittest.main()
