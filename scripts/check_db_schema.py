"""Simple schema check script for local/dev environments.

Usage (from repo root):

    python -m scripts.check_db_schema

Or in Docker:

    docker compose run --rm api python -m scripts.check_db_schema

The script checks whether the `marketplace_api_snapshots` table exists in the
current DATABASE_URL / POSTGRES_* target and prints a human-readable message.
Exit codes:
  - 0: table exists
  - 1: table missing or database not reachable
"""

from __future__ import annotations

import sys

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.db import engine


def main() -> int:
  print("Checking for table: marketplace_api_snapshots")
  try:
      with engine.connect() as conn:
          # Use to_regclass to detect table existence in PostgreSQL
          result = conn.execute(
              text("SELECT to_regclass('public.marketplace_api_snapshots')")
          ).scalar()

      if result is None:
          print(
              "❌ Table 'marketplace_api_snapshots' is MISSING in the current database.\n"
              "Run Alembic migrations, for example:\n"
              "  alembic upgrade head\n"
              "or via Docker:\n"
              "  docker compose run --rm api alembic upgrade head"
          )
          return 1

      print("✅ Table 'marketplace_api_snapshots' exists.")
      return 0
  except (OperationalError, ProgrammingError) as e:
      print("❌ Failed to query database for schema information.")
      print(f"Error: {e}")
      print(
          "Make sure your DATABASE_URL / POSTGRES_* settings are correct and the "
          "database is reachable, then run Alembic migrations:\n"
          "  alembic upgrade head"
      )
      return 1
  except Exception as e:
      print("❌ Unexpected error while checking schema:")
      print(e)
      return 1


if __name__ == "__main__":
  sys.exit(main())

