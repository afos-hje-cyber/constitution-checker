"""Unit tests for usage.py and the LLM client's before_api_call hook.

No real API: the LLM client gets a fake provider. Run:
    .venv\\Scripts\\python -m unittest discover -s tests -t . -v
"""

import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rag.llm import LLMClient, ProviderResponse  # noqa: E402
from common.usage import DailyCounter, UsageLimitError, make_guard  # noqa: E402


class FakeClock:
    def __init__(self, iso_utc):
        self.now = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)

    def __call__(self):
        return self.now


class DailyCounterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "daily.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_cap_and_persistence(self):
        clock = FakeClock("2026-10-26T12:00:00")
        counter = DailyCounter(self.path, cap=2, now=clock)
        self.assertEqual(counter.try_consume(), 1)
        self.assertEqual(counter.try_consume(), 2)
        with self.assertRaises(UsageLimitError) as ctx:
            counter.try_consume()
        self.assertEqual(ctx.exception.kind, "daily")
        # A new counter (e.g. after an app restart) reads the same file.
        self.assertEqual(DailyCounter(self.path, cap=2, now=clock).used(), 2)

    def test_resets_at_midnight_pacific_not_utc(self):
        # 2026-10-26 06:59 UTC = 23:59 on the 25th in Los Angeles (PDT, UTC-7).
        clock = FakeClock("2026-10-26T06:59:00")
        counter = DailyCounter(self.path, cap=1, now=clock)
        counter.try_consume()
        clock.now = clock.now.replace(hour=1)          # 01:00 UTC: earlier, same LA day
        self.assertEqual(counter.used(), 1)
        clock.now = datetime(2026, 10, 26, 7, 1, tzinfo=timezone.utc)   # 00:01 LA, new day
        self.assertEqual(counter.used(), 0)
        self.assertEqual(counter.try_consume(), 1)

    def test_corrupt_file_counts_as_zero(self):
        self.path.write_text("not json", encoding="utf-8")
        counter = DailyCounter(self.path, cap=1, now=FakeClock("2026-10-26T12:00:00"))
        self.assertEqual(counter.used(), 0)

    def test_concurrent_sessions_do_not_double_count(self):
        counter = DailyCounter(self.path, cap=50, now=FakeClock("2026-10-26T12:00:00"))
        results, errors = [], []

        def worker():
            for _ in range(10):
                try:
                    results.append(counter.try_consume())
                except UsageLimitError:
                    errors.append(1)

        threads = [threading.Thread(target=worker) for _ in range(8)]   # 80 attempts
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), list(range(1, 51)))   # each count given out once
        self.assertEqual(len(errors), 30)
        self.assertEqual(counter.used(), 50)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyCounter(Path(self.tmp.name) / "daily.json", cap=3,
                                  now=FakeClock("2026-10-26T12:00:00"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_cap_blocks_the_next_question(self):
        session = {}
        make_guard(self.daily, session, session_cap=1)()          # question 1
        with self.assertRaises(UsageLimitError) as ctx:
            make_guard(self.daily, session, session_cap=1)()      # question 2
        self.assertEqual(ctx.exception.kind, "session")
        self.assertEqual(self.daily.used(), 1)    # the blocked question used no daily budget
        self.assertEqual(session["new_analyses"], 1)

    def test_retries_count_daily_but_not_session(self):
        session = {}
        guard = make_guard(self.daily, session, session_cap=1)    # one question
        guard()
        guard()      # retry: allowed although the session cap (1) is now reached
        self.assertEqual((self.daily.used(), session["new_analyses"]), (2, 1))

    def test_daily_cap_shared_by_sessions(self):
        a, b = {}, {}
        make_guard(self.daily, a, 10)()
        make_guard(self.daily, b, 10)()
        make_guard(self.daily, b, 10)()
        with self.assertRaises(UsageLimitError) as ctx:
            make_guard(self.daily, a, 10)()
        self.assertEqual(ctx.exception.kind, "daily")
        self.assertEqual((a["new_analyses"], b["new_analyses"]), (1, 2))


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


class HookTest(unittest.TestCase):
    """The guard must run for real API calls only, never for cache hits."""

    def test_hook_runs_only_on_real_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeProvider()
            client = LLMClient(provider, "fake-model", "v1", "test_prompt",
                               cache_dir=Path(tmp), rpm_limit=1000)
            hook_calls = []
            hook = lambda: hook_calls.append(1)   # noqa: E731

            first = client.generate_json("sys", "user", before_api_call=hook)
            second = client.generate_json("sys", "user", before_api_call=hook)
            self.assertEqual((first.cached, second.cached), (False, True))
            self.assertEqual((provider.calls, len(hook_calls)), (1, 1))

    def test_blocking_hook_prevents_the_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeProvider()
            client = LLMClient(provider, "fake-model", "v1", "test_prompt",
                               cache_dir=Path(tmp), rpm_limit=1000)

            def block():
                raise UsageLimitError("session")

            with self.assertRaises(UsageLimitError):
                client.generate_json("sys", "other", before_api_call=block)
            self.assertEqual(provider.calls, 0)


class FlakyProvider:
    """1st request: retryable error (like a 503); 2nd: invalid JSON; 3rd: valid answer."""
    name = "flaky"

    def __init__(self):
        self.calls = 0

    def call(self, system_prompt, user_prompt, schema=None):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("simulated 503")
        text = "not json" if self.calls == 2 else '{"ok": true}'
        return ProviderResponse(text, {"input_tokens": 1, "output_tokens": 1,
                                       "thinking_tokens": 0, "total_tokens": 2})

    def is_retryable(self, error):
        return isinstance(error, ConnectionError)


class CapsWithRetriesTest(unittest.TestCase):
    """Daily cap = every API request; session cap = new analyses (questions)."""

    def setUp(self):
        from rag import llm
        self._sleep = llm.time.sleep
        llm.time.sleep = lambda s: None            # skip retry backoff in tests
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyCounter(Path(self.tmp.name) / "daily.json", cap=100,
                                  now=FakeClock("2026-10-26T12:00:00"))

    def tearDown(self):
        from rag import llm
        llm.time.sleep = self._sleep
        self.tmp.cleanup()

    def client(self, provider):
        return LLMClient(provider, "fake-model", "v1", "test_prompt",
                         cache_dir=Path(self.tmp.name) / "cache", rpm_limit=1000)

    def test_question_with_two_retries(self):
        session = {}
        provider = FlakyProvider()
        c = self.client(provider)
        c.generate_json("sys", "q1", before_api_call=make_guard(self.daily, session, 10))
        self.assertEqual(provider.calls, 3)                 # 503 retry + bad-JSON retry
        self.assertEqual(self.daily.used(), 3)              # every request counted
        self.assertEqual(session["new_analyses"], 1)        # one new analysis

        # Same question again: cache hit, counts nowhere.
        r = c.generate_json("sys", "q1", before_api_call=make_guard(self.daily, session, 10))
        self.assertTrue(r.cached)
        self.assertEqual((self.daily.used(), session["new_analyses"]), (3, 1))

    def test_session_cap_does_not_cut_off_retries(self):
        session = {}
        c = self.client(FlakyProvider())
        out = c.generate_json("sys", "q1", before_api_call=make_guard(self.daily, session, 1))
        self.assertEqual(out.data, {"ok": True})            # retries finished despite cap=1
        with self.assertRaises(UsageLimitError):            # but a new question is blocked
            c.generate_json("sys", "q2", before_api_call=make_guard(self.daily, session, 1))
        self.assertEqual((self.daily.used(), session["new_analyses"]), (3, 1))


if __name__ == "__main__":
    unittest.main()
