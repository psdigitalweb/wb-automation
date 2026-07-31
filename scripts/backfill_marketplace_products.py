"""Plan or apply the marketplace-neutral product identity backfill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.services.marketplace_product_backfill import (  # noqa: E402
    backfill_wildberries_marketplace_products,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill legacy WB products into marketplace_products. Defaults to dry-run."
    )
    parser.add_argument("--project-id", type=int, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the backfill. Without this flag no data is changed.",
    )
    args = parser.parse_args()

    result = backfill_wildberries_marketplace_products(
        project_id=args.project_id,
        dry_run=not args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
