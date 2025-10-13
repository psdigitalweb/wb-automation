import argparse
import logging
import os
import sys
from typing import List

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .wb_api import WbApiClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest WB warehouses data")
    parser.add_argument("--dry-run", action="store_true", help="Do not write into DB")
    parser.add_argument(
        "--only",
        choices=["offices", "warehouses", "all"],
        default="all",
        help="Which data to fetch (default: all)",
    )
    return parser.parse_args()


def _build_engine() -> Engine:
    # Use existing engine from app.main
    from .main import engine
    return engine


def main() -> int:
    load_dotenv()

    # Check required environment variables first
    token = os.getenv("WB_API_TOKEN") or os.getenv("WB_TOKEN")
    if not token:
        # Set up basic logging for error message
        logging.basicConfig(
            level=logging.ERROR,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        logger = logging.getLogger("wb.ingest.warehouses")
        logger.error("WB_API_TOKEN is missing, cannot call Wildberries API.")
        return 2

    # Read environment parameters with defaults
    min_interval = os.getenv("WB_API_MIN_INTERVAL")
    max_retries = os.getenv("WB_API_MAX_RETRIES")
    timeout = os.getenv("WB_API_TIMEOUT")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    # Set up logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("wb.ingest.warehouses")

    # Validate and log defaults for missing parameters
    if not min_interval:
        logger.info("using default WB_API_MIN_INTERVAL=0.2")
        min_interval = "0.2"
    if not max_retries:
        logger.info("using default WB_API_MAX_RETRIES=3")
        max_retries = "3"
    if not timeout:
        logger.info("using default WB_API_TIMEOUT=15")
        timeout = "15"

    args = parse_args()

    # Log effective configuration
    logger.info("env min_interval=%s, max_retries=%s, timeout=%s, log_level=%s", 
                min_interval, max_retries, timeout, log_level)

    # WB client params from env
    client = WbApiClient(
        token=token,
        min_interval=float(min_interval),
        max_retries=int(max_retries),
        timeout_seconds=float(timeout),
        logger=logging.getLogger("wb.api"),
    )

    # DB
    engine = _build_engine()
    
    # Import DB functions
    from .db_warehouses import ensure_schema, upsert_wb_offices, upsert_seller_warehouses
    ensure_schema(engine)

    try:
        if args.only in ["offices", "all"]:
            logger.info("Fetching offices...")
            offices = client.get_offices()
            logger.info("fetched offices=%s", len(offices))
            
            if args.dry_run:
                if offices:
                    first = offices[0]
                    logger.info("dry-run offices count=%s", len(offices))
                    logger.info("dry-run sample: id=%s name=%s city=%s", 
                              first.get("id"), first.get("name"), first.get("city"))
                else:
                    logger.info("dry-run offices count=0")
            else:
                inserted, updated = upsert_wb_offices(engine, offices)

        if args.only in ["warehouses", "all"]:
            logger.info("Fetching warehouses...")
            warehouses = client.get_seller_warehouses()
            logger.info("fetched warehouses=%s", len(warehouses))
            
            if args.dry_run:
                if warehouses:
                    first = warehouses[0]
                    logger.info("dry-run warehouses count=%s", len(warehouses))
                    logger.info("dry-run sample: id=%s name=%s officeId=%s", 
                              first.get("id"), first.get("name"), first.get("officeId"))
                else:
                    logger.info("dry-run warehouses count=0")
            else:
                inserted, updated = upsert_seller_warehouses(engine, warehouses)

        return 0

    except PermissionError as e:
        logger.error("%s", str(e))
        print("Check WB_API_TOKEN", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error("Unexpected error: %s", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
