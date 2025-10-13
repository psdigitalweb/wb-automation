import argparse
import logging
import os
import sys
import time
from typing import List, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .wb_api import WbApiClient
from .db_tariffs import ensure_schema, insert_commission, insert_box, insert_pallet, insert_return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest WB tariffs")
    parser.add_argument("--dry-run", action="store_true", help="Do not write into DB")
    parser.add_argument(
        "--only",
        action="append",
        choices=["commission", "box", "pallet", "return"],
        help="Limit to selected endpoints (can be repeated)",
    )
    return parser.parse_args()


def _get_targets(only: List[str] | None) -> List[str]:
    default = ["commission", "box", "pallet", "return"]
    if not only:
        return default
    # keep order as default but filter
    return [t for t in default if t in set(only)]


def _build_engine() -> Tuple[str, Engine]:
    # Prefer DATABASE_URL used by FastAPI app
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if "psycopg://" in database_url:
            database_url = database_url.replace("psycopg://", "psycopg2://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    else:
        # Fallback to settings components if present
        from . import settings

        database_url = settings.SQLALCHEMY_DATABASE_URL

    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    return database_url, engine


def main() -> int:
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("wb.ingest.tariffs")

    args = parse_args()
    targets = _get_targets(args.only)

    # WB client params from env (with defaults in client)
    client = WbApiClient(
        base_url=os.getenv("WB_API_BASE", "https://common-api.wildberries.ru"),
        token=os.getenv("WB_API_TOKEN") or os.getenv("WB_TOKEN"),
        min_interval=float(os.getenv("WB_API_MIN_INTERVAL", "0.3")),
        max_retries=int(os.getenv("WB_API_MAX_RETRIES", "5")),
        timeout_seconds=float(os.getenv("WB_API_TIMEOUT", "15")),
        logger=logging.getLogger("wb.tariffs"),
    )

    # Box tariffs date parameter
    box_date = os.getenv("WB_TARIFFS_BOX_DATE")
    box_params = {"date": box_date} if box_date else {}

    # Pallet tariffs date parameter
    pallet_date = os.getenv("WB_TARIFFS_PALLET_DATE")
    pallet_params = {"date": pallet_date} if pallet_date else {}

    # Return tariffs date parameter
    return_date = os.getenv("WB_TARIFFS_RETURN_DATE")
    return_params = {"date": return_date} if return_date else {}

    # DB
    _, engine = _build_engine()
    ensure_schema(engine)

    # Fetch
    start_ts = time.monotonic()
    results: dict = {"commission": None, "box": None, "pallet": None, "return": None}
    sizes: dict = {"commission": 0, "box": 0, "pallet": 0, "return": 0}
    statuses: dict = {"commission": "skipped", "box": "skipped", "pallet": "skipped", "return": "skipped"}

    try:
        for target in targets:
            t0 = time.monotonic()
            if target == "commission":
                data = client.get_tariffs_commission()
            elif target == "box":
                data = client.get_tariffs_box(params=box_params)
            elif target == "pallet":
                data = client.get_tariffs_pallet(params=pallet_params)
            elif target == "return":
                data = client.get_tariffs_return(params=return_params)
            else:
                continue

            results[target] = data
            try:
                import json

                sizes[target] = len(json.dumps(data).encode("utf-8"))
            except Exception:
                sizes[target] = 0
            statuses[target] = "ok"
            logger.info("OK %s bytes=%s", target, sizes[target])
            _ = time.monotonic() - t0
    except PermissionError as e:
        logger.error("%s", str(e))
        print("Check WB_API_TOKEN", file=sys.stderr)
        return 1

    # Store if not dry run
    if not args.dry_run:
        if results.get("commission") is not None:
            record_id = insert_commission(engine, results["commission"])  # type: ignore[arg-type]
            logger.info("INSERT ok table=tariffs_commission id=%s bytes=%s", record_id, sizes["commission"])
        if results.get("box") is not None:
            record_id = insert_box(engine, results["box"])  # type: ignore[arg-type]
            logger.info("INSERT ok table=tariffs_box id=%s bytes=%s", record_id, sizes["box"])
        if results.get("pallet") is not None:
            record_id = insert_pallet(engine, results["pallet"])  # type: ignore[arg-type]
            logger.info("INSERT ok table=tariffs_pallet id=%s bytes=%s", record_id, sizes["pallet"])
        if results.get("return") is not None:
            record_id = insert_return(engine, results["return"])  # type: ignore[arg-type]
            logger.info("INSERT ok table=tariffs_return id=%s bytes=%s", record_id, sizes["return"])
    else:
        # Dry run logging
        if results.get("commission") is not None:
            logger.info("DRY-RUN skip write table=tariffs_commission bytes=%s", sizes["commission"])
        if results.get("box") is not None:
            logger.info("DRY-RUN skip write table=tariffs_box bytes=%s", sizes["box"])
        if results.get("pallet") is not None:
            logger.info("DRY-RUN skip write table=tariffs_pallet bytes=%s", sizes["pallet"])
        if results.get("return") is not None:
            logger.info("DRY-RUN skip write table=tariffs_return bytes=%s", sizes["return"])

    elapsed = round(time.monotonic() - start_ts, 3)
    summary = (
        f"Summary: commission={statuses['commission']}({sizes['commission']}), "
        f"box={statuses['box']}({sizes['box']}), "
        f"pallet={statuses['pallet']}({sizes['pallet']}), "
        f"return={statuses['return']}({sizes['return']}); "
        f"dry_run={args.dry_run}; elapsed={elapsed}s"
    )
    logger.info(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())


