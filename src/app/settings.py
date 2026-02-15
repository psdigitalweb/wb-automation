import os
from dotenv import load_dotenv

# Use override=True to ensure .env file values take precedence over existing env vars
# This is important when .env is mounted as volume and may have updated values
load_dotenv(override=True)

def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default

POSTGRES_DB = os.getenv("POSTGRES_DB", "wb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "wb")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "wbpassword")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

# Service-level WB token for marketplace-wide operations (e.g. tariffs)
WB_SERVICE_TOKEN = os.getenv("WB_SERVICE_TOKEN") or os.getenv("WB_TOKEN", "MOCK")
WB_TOKEN = os.getenv("WB_TOKEN", "MOCK")
WB_VALIDATE_TOKEN = os.getenv("WB_VALIDATE_TOKEN", "true").lower() in ("true", "1", "yes")
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
TZ = os.getenv("TZ", "Europe/Moscow")

SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Directory for storing uploaded Internal Data files (local filesystem).
INTERNAL_DATA_DIR = os.getenv("INTERNAL_DATA_DIR", "/data/internal_data")

# Ingest: if no heartbeat for longer than TTL, run is considered stuck.
INGEST_STUCK_TTL_SECONDS_DEFAULT = _get_env_int("INGEST_STUCK_TTL_SECONDS_DEFAULT", 1800)

# Frontend prices (catalog.wb.ru): rate-limit and runtime guards
FRONTEND_PRICES_MAX_RUNTIME_SECONDS = _get_env_int("FRONTEND_PRICES_MAX_RUNTIME_SECONDS", 1200)
FRONTEND_PRICES_MAX_TOTAL_RETRY_WAIT_SECONDS = _get_env_int("FRONTEND_PRICES_MAX_TOTAL_RETRY_WAIT_SECONDS", 300)
FRONTEND_PRICES_MAX_RETRY_SLEEP_SECONDS = _get_env_int("FRONTEND_PRICES_MAX_RETRY_SLEEP_SECONDS", 120)
FRONTEND_PRICES_RATE_LIMIT_BACKOFF_MINUTES = _get_env_int("FRONTEND_PRICES_RATE_LIMIT_BACKOFF_MINUTES", 15)
# HTTP timeout (seconds). With proxy, responses are often slower — set 60–90 locally if you see ReadTimeout.
FRONTEND_PRICES_HTTP_TIMEOUT = _get_env_int("FRONTEND_PRICES_HTTP_TIMEOUT", 30)
# With rotating proxy: min retries per request before giving up (each attempt = new IP). Default 10.
FRONTEND_PRICES_HTTP_MIN_RETRIES = _get_env_int("FRONTEND_PRICES_HTTP_MIN_RETRIES", 10)
# Random jitter (seconds) added to timeout per attempt to avoid killing requests too early. Default 10.
FRONTEND_PRICES_HTTP_TIMEOUT_JITTER = _get_env_int("FRONTEND_PRICES_HTTP_TIMEOUT_JITTER", 10)
def _get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default
# Min share of expected_total we must have saved to consider run success (0.0–1.0). Default 0.8 = 80%.
FRONTEND_PRICES_MIN_COVERAGE_RATIO = _get_env_float("FRONTEND_PRICES_MIN_COVERAGE_RATIO", 0.80)# Local dev: allow unauthenticated access to actual-v2-preview (default False, do not enable in prod)
ALLOW_UNAUTH_LOCAL = os.getenv("ALLOW_UNAUTH_LOCAL", "false").lower() in ("true", "1", "yes")