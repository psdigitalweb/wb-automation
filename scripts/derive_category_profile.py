"""CLI entrypoint for Phase 0 Step 3 category-profile skeleton derive."""

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
from app.services.seo.category_profile_derive import derive_category_profile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive a category profile skeleton for one category.")
    parser.add_argument("--project", type=int, required=True, help="Project ID.")
    parser.add_argument("--category", type=int, required=True, help="WB category ID.")
    parser.add_argument("--dry-run", action="store_true", help="Build payload without writing DB rows or snapshots.")
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Reserved for later steps. Step 3 keeps activation disabled.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output file or root directory for the snapshot path.",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        result = derive_category_profile(
            project_id=args.project,
            category_id=args.category,
            session=session,
            activate=bool(args.activate),
            dry_run=bool(args.dry_run),
            out_path=args.out,
        )
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "profile_version": result.profile_version,
                "snapshot_path": str(result.snapshot_path),
                "self_check_status": result.self_check.status,
                "status": result.status,
                "dry_run": bool(args.dry_run),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
