"""Create baseline content versions for existing WB products.

Usage:
    python scripts/backfill_wb_product_content_history.py --project-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.db import engine  # noqa: E402
from app.services.wb_product_content.history import persist_product_content  # noqa: E402
from app.services.wb_product_content.main_photo import prepare_main_photo_attempts  # noqa: E402


def _load_batch(project_id: int, after_id: int, batch_size: int) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, nm_id, vendor_code, title, brand, subject_id,
                       subject_name, description, price_u, sale_price_u,
                       rating, feedbacks, sizes, colors, pics, dimensions,
                       characteristics, created_at_api, need_kiz, raw
                FROM products
                WHERE project_id = :project_id
                  AND id > :after_id
                  AND content_version IS NULL
                ORDER BY id
                LIMIT :batch_size
                """
            ),
            {
                "project_id": int(project_id),
                "after_id": int(after_id),
                "batch_size": int(batch_size),
            },
        ).mappings().all()
    return [dict(row) for row in rows]


async def run(project_id: int, batch_size: int) -> Dict[str, int]:
    after_id = 0
    stats = {"processed": 0, "versions_created": 0, "photo_failures": 0}
    while True:
        rows = _load_batch(project_id, after_id, batch_size)
        if not rows:
            break
        attempts = await prepare_main_photo_attempts(project_id=project_id, rows=rows)
        for row in rows:
            result = persist_product_content(
                row=row,
                project_id=project_id,
                ingest_run_id=None,
                photo_attempt=attempts.get(int(row["nm_id"])),
            )
            stats["processed"] += 1
            stats["versions_created"] += int(bool(result["changed"]))
            stats["photo_failures"] += int(result.get("photo_status") == "failed")
            after_id = max(after_id, int(row["id"]))
        print(
            "backfill_wb_product_content_history: "
            f"project_id={project_id} processed={stats['processed']} after_id={after_id}"
        )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True, type=int)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    result = asyncio.run(run(args.project_id, max(1, min(args.batch_size, 1000))))
    print(f"backfill_wb_product_content_history: completed {result}")


if __name__ == "__main__":
    main()
