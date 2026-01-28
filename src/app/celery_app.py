"""Common Celery app for Beat and Worker."""

import importlib
import pkgutil
from typing import List

from celery import Celery
from celery.schedules import crontab
from app import settings

celery_app = Celery(
    "wb",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Celery Beat schedule
celery_app.conf.beat_schedule = {
    "sync-frontend-prices-every-4-hours": {
        "task": "app.tasks.frontend_prices.sync_frontend_prices_brand",
        "schedule": crontab(minute=0, hour="*/4"),  # Every 4 hours at :00
    },
    "ingest-wb-tariffs-all-daily": {
        "task": "app.tasks.wb_tariffs.ingest_wb_tariffs_all",
        # Once per day at 03:30 server time (UTC in our Celery config)
        "schedule": crontab(minute=30, hour=3),
        # Worker listens on default 'celery' queue.
        "options": {"queue": "celery"},
    },
    # Dispatcher: checks ingest_schedules every minute and enqueues due runs
    "dispatch-ingest-schedules-every-minute": {
        "task": "app.tasks.ingest_dispatcher.dispatch_due_schedules",
        "schedule": crontab(minute="*"),
        # Worker listens on default 'celery' queue.
        "options": {"queue": "celery"},
    },
    # Price discrepancies diagnostics: run every 6 hours to check data availability
    # This ensures we catch missing data issues even if post-ingest hooks fail
    "diagnose-price-discrepancies-data-every-6-hours": {
        "task": "app.tasks.price_discrepancies.diagnose_all_projects_data_availability",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours at :00
        # Worker listens on default 'celery' queue.
        "options": {"queue": "celery"},
    },
}

celery_app.conf.timezone = "UTC"
# IMPORTANT:
# Celery Beat uses a persistent schedule file (celerybeat-schedule) and can keep old
# routing options (like queue name) even after code changes. Bump the filename so
# Beat reloads schedule entries with current config.
celery_app.conf.beat_schedule_filename = "celerybeat-schedule-v2"

def _import_all_task_modules() -> List[str]:
    """Import all modules under `app.tasks.*` so Celery registers task decorators.

    This avoids manual imports in `app/tasks/__init__.py` and automatically picks up
    new task modules when they are added.
    """
    imported: List[str] = []
    try:
        import app.tasks as tasks_pkg
    except Exception as e:
        raise RuntimeError(
            "Celery startup failed: cannot import task package 'app.tasks'"
        ) from e

    try:
        for module_info in pkgutil.walk_packages(
            tasks_pkg.__path__,
            prefix=f"{tasks_pkg.__name__}.",
        ):
            # Import modules; skip packages (walk_packages yields both)
            name = module_info.name
            importlib.import_module(name)
            imported.append(name)
    except Exception as e:
        raise RuntimeError(
            "Celery startup failed: error while importing task modules under 'app.tasks.*'"
        ) from e
    return imported


# Auto-import tasks for both worker and beat processes.
_import_all_task_modules()