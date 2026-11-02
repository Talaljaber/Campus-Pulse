"""Background triggers of the API process (P4.9, P9.4): the SLA reminder loop and the response sweeper.

One uvicorn worker (Dockerfile, ARCHITECTURE §3.15), so exactly one scanner runs. The scan itself is
blocking (database and sink calls), so it runs in a worker thread and never stalls the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import datetime

from campuspulse_ai.domain.ports import Clock

log = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60

Scan = Callable[[datetime], list[str]]


async def sla_loop(scan: Scan, clock: Clock, interval_s: float) -> None:
    """Run `scan(clock.now())` now and then every `interval_s` seconds until cancelled.

    A failing scan is logged and the loop goes on (the next scan retries); cancellation (app
    shutdown) ends it.
    """
    while True:
        try:
            escalated = await asyncio.to_thread(scan, clock.now())
            if escalated:
                log.info("SLA scan escalated %d ticket(s): %s", len(escalated), escalated)
        except Exception:  # keep the loop alive; the error is logged with its traceback
            log.exception("SLA scan failed")
        await asyncio.sleep(interval_s)


class SlaSweeper:
    """Run the SLA scan after API responses, at most once per `min_interval_s` (P9.4).

    `maybe_run()` returns at once when the last run is younger than `min_interval_s` or another run is in
    progress (non-blocking lock); otherwise it runs `scan(clock.now())` in a worker thread. Every scan is
    idempotent (`claim_reminder`), so a duplicate run could never send twice anyway. Never raises.
    """

    def __init__(self, scan: Scan, clock: Clock, min_interval_s: float) -> None:
        self._scan = scan
        self._clock = clock
        self._min_interval_s = min_interval_s
        self._lock = threading.Lock()
        self._last: datetime | None = None

    async def maybe_run(self) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            now = self._clock.now()
            if self._last is not None and (now - self._last).total_seconds() < self._min_interval_s:
                return
            self._last = now
            reminded = await asyncio.to_thread(self._scan, now)
            if reminded:
                log.info("SLA sweep reminded %d ticket(s): %s", len(reminded), reminded)
        except Exception:  # a sweep must never break the response path; the next one retries
            log.exception("SLA sweep failed")
        finally:
            self._lock.release()
