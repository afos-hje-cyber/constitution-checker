"""Startup model check: verify_model, ModelStatus and the missing-key case
(no API, no key needed).

Run:  .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from common import config  # noqa: E402
from rag.llm import GeminiProvider, LLMClient, MissingAPIKeyError, ModelStatus  # noqa: E402


class FakeProvider:
    """Stands in for GeminiProvider: reports a fixed version, or fails."""
    name = "fake"

    def __init__(self, version=None, error=None):
        self.version, self.error = version, error

    def model_version(self):
        if self.error:
            raise self.error
        return self.version


def client(provider):
    return LLMClient(provider, "some-model", "v-evaluated", "assess_v2")


class VerifyModelTest(unittest.TestCase):
    def test_same_version_is_ok(self):
        self.assertEqual(client(FakeProvider("v-evaluated")).verify_model(), "ok")

    def test_different_version_is_mismatch_not_an_error(self):
        # The app then answers with retrieval only instead of stopping.
        self.assertEqual(client(FakeProvider("v-new")).verify_model(), "mismatch")

    def test_provider_failure_is_unreachable(self):
        provider = FakeProvider(error=ConnectionError("no network"))
        self.assertEqual(client(provider).verify_model(), "unreachable")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ModelStatusTest(unittest.TestCase):
    def make(self, results):
        """ModelStatus whose check returns `results` in order; counts the calls."""
        self.calls = 0

        def check():
            self.calls += 1
            return results[self.calls - 1]
        self.clock = FakeClock()
        return ModelStatus(check, retry_seconds=300, clock=self.clock)

    def test_ok_is_checked_once(self):
        status = self.make(["ok"])
        self.clock.now = 10_000
        self.assertEqual([status.get(), status.get()], ["ok", "ok"])
        self.assertEqual(self.calls, 1)

    def test_unreachable_is_checked_again_after_retry_seconds(self):
        # A network blip at startup must not disable the check until a restart.
        status = self.make(["unreachable", "ok"])
        self.assertEqual(status.get(), "unreachable")
        self.clock.now = 299
        self.assertEqual(status.get(), "unreachable")   # too soon: no new request
        self.assertEqual(self.calls, 1)
        self.clock.now = 300
        self.assertEqual(status.get(), "ok")
        self.assertEqual(self.calls, 2)

    def test_mismatch_after_unreachable_is_kept(self):
        status = self.make(["unreachable", "mismatch"])
        status.get()
        self.clock.now = 300
        self.assertEqual(status.get(), "mismatch")
        self.clock.now = 10_000
        self.assertEqual(status.get(), "mismatch")
        self.assertEqual(self.calls, 2)

    def test_no_key_is_kept(self):
        status = self.make(["no_key"])
        self.clock.now = 10_000
        self.assertEqual(status.get(), "no_key")
        self.assertEqual(self.calls, 1)


class MissingKeyTest(unittest.TestCase):
    def test_provider_without_key_raises_missing_api_key(self):
        # No key in the environment and no .env file (as in a fresh clone).
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(config, "ENV_PATH", Path("does-not-exist.env")):
            with self.assertRaises(MissingAPIKeyError):
                GeminiProvider(config.MODEL, config.TEMPERATURE)


if __name__ == "__main__":
    unittest.main()
