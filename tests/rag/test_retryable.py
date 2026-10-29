"""Which provider errors are retried (no API, no key needed).

Run:  .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rag.llm import GeminiProvider  # noqa: E402

# is_retryable does not use the API client, so skip __init__ (which needs a key).
PROVIDER = object.__new__(GeminiProvider)


class RetryableTest(unittest.TestCase):
    def test_dropped_connection_is_retryable(self):
        # The error that stopped the assess_v2 dev run on 2026-10-27.
        err = httpx.RemoteProtocolError("Server disconnected without sending a response.")
        self.assertTrue(PROVIDER.is_retryable(err))

    def test_other_network_errors_are_retryable(self):
        for err in (httpx.ConnectError("refused"), httpx.ReadTimeout("slow"),
                    ConnectionError("reset"), TimeoutError("timeout")):
            with self.subTest(err=type(err).__name__):
                self.assertTrue(PROVIDER.is_retryable(err))

    def test_api_errors(self):
        from google.genai import errors
        self.assertTrue(PROVIDER.is_retryable(errors.APIError(429, {})))
        self.assertTrue(PROVIDER.is_retryable(errors.APIError(503, {})))
        self.assertFalse(PROVIDER.is_retryable(errors.APIError(400, {})))
        self.assertFalse(PROVIDER.is_retryable(errors.APIError(403, {})))

    def test_programming_errors_are_not_retryable(self):
        for err in (ValueError("bad"), KeyError("x"), TypeError("y")):
            with self.subTest(err=type(err).__name__):
                self.assertFalse(PROVIDER.is_retryable(err))


if __name__ == "__main__":
    unittest.main()
