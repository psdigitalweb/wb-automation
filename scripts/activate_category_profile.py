"""CLI entrypoint for safe category-profile activation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.db import SessionLocal  # noqa: E402
from app.services.seo.category_profile_admin import activate_category_profile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate a derived category profile by profile ID.")
    parser.add_argument("--profile-id", type=int, required=True, help="Category-profile row ID.")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        row = activate_category_profile(session, int(args.profile_id))
        payload = {
            "profile_id": int(row.id),
            "project_id": int(row.project_id),
            "category_id": int(row.category_id),
            "version": str(row.version),
            "is_active": bool(row.is_active),
        }
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
