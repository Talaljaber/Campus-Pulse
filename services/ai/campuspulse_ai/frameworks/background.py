"""Background loops of the API process (P4.9): the SLA scanner.

One uvicorn worker (Dockerfile, ARCHITECTURE §3.15), so exactly one scanner runs. The scan itself is
blocking (database and sink calls), so it runs in a worker thread and never stalls the event loop.
"""

from __future__ import annotations

import asyncio
import logging
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
