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
}

celery_app.conf.timezone = "UTC"

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