"""Unit tests for the rerank stage with a fake scorer (no model download).

Run:  .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from common import config  # noqa: E402
from rag.rerank import rerank_hits  # noqa: E402


def hits(*ids):
    return [{"chunk_id": cid, "article": int(cid.removeprefix("art")), "score": 0.9 - i / 100,
             "text": f"text of {cid}"} for i, cid in enumerate(ids)]


def fake_scorer(table):
    """Scorer that returns a fixed score per chunk text."""
    return lambda query, texts: [table[t.removeprefix("text of ")] for t in texts]


class RerankHitsTest(unittest.TestCase):
    def test_reorders_by_score_and_keeps_top_k(self):
        pool = hits("art1", "art2", "art3", "art4")
        scorer = fake_scorer({"art1": 0.1, "art2": 0.9, "art3": 0.5, "art4": 0.7})
        out = rerank_hits("q", pool, k=2, scorer=scorer)
        self.assertEqual([h["chunk_id"] for h in out], ["art2", "art4"])

    def test_keeps_fields_and_adds_rerank_info(self):
        pool = hits("art1", "art2")
        out = rerank_hits("q", pool, k=2, scorer=fake_scorer({"art1": 0.2, "art2": 0.8}))
        self.assertEqual(out[0]["chunk_id"], "art2")
        self.assertEqual(out[0]["retrieval_rank"], 2)      # was second before reranking
        self.assertEqual(out[0]["rerank_score"], 0.8)
        self.assertEqual(out[0]["article"], 2)
        self.assertAlmostEqual(out[0]["score"], 0.89)       # embedding score kept

    def test_ties_keep_retrieval_order(self):
        pool = hits("art1", "art2", "art3")
        out = rerank_hits("q", pool, k=3, scorer=fake_scorer({"art1": 0.5, "art2": 0.5, "art3": 0.5}))
        self.assertEqual([h["chunk_id"] for h in out], ["art1", "art2", "art3"])

    def test_does_not_modify_input(self):
        pool = hits("art1", "art2")
        rerank_hits("q", pool, k=1, scorer=fake_scorer({"art1": 0.1, "art2": 0.9}))
        self.assertNotIn("rerank_score", pool[0])

    def test_scorer_gets_query_and_texts(self):
        seen = {}

        def scorer(query, texts):
            seen["query"], seen["texts"] = query, texts
            return [0.0] * len(texts)

        rerank_hits("Proibir greves", hits("art57"), k=1, scorer=scorer)
        self.assertEqual(seen, {"query": "Proibir greves", "texts": ["text of art57"]})

    def test_off_by_default(self):
        self.assertFalse(config.RERANK_ENABLED)


if __name__ == "__main__":
    unittest.main()
