"""QueryCachingMemoryStore: one live-memory query per request instead of two (P4.13 latency).

The kNN member runs once for the category head and once for the priority head, and each asks the live
memory for the neighbours of the same embedding with the same `k` and `min_sim` (one pgvector RPC
each, about one network round trip). This decorator remembers the last answer for `ttl_s` seconds and
returns it when the identical question comes again, so a request pays for one RPC. The answer is the
same data the second RPC would return (a correction saved between the two calls of one request is
not seen by its second head, which is the consistent behaviour anyway). `add` and `deactivate` clear
the cache, so a staff correction is visible to the very next request.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.ports import Clock, MemoryStore
from campuspulse_ai.domain.values import MemoryStats, Neighbor

_Key = tuple[tuple[float, ...], int, float]


class QueryCachingMemoryStore:
    """`MemoryStore` decorator: caches the last `neighbors(embedding, k, min_sim)` answer for `ttl_s`.

    Thread-safe (uvicorn runs sync routes in a thread pool). `ttl_s <= 0` disables the cache. Errors
    are the inner store's; a failed query is not cached.
    """

    def __init__(self, inner: MemoryStore, clock: Clock, ttl_s: float) -> None:
        self._inner = inner
        self._clock = clock
        self._ttl_s = ttl_s
        self._lock = threading.Lock()
        self._last: tuple[_Key, datetime, list[Neighbor]] | None = None

    def neighbors(self, embedding: Sequence[float], k: int, min_sim: float) -> list[Neighbor]:
        key: _Key = (tuple(float(x) for x in embedding), k, min_sim)
        now = self._clock.now()
        with self._lock:
            last = self._last
        if last is not None and last[0] == key and (now - last[1]).total_seconds() < self._ttl_s:
            return list(last[2])
        found = self._inner.neighbors(embedding, k, min_sim)
        if self._ttl_s > 0:
            with self._lock:
                self._last = (key, now, list(found))
        return found

    def add(self, ex: MemoryExample) -> MemoryExample:
        self._clear()
        try:
            return self._inner.add(ex)
        finally:
            self._clear()  # a query that raced the write must not keep the old answer

    def deactivate(self, id: str) -> None:
        self._clear()
        try:
            self._inner.deactivate(id)
        finally:
            self._clear()

    def active(self, since: datetime | None = None) -> list[MemoryExample]:
        return self._inner.active(since)

    def stats(self) -> MemoryStats:
        return self._inner.stats()

    def _clear(self) -> None:
        with self._lock:
            self._last = None
