"""Bulk-run matcher_v2 for labeled SKUs in category 812.

For every nm_id that has SeoEvalLabel rows (in the specified label_set), call
``run_matcher_v2`` so that the eval harness has matcher_v2 runs to score.

Usage (inside the api container):

    python -m scripts.run_matcher_v2_for_labeled_812 --project-id 1
    python -m scripts.run_matcher_v2_for_labeled_812 --project-id 1 --limit 4
    python -m scripts.run_matcher_v2_for_labeled_812 --project-id 1 --nm-ids 277132340 291861306
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import SeoEvalLabel  # noqa: E402
from app.services.seo.matcher_v2 import run_matcher_v2  # noqa: E402


CATEGORY_ID = 812


def _labeled_nm_ids(session, *, project_id: int, label_set_id: int) -> list[tuple[int, int]]:
    rows = session.execute(
        select(SeoEvalLabel.nm_id, func.count().label("n"))
        .where(
            SeoEvalLabel.project_id == int(project_id),
            SeoEvalLabel.category_id == CATEGORY_ID,
            SeoEvalLabel.label_set_id == int(label_set_id),
        )
        .group_by(SeoEvalLabel.nm_id)
        .order_by(func.count().desc())
    ).all()
    return [(int(nm), int(n)) for nm, n in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run matcher_v2 for labeled SKUs (cat 812).")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--label-set-id", type=int, default=1)
    parser.add_argument("--nm-ids", type=int, nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.nm_ids:
            targets = [(int(x), -1) for x in args.nm_ids]
        else:
            targets = _labeled_nm_ids(
                session, project_id=args.project_id, label_set_id=args.label_set_id
            )
        if args.limit is not None:
            targets = targets[: int(args.limit)]

        print(f"[info] targets: {len(targets)} SKU")
        for nm, n in targets:
            print(f"  nm_id={nm} label_rows={n}")

        ok = 0
        fail = 0
        for idx, (nm, _) in enumerate(targets, start=1):
            t0 = time.time()
            try:
                bundle = run_matcher_v2(
                    session,
                    project_id=int(args.project_id),
                    category_id=CATEGORY_ID,
                    nm_id=int(nm),
                    limit=400,
                    include_rejected=True,
                )
                session.commit()
                dt = time.time() - t0
                print(
                    f"[ok  {idx}/{len(targets)}] nm_id={nm} "
                    f"run_id={getattr(bundle, 'run_id', '?')} in {dt:.1f}s"
                )
                ok += 1
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                dt = time.time() - t0
                print(f"[err {idx}/{len(targets)}] nm_id={nm} after {dt:.1f}s: {exc!r}")
                fail += 1

        print(f"[done] ok={ok} fail={fail} total={len(targets)}")
        return 0 if fail == 0 else 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
