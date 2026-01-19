import os
from dotenv import load_dotenv

# Use override=True to ensure .env file values take precedence over existing env vars
# This is important when .env is mounted as volume and may have updated values
load_dotenv(override=True)

POSTGRES_DB = os.getenv("POSTGRES_DB", "wb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "wb")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "wbpass")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

WB_TOKEN = os.getenv("WB_TOKEN", "MOCK")
WB_VALIDATE_TOKEN = os.getenv("WB_VALIDATE_TOKEN", "true").lower() in ("true", "1", "yes")
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
TZ = os.getenv("TZ", "Europe/Moscow")

SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
