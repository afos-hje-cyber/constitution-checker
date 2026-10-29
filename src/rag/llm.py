"""Thin LLM wrapper: one interface, swappable providers, disk cache.

Usage:
    client = LLMClient.from_config()
    result = client.generate_json(system_prompt, user_prompt, schema=SCHEMA)
    result.data      # parsed dict
    result.usage     # token counts of the call
    result.cached    # True if served from data/cache/llm/ (no API request)

To add a provider (e.g. Groq), write a class with `name`,
`call(system_prompt, user_prompt, schema) -> ProviderResponse`,
`is_retryable(error)` and `model_version()`, and register it in PROVIDERS.
Callers do not change.
"""

import hashlib
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from dotenv import load_dotenv

from common import config


class LLMUnavailableError(RuntimeError):
    """The provider kept failing (rate limit, server error, network)."""


class LLMOutputError(RuntimeError):
    """The model returned something that is not the JSON we asked for."""


class MissingAPIKeyError(RuntimeError):
    """No API key in the environment (.env locally, secrets on Streamlit Cloud)."""


@dataclass
class ProviderResponse:
    text: str
    usage: dict
    response_model_version: str | None = None   # what the API says it ran


@dataclass
class LLMResult:
    data: dict
    usage: dict
    cached: bool
    model: str
    model_version: str
    response_model_version: str | None
    seconds: float
    attempts: int = 1
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------- providers

class GeminiProvider:
    name = "gemini"

    def __init__(self, model, temperature):
        from google import genai   # imported here so other providers don't need it

        load_dotenv(config.ENV_PATH)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise MissingAPIKeyError("GEMINI_API_KEY is not set")
        self._genai = genai
        self.client = genai.Client(api_key=api_key)  # never logged
        self.model = model
        self.temperature = temperature

    def call(self, system_prompt, user_prompt, schema=None):
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.temperature,
            response_mime_type="application/json",   # JSON output mode
            response_json_schema=schema,
        )
        response = self.client.models.generate_content(
            model=self.model, contents=user_prompt, config=cfg)
        u = response.usage_metadata
        usage = {
            "input_tokens": u.prompt_token_count or 0,
            "output_tokens": u.candidates_token_count or 0,
            "thinking_tokens": u.thoughts_token_count or 0,
            "total_tokens": u.total_token_count or 0,
        }
        return ProviderResponse(response.text or "", usage, response.model_version)

    def is_retryable(self, error):
        """429 (rate limit) and 5xx (server) are worth retrying; network errors too.

        The SDK sends requests with httpx, so dropped connections arrive as
        httpx.TransportError (e.g. RemoteProtocolError "Server disconnected
        without sending a response"), which is not an OSError.
        """
        import httpx
        from google.genai import errors

        if isinstance(error, errors.APIError):
            return error.code == 429 or (error.code or 0) >= 500
        return isinstance(error, (httpx.TransportError, ConnectionError, TimeoutError, OSError))

    def model_version(self):
        """Version string the API reports for our model (models.get: no quota used)."""
        return self.client.models.get(model=self.model).version


PROVIDERS = {"gemini": GeminiProvider}


# ------------------------------------------------------------- rate limit

class MinuteRateLimiter:
    """Sleep before a request if the last minute already used rpm_limit requests."""

    def __init__(self, rpm_limit):
        self.rpm_limit = rpm_limit
        self.sent = deque()   # timestamps of recent requests

    def wait(self):
        now = time.monotonic()
        while self.sent and now - self.sent[0] > 60:
            self.sent.popleft()
        if len(self.sent) >= self.rpm_limit:
            time.sleep(60 - (now - self.sent[0]) + 0.1)
        self.sent.append(time.monotonic())


# ------------------------------------------------------------ model status

class ModelStatus:
    """Result of the startup model check, kept for the whole app process.

    check: callable returning "ok", "mismatch", "unreachable" or "no_key".
    "ok", "mismatch" and "no_key" are kept until the app restarts;
    "unreachable" (e.g. a network blip at startup) is checked again once
    retry_seconds have passed, so it never sticks for the whole process.
    """

    def __init__(self, check, retry_seconds=300, clock=time.monotonic):
        self.check = check
        self.retry_seconds = retry_seconds
        self.clock = clock                  # injectable for tests
        self.status = None
        self.checked_at = None
        self._lock = threading.Lock()       # Streamlit sessions are threads

    def get(self):
        with self._lock:
            stale = (self.status == "unreachable"
                     and self.clock() - self.checked_at >= self.retry_seconds)
            if self.status is None or stale:
                self.status = self.check()
                self.checked_at = self.clock()
            return self.status


# ------------------------------------------------------------------ client

class LLMClient:
    def __init__(self, provider, model, model_version, prompt_version,
                 cache_dir=config.CACHE_DIR, max_retries=config.MAX_RETRIES,
                 rpm_limit=config.RPM_LIMIT):
        self.provider = provider
        self.model = model
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.limiter = MinuteRateLimiter(rpm_limit)
        # api_calls counts every request sent; transport_retries the ones repeated
        # after a 429/5xx/network error; output_retries the ones repeated after bad JSON.
        self.stats = {"api_calls": 0, "cache_hits": 0, "transport_retries": 0,
                      "output_retries": 0}

    @classmethod
    def from_config(cls, prompt_version=config.PROMPT_VERSION):
        provider = PROVIDERS[config.PROVIDER](config.MODEL, config.TEMPERATURE)
        return cls(provider, config.MODEL, config.MODEL_VERSION, prompt_version)

    # -- cache -----------------------------------------------------------
    def cache_key(self, system_prompt, user_prompt):
        # The model version is part of the key too: a new model version must
        # not be served old answers.
        parts = [self.provider.name, self.model, self.model_version,
                 self.prompt_version, system_prompt, user_prompt]
        return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _cache_path(self, key):
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key):
        path = self._cache_path(key)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write_cache(self, key, entry):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path(key), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

    # -- model check -------------------------------------------------------
    def verify_model(self):
        """Compare the version the provider reports with config.

        Returns "ok"; "unreachable" if the provider could not be asked; or
        "mismatch" if it now serves a different version than the one evaluated
        (the app then answers with retrieval only instead of the LLM).
        """
        if config.FORCE_LLM_UNAVAILABLE:
            return "unreachable"
        try:
            served = self.provider.model_version()
        except Exception:   # network/auth problems: not a version mismatch
            return "unreachable"
        return "ok" if served == self.model_version else "mismatch"

    # -- API call with retries ------------------------------------------
    def _call_with_retries(self, system_prompt, user_prompt, schema, before_api_call):
        for attempt in range(self.max_retries + 1):
            if config.FORCE_LLM_UNAVAILABLE:
                raise LLMUnavailableError("forced by FORCE_LLM_UNAVAILABLE=1")
            if before_api_call:
                before_api_call()   # e.g. usage caps; may raise to block the call
            self.limiter.wait()
            try:
                self.stats["api_calls"] += 1
                return self.provider.call(system_prompt, user_prompt, schema)
            except Exception as error:   # provider-specific errors are classified below
                if not self.provider.is_retryable(error):
                    raise
                if attempt == self.max_retries:
                    raise LLMUnavailableError(
                        f"{self.provider.name} unavailable after {attempt + 1} attempts: "
                        f"{type(error).__name__}") from error
                self.stats["transport_retries"] += 1
                time.sleep(2 * 2 ** attempt)   # 2 s, then 4 s

    # -- public interface ------------------------------------------------
    def generate_json(self, system_prompt, user_prompt, schema=None, validate=None,
                      before_api_call=None):
        """Return an LLMResult whose .data is the parsed JSON object.

        validate: optional callable(data) that raises ValueError if the
        structure is wrong. On a parse or validation failure the call is
        retried once; only valid results are cached.
        before_api_call: optional callable run before EVERY real API request
        (never on a cache hit); it may raise to block the request.
        """
        key = self.cache_key(system_prompt, user_prompt)
        start = time.perf_counter()

        entry = self._read_cache(key)
        if entry is not None:
            self.stats["cache_hits"] += 1
            return LLMResult(entry["data"], entry["usage"], True, entry["model"],
                             entry["model_version"], entry["response_model_version"],
                             time.perf_counter() - start, extra={"cache_key": key})

        last_error = None
        for attempt in (1, 2):   # first try + one retry on bad output
            response = self._call_with_retries(system_prompt, user_prompt, schema,
                                               before_api_call)
            try:
                data = json.loads(response.text)
                if not isinstance(data, dict):
                    raise ValueError("top-level JSON is not an object")
                if validate:
                    validate(data)
            except ValueError as error:   # json.JSONDecodeError is a ValueError
                last_error = error
                if attempt == 1:
                    self.stats["output_retries"] += 1
                continue
            self._write_cache(key, {
                "provider": self.provider.name,
                "model": self.model,
                "model_version": self.model_version,
                "response_model_version": response.response_model_version,
                "prompt_version": self.prompt_version,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "user_prompt": user_prompt,
                "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
                "usage": response.usage,
                "raw_text": response.text,
                "data": data,
            })
            return LLMResult(data, response.usage, False, self.model, self.model_version,
                             response.response_model_version, time.perf_counter() - start,
                             attempts=attempt, extra={"cache_key": key})
        raise LLMOutputError(f"invalid output after 2 attempts: {last_error}")
