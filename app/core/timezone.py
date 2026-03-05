from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.core.config import settings


def get_orion_tz() -> tzinfo:
    tz_name = settings.timezone_name.strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            pass
    return timezone(timedelta(hours=8))


def now_orion() -> datetime:
    return datetime.now(get_orion_tz())


def now_orion_naive() -> datetime:
    return now_orion().replace(tzinfo=None)


def to_orion(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    tz = get_orion_tz()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)
