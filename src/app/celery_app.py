"""Common Celery app for Beat and Worker."""

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

