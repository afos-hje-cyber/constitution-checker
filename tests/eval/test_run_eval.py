"""Unit tests for the evaluation metrics in scripts/run_eval.py (no model, no API).

Run:  .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
import json  # noqa: E402

from run_eval import CASES_PATH, FREEZES_PATH, freeze_times, label_and_reason_ok  # noqa: E402


class FreezeTimesTest(unittest.TestCase):
    CASES = [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_every_case_frozen_once(self):
        freezes = [{"batch": 1, "frozen_at": "2026-10-27T15:50:26Z", "ids": [1, 2]},
                   {"batch": 2, "frozen_at": "2026-10-28T10:00:00Z", "ids": [3]}]
        times = freeze_times(self.CASES, freezes)
        self.assertEqual(times[1], "2026-10-27T15:50:26+00:00")
        self.assertEqual(times[3], "2026-10-28T10:00:00+00:00")

    def test_case_missing_from_freezes_fails(self):
        freezes = [{"batch": 1, "frozen_at": "2026-10-27T15:50:26Z", "ids": [1, 2]}]
        with self.assertRaisesRegex(ValueError, r"missing.*\[3\]"):
            freeze_times(self.CASES, freezes)

    def test_case_in_two_batches_fails(self):
        freezes = [{"batch": 1, "frozen_at": "2026-10-27T15:50:26Z", "ids": [1, 2]},
                   {"batch": 2, "frozen_at": "2026-10-28T10:00:00Z", "ids": [2, 3]}]
        with self.assertRaisesRegex(ValueError, "case 2 appears in two"):
            freeze_times(self.CASES, freezes)

    def test_unknown_id_in_freezes_fails(self):
        freezes = [{"batch": 1, "frozen_at": "2026-10-27T15:50:26Z", "ids": [1, 2, 3, 99]}]
        with self.assertRaisesRegex(ValueError, "unknown case ids"):
            freeze_times(self.CASES, freezes)

    def test_real_files_are_consistent(self):
        with open(CASES_PATH, encoding="utf-8") as f:
            cases = json.load(f)
        with open(FREEZES_PATH, encoding="utf-8") as f:
            freezes = json.load(f)
        self.assertEqual(len(freeze_times(cases, freezes)), len(cases))


class LabelAndReasonTest(unittest.TestCase):
    def test_correct_label_and_expected_citation_passes(self):
        self.assertTrue(label_and_reason_ok(
            "potential_conflict", ["potential_conflict"], [24], [24, 30]))

    def test_correct_label_without_expected_citation_fails(self):
        self.assertFalse(label_and_reason_ok(
            "potential_conflict", ["potential_conflict"], [55], [56, 288]))

    def test_no_expected_articles_and_correct_label_passes(self):
        self.assertTrue(label_and_reason_ok("unclear", ["unclear"], [], []))
        self.assertTrue(label_and_reason_ok("unclear", ["unclear"], [], [9, 81]))

    def test_wrong_label_fails_even_with_expected_citation(self):
        self.assertFalse(label_and_reason_ok(
            "potential_conflict", ["likely_compatible", "unclear"], [255], [255, 256]))

    def test_any_expected_article_is_enough(self):
        self.assertTrue(label_and_reason_ok(
            "likely_compatible", ["likely_compatible"], [59, 13], [13, 9]))


if __name__ == "__main__":
    unittest.main()
