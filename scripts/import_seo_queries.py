#!/usr/bin/env python3
"""Import one local WB SEO query CSV for a project/category."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.db import SessionLocal
from app.services.seo.query_pipeline import CsvImportError, import_queries_from_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one local WB SEO query CSV")
    parser.add_argument("--csv-path", required=True, help="Absolute or relative path to local CSV file")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id scope")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        diagnostics = import_queries_from_csv(
            session,
            csv_path=args.csv_path,
            project_id=args.project_id,
            category_id=args.category_id,
        )
        session.commit()
        print(json.dumps(diagnostics.to_dict(), ensure_ascii=False, indent=2))
        return 0
    except CsvImportError as exc:
        session.rollback()
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    except Exception as exc:
        session.rollback()
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
