"""RetryingSink: exponential-backoff retries around any TicketSink (P4.6, SPEC §5.1 [12])."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import SinkError
from campuspulse_ai.domain.ports import TicketSink
from campuspulse_ai.domain.values import InboundEvent, TicketLink

T = TypeVar("T")


class RetryingSink:
    """`TicketSink` decorator: retries `create`, `update_status` and `close` on retryable errors.

    At most `max_attempts` calls (Settings `SINK_RETRY_MAX`); before attempt n+1 it sleeps
    `base_backoff_s * 2**(n-1)` (Settings `SINK_RETRY_BASE_S`). A `SinkError(retryable=False)` is
    raised at once, and the last retryable error is raised when the attempts run out; `ActUseCase`
    then records it on the link and carries on. Safe because every inner call is idempotent on the
    ticket id. `handle_inbound` is passed through without retries (signature checks are
    deterministic). `name` is the inner sink's name.
    """

    def __init__(
        self,
        inner: TicketSink,
        max_attempts: int,
        base_backoff_s: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1 or base_backoff_s < 0:
            raise ValueError("max_attempts must be >= 1 and base_backoff_s >= 0")
        self.name = inner.name
        self._inner = inner
        self._max_attempts = max_attempts
        self._base = base_backoff_s
        self._sleep = sleep

    def create(self, ticket: Ticket) -> TicketLink:
        return self._retry(lambda: self._inner.create(ticket))

    def update_status(self, ticket: Ticket) -> None:
        self._retry(lambda: self._inner.update_status(ticket))

    def close(self, ticket: Ticket) -> None:
        self._retry(lambda: self._inner.close(ticket))

    def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None:
        return self._inner.handle_inbound(payload, signature)

    def _retry(self, call: Callable[[], T]) -> T:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return call()
            except SinkError as exc:
                if not exc.retryable or attempt == self._max_attempts:
                    raise
                self._sleep(self._base * 2 ** (attempt - 1))
        raise AssertionError("unreachable: the loop returns or raises")
