"""Unit tests for validation.py with fake LLM outputs (no model, no API).

Run:  .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rag.validation import extract_references, validate_output  # noqa: E402


def hit(article, paragraph=None, alineas=None):
    """A fake retrieved chunk with only the fields validation uses."""
    cid = f"art{article}" + (f"_n{paragraph}" if paragraph else "")
    return {"chunk_id": cid, "article": article, "paragraph": paragraph, "alineas": alineas}


def answer(label="potential_conflict", summary="Resumo.", reasoning="Raciocínio.",
           citations=None):
    """A fake LLM output that passes the structure check."""
    return {"label": label, "summary": summary, "reasoning": reasoning,
            "citations": citations or [], "missing_information": None}


def cite(article, n=None, alinea=None):
    return {"article": article, "n": n, "alinea": alinea, "explanation": "x"}


class ExtractReferencesTest(unittest.TestCase):
    def test_forms(self):
        cases = {
            "o artigo 24.º estabelece": {(24, None)},
            "Artigo 24.º": {(24, None)},
            "nos termos do art. 24.º": {(24, None)},
            "os artigos 24.º e 30.º": {(24, None), (30, None)},
            "os artigos 13.º, 24.º e 30.º": {(13, None), (24, None), (30, None)},
            "o artigo 24.º, n.º 2, diz": {(24, 2)},
            "o n.º 3 do artigo 57.º prevê": {(57, 3)},
            "como diz o 24.º, n.º 1": {(24, 1)},
            "arts. 37.º e 38.º, n.º 2": {(37, None), (38, 2)},
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_references(text), expected)

    def test_bare_article_dropped_when_paragraph_given(self):
        text = "O artigo 24.º, n.º 2 proíbe; o artigo 24.º protege a vida."
        self.assertEqual(extract_references(text), {(24, 2)})

    def test_no_false_positives(self):
        for text in ("o n.º 1 da lei", "em 1976 foi aprovada", "1.º lugar", "alínea m)"):
            with self.subTest(text=text):
                self.assertEqual(extract_references(text), set())


class ValidateOutputTest(unittest.TestCase):
    def test_clean_answer_unchanged(self):
        data = answer(reasoning="O artigo 24.º, n.º 2, proíbe a pena de morte.",
                      citations=[cite(24, 2)])
        result, rej_c, rej_r, notes = validate_output(data, [hit(24)])
        self.assertEqual(result, data)
        self.assertEqual((rej_c, rej_r, notes), ([], [], []))

    def test_reference_retrieved_but_not_cited_is_added(self):
        # Case 1 of the smoke test: reasoning mentions n.º 1, citations only n.º 2.
        data = answer(reasoning="O artigo 24.º, n.º 2, proíbe a pena de morte. "
                                "O artigo 24.º, n.º 1, diz que a vida é inviolável.",
                      citations=[cite(24, 2)])
        result, _, rej_r, notes = validate_output(data, [hit(24), hit(30)])
        self.assertEqual([(c["article"], c["n"]) for c in result["citations"]],
                         [(24, 2), (24, 1)])
        self.assertEqual(result["citations"][1]["explanation"], "referido no raciocínio")
        self.assertEqual(rej_r, [])
        self.assertEqual(result["label"], "potential_conflict")
        self.assertTrue(any("acrescentada" in n for n in notes))

    def test_reference_not_retrieved_forces_unclear(self):
        data = answer(summary="Conflito com o artigo 24.º.",
                      reasoning="O artigo 24.º, n.º 2, proíbe; o artigo 33.º também.",
                      citations=[cite(24, 2)])
        result, _, rej_r, notes = validate_output(data, [hit(24)])
        self.assertEqual(result["label"], "unclear")
        self.assertEqual([(r["article"], r["reason"]) for r in rej_r],
                         [(33, "mentioned in text but not retrieved")])
        self.assertEqual([(c["article"], c["n"]) for c in result["citations"]], [(24, 2)])
        self.assertTrue(any("alterada para 'unclear'" in n for n in notes))

    def test_reference_to_paragraph_not_shown_is_rejected(self):
        # Only n.º 3 of art. 27.º was retrieved; the text relies on n.º 1.
        data = answer(reasoning="O artigo 27.º, n.º 1, garante a liberdade.",
                      citations=[cite(27, 3)])
        result, _, rej_r, _ = validate_output(data, [hit(27, 3)])
        self.assertEqual(result["label"], "unclear")
        self.assertEqual([(r["article"], r["n"]) for r in rej_r], [(27, 1)])

    def test_citation_not_retrieved_is_rejected(self):
        data = answer(citations=[cite(24, 2), cite(99)])
        result, rej_c, _, _ = validate_output(data, [hit(24)])
        self.assertEqual([c["article"] for c in result["citations"]], [24])
        self.assertEqual(rej_c[0]["article"], 99)
        self.assertEqual(result["label"], "potential_conflict")

    def test_nonexistent_paragraph_is_rejected(self):
        data = answer(citations=[cite(24, 5)])     # art. 24.º has only n.º 1 and 2
        result, rej_c, _, _ = validate_output(data, [hit(24)])
        self.assertIn("não tem n.º 5", rej_c[0]["reason"])
        self.assertEqual(result["label"], "unclear")

    def test_label_without_valid_citation_becomes_unclear(self):
        data = answer(label="likely_compatible", citations=[])
        result, _, _, notes = validate_output(data, [hit(81)])
        self.assertEqual(result["label"], "unclear")
        self.assertTrue(any("nenhuma citação válida" in n for n in notes))

    def test_unclear_without_citations_is_fine(self):
        data = answer(label="unclear", citations=[])
        result, rej_c, rej_r, notes = validate_output(data, [hit(9)])
        self.assertEqual((result, rej_c, rej_r, notes), (data, [], [], []))

    def test_input_not_modified(self):
        data = answer(reasoning="O artigo 24.º, n.º 1, e o artigo 33.º.",
                      citations=[cite(24, 2)])
        before = repr(data)
        validate_output(data, [hit(24)])
        self.assertEqual(repr(data), before)


if __name__ == "__main__":
    unittest.main()
