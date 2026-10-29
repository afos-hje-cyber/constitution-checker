"""Central configuration. No secrets here: API keys live in .env.

Values marked "env" can be overridden with an environment variable of the
same name (used to test the usage caps and outage handling).
"""

import os
from pathlib import Path

# The only place that knows where the repository is (this file is
# src/common/config.py, so the root is three levels up). Every other path is
# built from it, so the code works from any working directory.
ROOT = Path(__file__).resolve().parents[2]

# ---- Paths ------------------------------------------------------------------
DATA_DIR = ROOT / "data"
PDF_PATH = DATA_DIR / "crpviirevisao.pdf"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
EVAL_DIR = ROOT / "eval"
ENV_PATH = ROOT / ".env"

# ---- LLM ------------------------------------------------------------------
PROVIDER = "gemini"
MODEL = "gemini-3.5-flash-lite"            # fixed name, never the "-latest" alias
MODEL_VERSION = "3.5-flash-lite-07-2026"   # from models.list on 2026-10-25
TEMPERATURE = 0

# Free-tier limits (requests/minute, requests/day, tokens/minute).
RPM_LIMIT = 15
RPD_LIMIT = 500
TPM_LIMIT = 250_000

MAX_RETRIES = 2            # on 429 / 5xx, then LLMUnavailableError
CACHE_DIR = DATA_DIR / "cache" / "llm"

# Testing aid (env): FORCE_LLM_UNAVAILABLE=1 makes every real API call fail
# with LLMUnavailableError. Cached answers are still served.
FORCE_LLM_UNAVAILABLE = os.getenv("FORCE_LLM_UNAVAILABLE") == "1"

# ---- Usage caps (app) -------------------------------------------------------
# Only real API calls count; cache hits are free.
DAILY_CAP = int(os.getenv("DAILY_CAP", "400"))       # env; global, all sessions
SESSION_CAP = int(os.getenv("SESSION_CAP", "10"))    # env; per browser session
USAGE_DIR = Path(os.getenv("USAGE_DIR", str(DATA_DIR / "usage")))   # env
QUOTA_TIMEZONE = "America/Los_Angeles"   # Google resets free-tier quotas at midnight Pacific

# ---- Assessment -----------------------------------------------------------
PROMPT_VERSION = "assess_v2"   # was assess_v1; see eval/results/dev/llm_prompt_v2_dev.md
PROMPTS_DIR = ROOT / "src" / "rag" / "prompts"
RETRIEVAL_STRATEGY = "hybrid"
RETRIEVAL_K = 10   # was 8; changed after eval/results/dev/llm_k10_dev.md (see eval/NOTES.md)
MAX_PROPOSAL_CHARS = 2000

# Optional rerank stage (experiment; OFF by default): retrieve RERANK_CANDIDATES
# chunks with the embeddings, rescore them with a cross-encoder, keep the top k.
RERANK_ENABLED = os.getenv("RERANK_ENABLED") == "1"                  # env
RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
RERANK_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"
RERANK_CANDIDATES = 30

# Label codes stored in results -> European Portuguese display names.
LABELS = {
    "likely_compatible": "Provavelmente compatível",
    "potential_conflict": "Potencial conflito",
    "unclear": "Incerto / requer análise jurídica",
}
