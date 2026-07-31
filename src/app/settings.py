"""Environment-backed application settings."""

from __future__ import annotations

import os
import tempfile
from typing import Dict

from dotenv import load_dotenv


load_dotenv(override=True)


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


POSTGRES_DB = os.getenv("POSTGRES_DB", "wb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "wb")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "wbpassword")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

WB_SERVICE_TOKEN = os.getenv("WB_SERVICE_TOKEN") or os.getenv("WB_TOKEN", "MOCK")
WB_TOKEN = os.getenv("WB_TOKEN", "MOCK")
WB_VALIDATE_TOKEN = os.getenv("WB_VALIDATE_TOKEN", "true").lower() in ("true", "1", "yes")
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
TZ = os.getenv("TZ", "Europe/Moscow")

SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
INTERNAL_DATA_DIR = os.getenv("INTERNAL_DATA_DIR", "/data/internal_data")
SEO_QUERY_IMPORT_TMP_DIR = os.getenv(
    "SEO_QUERY_IMPORT_TMP_DIR",
    os.path.join(tempfile.gettempdir(), "ecomcore", "seo_query_import"),
)
INGEST_STUCK_TTL_SECONDS_DEFAULT = _get_env_int("INGEST_STUCK_TTL_SECONDS_DEFAULT", 1800)

FRONTEND_PRICES_MAX_RUNTIME_SECONDS = _get_env_int("FRONTEND_PRICES_MAX_RUNTIME_SECONDS", 1200)
FRONTEND_PRICES_MAX_TOTAL_RETRY_WAIT_SECONDS = _get_env_int("FRONTEND_PRICES_MAX_TOTAL_RETRY_WAIT_SECONDS", 300)
FRONTEND_PRICES_MAX_RETRY_SLEEP_SECONDS = _get_env_int("FRONTEND_PRICES_MAX_RETRY_SLEEP_SECONDS", 120)
FRONTEND_PRICES_RATE_LIMIT_BACKOFF_MINUTES = _get_env_int("FRONTEND_PRICES_RATE_LIMIT_BACKOFF_MINUTES", 15)
FRONTEND_PRICES_HTTP_TIMEOUT = _get_env_int("FRONTEND_PRICES_HTTP_TIMEOUT", 30)
FRONTEND_PRICES_HTTP_MIN_RETRIES = _get_env_int("FRONTEND_PRICES_HTTP_MIN_RETRIES", 10)
FRONTEND_PRICES_HTTP_TIMEOUT_JITTER = _get_env_int("FRONTEND_PRICES_HTTP_TIMEOUT_JITTER", 10)
FRONTEND_PRICES_MIN_COVERAGE_RATIO = _get_env_float("FRONTEND_PRICES_MIN_COVERAGE_RATIO", 0.80)
ALLOW_UNAUTH_LOCAL = os.getenv("ALLOW_UNAUTH_LOCAL", "false").lower() in ("true", "1", "yes")

WB_ANALYTICS_BASE_URL = os.getenv("WB_ANALYTICS_BASE_URL", "https://seller-analytics-api.wildberries.ru")
WB_ANALYTICS_REQUEST_INTERVAL_SEC = _get_env_int("WB_ANALYTICS_REQUEST_INTERVAL_SEC", 20)
WB_ANALYTICS_MAX_RETRIES = _get_env_int("WB_ANALYTICS_MAX_RETRIES", 3)
WB_ANALYTICS_TIMEOUT_SEC = _get_env_int("WB_ANALYTICS_TIMEOUT_SEC", 60)
WB_FUNNEL_REPORT_MAX_UPLOAD_BYTES = _get_env_int("WB_FUNNEL_REPORT_MAX_UPLOAD_BYTES", 20 * 1024 * 1024)
WB_FUNNEL_CTR_MISMATCH_TOLERANCE_PP = _get_env_float("WB_FUNNEL_CTR_MISMATCH_TOLERANCE_PP", 1.0)
WB_FUNNEL_CTR_INDICATIVE_IMPRESSIONS = _get_env_int("WB_FUNNEL_CTR_INDICATIVE_IMPRESSIONS", 100)
WB_FUNNEL_CTR_RELIABLE_IMPRESSIONS = _get_env_int("WB_FUNNEL_CTR_RELIABLE_IMPRESSIONS", 400)
WB_FUNNEL_CTR_HIGH_SAMPLE_IMPRESSIONS = _get_env_int("WB_FUNNEL_CTR_HIGH_SAMPLE_IMPRESSIONS", 1000)

# WB product content history and local main-photo archive.
WB_CONTENT_HISTORY_ENABLED = os.getenv("WB_CONTENT_HISTORY_ENABLED", "false").lower() in ("true", "1", "yes")
WB_MAIN_PHOTO_ARCHIVE_ENABLED = os.getenv("WB_MAIN_PHOTO_ARCHIVE_ENABLED", "false").lower() in ("true", "1", "yes")
WB_SHOWCASE_PRESENCE_ENABLED = os.getenv("WB_SHOWCASE_PRESENCE_ENABLED", "false").lower() in ("true", "1", "yes")
MARKETPLACE_PRODUCTS_DUAL_WRITE_ENABLED = os.getenv(
    "MARKETPLACE_PRODUCTS_DUAL_WRITE_ENABLED",
    "false",
).lower() in ("true", "1", "yes")
WB_CONTENT_HISTORY_PROJECT_ALLOWLIST = {
    int(value.strip())
    for value in os.getenv("WB_CONTENT_HISTORY_PROJECT_ALLOWLIST", "").split(",")
    if value.strip().isdigit()
}
WB_CONTENT_MEDIA_DIR = os.getenv(
    "WB_CONTENT_MEDIA_DIR",
    os.path.join(tempfile.gettempdir(), "ecomcore", "wb-content-history"),
)
WB_CONTENT_MEDIA_MAX_FILE_SIZE_MB = _get_env_int("WB_CONTENT_MEDIA_MAX_FILE_SIZE_MB", 20)
WB_CONTENT_MEDIA_DOWNLOAD_TIMEOUT_SECONDS = _get_env_int(
    "WB_CONTENT_MEDIA_DOWNLOAD_TIMEOUT_SECONDS",
    20,
)
WB_SHOWCASE_INACTIVE_AFTER_MISSING_RUNS = max(
    1,
    _get_env_int("WB_SHOWCASE_INACTIVE_AFTER_MISSING_RUNS", 2),
)
WB_FUNNEL_CTR_RECOMMENDED_ACTIVE_DAYS = _get_env_int("WB_FUNNEL_CTR_RECOMMENDED_ACTIVE_DAYS", 7)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "openai/gpt-4.1-mini")
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
OPENROUTER_REVIEW_MODEL = os.getenv("OPENROUTER_REVIEW_MODEL", "openai/gpt-5.6-terra")
OPENROUTER_REVIEW_REASONING_EFFORT = os.getenv(
    "OPENROUTER_REVIEW_REASONING_EFFORT",
    "medium",
)
OPENROUTER_REVIEW_TIMEOUT_SECONDS = _get_env_int("OPENROUTER_REVIEW_TIMEOUT_SECONDS", 120)
OPENROUTER_COMPETITOR_NANO_MODEL = os.getenv(
    "OPENROUTER_COMPETITOR_NANO_MODEL",
    "openai/gpt-5-nano",
)
OPENROUTER_COMPETITOR_TERRA_MODEL = os.getenv(
    "OPENROUTER_COMPETITOR_TERRA_MODEL",
    OPENROUTER_REVIEW_MODEL,
)
WB_REVIEW_OPINION_ENABLED = os.getenv("WB_REVIEW_OPINION_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
WB_COMPETITOR_ANALYSIS_ENABLED = os.getenv(
    "WB_COMPETITOR_ANALYSIS_ENABLED",
    "false",
).lower() in ("true", "1", "yes")

SEO_GENERATION_PROVIDER = os.getenv("SEO_GENERATION_PROVIDER", "openrouter")
SEO_GENERATION_PRIMARY_MODEL = os.getenv("SEO_GENERATION_PRIMARY_MODEL", "anthropic/claude-haiku-4.5")
SEO_GENERATION_FALLBACK_MODEL = os.getenv("SEO_GENERATION_FALLBACK_MODEL", "anthropic/claude-sonnet-4.5")
SEO_GENERATION_TEMPERATURE = _get_env_float("SEO_GENERATION_TEMPERATURE", 0.35)
SEO_GENERATION_TOP_P = _get_env_float("SEO_GENERATION_TOP_P", 0.9)
SEO_GENERATION_MAX_TOKENS = _get_env_int("SEO_GENERATION_MAX_TOKENS", 2600)
# Iteration 1 generation discipline (CD-2 in 10_implementation_decision_lock_v1.md):
# default attempts lowered from 3 to 1. Retries happen ONLY on validator hard
# errors; V2-relevance retries were removed.
SEO_GENERATION_MAX_ATTEMPTS = _get_env_int("SEO_GENERATION_MAX_ATTEMPTS", 1)

# Iteration 1 research-preview flag. When false, frontend hides the
# generation endpoint and shows a "coming soon" state rather than a fake
# publishable result. Default OFF per OD-1 package recommendation.
SEO_GENERATION_PREVIEW_ENABLED = (
    os.getenv("SEO_GENERATION_PREVIEW_ENABLED", "false").lower() in ("true", "1", "yes")
)


def _build_seo_scoring_default_weights() -> Dict[str, float]:
    defaults = {
        "semantic_similarity": 0.35,
        "product_type_match": 0.20,
        "attribute_match": 0.15,
        "use_case_match": 0.10,
        "behavior_score": 0.10,
        "frequency_score": 0.10,
        "product_type_mismatch": 0.25,
        "attribute_mismatch": 0.10,
        "cluster_mismatch": 0.15,
        "competition_penalty": 0.10,
    }
    return {
        key: _get_env_float(f"SEO_SCORE_WEIGHT_{key.upper()}", value)
        for key, value in defaults.items()
    }


SEO_SCORING_DEFAULT_WEIGHTS = _build_seo_scoring_default_weights()
SEO_SCORING_WEIGHTS_VERSION = os.getenv("SEO_SCORING_WEIGHTS_VERSION", "v1_default")
