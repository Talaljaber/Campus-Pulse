"""`SystemClock`: the real `Clock`, in Asia/Amman (P1.15, LD-22)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

AMMAN_TZ = "Asia/Amman"
# Jordan has kept UTC+3 all year since 2022; used only where the IANA database is unavailable
# (Windows without the `tzdata` package).
AMMAN_FALLBACK = timezone(timedelta(hours=3), AMMAN_TZ)


def amman() -> tzinfo:
    """The Asia/Amman zone (IANA if available, else the fixed UTC+3 offset)."""
    try:
        return ZoneInfo(AMMAN_TZ)
    except ZoneInfoNotFoundError:
        return AMMAN_FALLBACK


class SystemClock:
    """Implements `domain.ports.Clock`: `now()` is the current time, tz-aware in Asia/Amman."""

    def __init__(self) -> None:
        self._tz = amman()

    def now(self) -> datetime:
        return datetime.now(self._tz)
