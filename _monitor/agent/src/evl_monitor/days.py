"""Local calendar days (the lab's time zone) for the daily summaries."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=4)
def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def day_start(ts: float, tz: str) -> int:
    """Epoch seconds of local midnight for the day containing ts."""
    local = datetime.fromtimestamp(ts, zone(tz))
    return int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def date_of(ts: float, tz: str) -> str:
    return datetime.fromtimestamp(ts, zone(tz)).strftime("%Y-%m-%d")
