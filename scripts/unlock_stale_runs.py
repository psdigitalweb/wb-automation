#!/usr/bin/env python3
"""Utility script to unlock stale running ingest_runs.

Stale runs are those with status='running' that haven't been updated
for more than the specified threshold (default 30 minutes).

Usage:
    python scripts/unlock_stale_runs.py [--threshold-minutes 30] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory to path to import app modules
sys.path.insert(0, str(__file__).replace("/scripts/unlock_stale_runs.py", ""))

from sqlalchemy import text

from app.db import engine


def unlock_stale_runs(threshold_minutes: int = 30, dry_run: bool = False) -> int:
    """Unlock stale running ingest_runs by marking them as failed.
    
    Args:
        threshold_minutes: Consider runs stale if updated_at is older than this
        dry_run: If True, only show what would be updated without making changes
    
    Returns:
        Number of runs unlocked
    """
    threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    
    # Find stale runs
    find_sql = text("""
        SELECT id, project_id, marketplace_code, job_code, started_at, updated_at
        FROM ingest_runs
        WHERE status = 'running'
          AND updated_at < :threshold
        ORDER BY updated_at ASC
    """)
    
    with engine.connect() as conn:
        stale_runs = conn.execute(
            find_sql,
            {"threshold": threshold}
        ).mappings().all()
    
    if not stale_runs:
        print(f"No stale runs found (threshold: {threshold_minutes} minutes)")
        return 0
    
    print(f"Found {len(stale_runs)} stale run(s):")
    for run in stale_runs:
        age_minutes = (datetime.now(timezone.utc) - run["updated_at"]).total_seconds() / 60
        print(
            f"  Run {run['id']}: project_id={run['project_id']}, "
            f"marketplace={run['marketplace_code']}, job={run['job_code']}, "
            f"age={age_minutes:.1f} minutes"
        )
    
    if dry_run:
        print("\n[DRY RUN] Would unlock these runs. Run without --dry-run to apply.")
        return len(stale_runs)
    
    # Unlock stale runs
    unlock_sql = text("""
        UPDATE ingest_runs
        SET status = 'failed',
            finished_at = now(),
            duration_ms = CASE
                WHEN started_at IS NOT NULL THEN
                    EXTRACT(EPOCH FROM (now() - started_at)) * 1000::bigint
                ELSE NULL
            END,
            error_message = 'Stale run unlocked (was stuck in running state)',
            error_trace = 'Unlocked by unlock_stale_runs.py script',
            stats_json = '{"ok": false, "reason": "stale_run_unlocked"}'::jsonb,
            updated_at = now()
        WHERE id = :run_id AND status = 'running'
        RETURNING id
    """)
    
    unlocked_count = 0
    with engine.begin() as conn:
        for run in stale_runs:
            result = conn.execute(unlock_sql, {"run_id": run["id"]}).mappings().first()
            if result:
                unlocked_count += 1
                print(f"✓ Unlocked run {run['id']}")
            else:
                print(f"✗ Run {run['id']} was already updated (race condition)")
    
    print(f"\nUnlocked {unlocked_count} stale run(s)")
    return unlocked_count


def main():
    parser = argparse.ArgumentParser(
        description="Unlock stale running ingest_runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (show what would be unlocked)
  python scripts/unlock_stale_runs.py --dry-run
  
  # Unlock runs older than 30 minutes (default)
  python scripts/unlock_stale_runs.py
  
  # Unlock runs older than 10 minutes
  python scripts/unlock_stale_runs.py --threshold-minutes 10
        """
    )
    parser.add_argument(
        "--threshold-minutes",
        type=int,
        default=30,
        help="Consider runs stale if older than this (default: 30)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be unlocked without making changes"
    )
    
    args = parser.parse_args()
    
    try:
        unlock_stale_runs(
            threshold_minutes=args.threshold_minutes,
            dry_run=args.dry_run
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
