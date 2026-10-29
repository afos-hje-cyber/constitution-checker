"""Usage caps for the app: a global daily cap and a per-session cap.

Cache hits never count (the LLM client calls the guard right before each
real API request, never on a cache hit).

- Daily cap: counts EVERY API request, retries included (that is what the
  provider's free-tier quota counts). One counter for the whole app, stored
  in data/usage/daily.json, reset at midnight Pacific time (when Google resets
  free-tier quotas). Streamlit runs every browser session as a thread of one
  process, so a threading.Lock is enough to stop two sessions double-counting;
  the file is written atomically (temp file + os.replace) so a crash cannot
  corrupt it.
- Session cap: counts NEW ANALYSES (questions that reach the LLM), not
  requests: a question that needs retries uses one unit. Kept in the session's
  own state (st.session_state["new_analyses"]).
"""

import json
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from common import config


class UsageLimitError(RuntimeError):
    """A usage cap was reached. `kind` is "daily" or "session"."""

    def __init__(self, kind):
        super().__init__(f"{kind} cap reached")
        self.kind = kind


class DailyCounter:
    def __init__(self, path, cap, timezone=config.QUOTA_TIMEZONE, now=None):
        self.path = path
        self.cap = cap
        self.tz = ZoneInfo(timezone)
        self._now = now or (lambda: datetime.now(self.tz))   # injectable for tests
        self._lock = threading.Lock()

    def _today(self):
        return self._now().astimezone(self.tz).date().isoformat()

    def _read(self):
        """Today's count (0 if the file is missing, unreadable or from another day)."""
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0
        return data.get("count", 0) if data.get("date") == self._today() else 0

    def _write(self, count):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": self._today(), "count": count, "timezone": str(self.tz)}, f)
        os.replace(tmp, self.path)   # atomic on the same disk

    def used(self):
        with self._lock:
            return self._read()

    def remaining(self):
        return max(0, self.cap - self.used())

    def try_consume(self):
        """Count one API call, or raise UsageLimitError("daily") if the cap is reached."""
        with self._lock:
            count = self._read()
            if count >= self.cap:
                raise UsageLimitError("daily")
            self._write(count + 1)
            return count + 1


def make_guard(daily, session_state, session_cap):
    """Build the callable the LLM client runs before every real API request.

    Create ONE guard per question. Its first call is the question's first
    request: it checks the session cap, then counts one daily request and one
    new analysis. Later calls are retries of the same question: they count
    only against the daily cap (the session cap does not block them, since
    the analysis was already admitted).

    session_state is a dict-like (st.session_state in the app). The session
    cap is checked first so a blocked session never uses the daily budget.
    """
    admitted = False

    def guard():
        nonlocal admitted
        if admitted:                       # retry of an analysis already counted
            daily.try_consume()
            return
        used = session_state.get("new_analyses", 0)
        if used >= session_cap:
            raise UsageLimitError("session")
        daily.try_consume()                # raises before the session is charged
        session_state["new_analyses"] = used + 1
        admitted = True
    return guard


def default_daily_counter():
    return DailyCounter(config.USAGE_DIR / "daily.json", config.DAILY_CAP)
