from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from fastapi import HTTPException, status


DEFAULT_TIMEZONE = "Europe/Istanbul"


def validate_cron(cron_expr: str) -> None:
    """Validate a 5-field cron expression.

    Raises HTTPException 422 if invalid.
    """
    try:
        # croniter itself validates format
        croniter(cron_expr, datetime.utcnow())
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid cron expression: {cron_expr}. Error: {exc}",
        )


def _get_timezone(tz_name: str) -> ZoneInfo:
    """Resolve timezone name to ZoneInfo with validation."""
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid timezone: {tz_name}. Error: {exc}",
        )


def compute_next_run(cron_expr: str, timezone: str, from_dt: datetime) -> datetime:
    """Compute next run datetime in UTC for given cron and timezone.

    Args:
        cron_expr: 5-field cron expression (minute, hour, dom, month, dow)
        timezone: IANA timezone string
        from_dt: current reference time (assumed UTC, tz-aware or naive)

    Returns:
        next_run_at in UTC as aware datetime
    """
    # Ensure `from_dt` is timezone-aware UTC
    if from_dt.tzinfo is None:
        from_dt_utc = from_dt.replace(tzinfo=ZoneInfo("UTC"))
    else:
        from_dt_utc = from_dt.astimezone(ZoneInfo("UTC"))

    tz = _get_timezone(timezone or DEFAULT_TIMEZONE)

    # Convert reference time to schedule timezone
    from_local = from_dt_utc.astimezone(tz)

    try:
        itr = croniter(cron_expr, from_local)
        next_local = itr.get_next(datetime)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid cron expression: {cron_expr}. Error: {exc}",
        )

    # Convert back to UTC for storage
    next_utc = next_local.astimezone(ZoneInfo("UTC"))
    return next_utc


def format_cron_human_readable(cron_expr: str) -> str:
    """Convert cron expression to human-readable format.
    
    Examples:
        "0 */4 * * *" -> "каждые 4 часа"
        "30 3 * * *" -> "ежедневно в 03:30"
        "0 0 * * *" -> "ежедневно в 00:00"
        "*/15 * * * *" -> "каждые 15 минут"
        "0 9 * * 1" -> "каждый понедельник в 09:00"
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return cron_expr
    
    minute, hour, day_of_month, month, day_of_week = parts
    
    # Every N minutes
    if minute.startswith("*/") and hour == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
        try:
            n = int(minute[2:])
            if n == 1:
                return "каждую минуту"
            elif n < 60:
                return f"каждые {n} минут"
        except ValueError:
            pass
    
    # Every N hours (at minute 0)
    if minute == "0" and hour.startswith("*/") and day_of_month == "*" and month == "*" and day_of_week == "*":
        try:
            n = int(hour[2:])
            if n == 1:
                return "каждый час"
            else:
                return f"каждые {n} часа"
        except ValueError:
            pass
    
    # Daily at specific time
    if minute.isdigit() and hour.isdigit() and day_of_month == "*" and month == "*" and day_of_week == "*":
        try:
            m = int(minute)
            h = int(hour)
            return f"ежедневно в {h:02d}:{m:02d}"
        except ValueError:
            pass
    
    # Weekly on specific day
    if minute.isdigit() and hour.isdigit() and day_of_month == "*" and month == "*" and day_of_week.isdigit():
        try:
            m = int(minute)
            h = int(hour)
            dow = int(day_of_week)
            days = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
            if 0 <= dow <= 6:
                return f"каждый {days[dow]} в {h:02d}:{m:02d}"
        except ValueError:
            pass
    
    # Monthly on specific day
    if minute.isdigit() and hour.isdigit() and day_of_month.isdigit() and month == "*" and day_of_week == "*":
        try:
            m = int(minute)
            h = int(hour)
            dom = int(day_of_month)
            return f"ежемесячно {dom}-го числа в {h:02d}:{m:02d}"
        except ValueError:
            pass
    
    # Fallback: return original cron expression
    return cron_expr

