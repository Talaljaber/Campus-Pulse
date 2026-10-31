"""NullMemoryStore: the offline MemoryStore (ARCHITECTURE §3.11, LD-22).

The frozen evaluation must not depend on live memory, so build_offline wires this store: it is
always empty, and writing to it is a bug.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.values import MemoryStats, Neighbor


class NullMemoryStore:
    """MemoryStore that holds nothing.

    `active`/`neighbors` return [], `stats` is all zeros, `deactivate` raises NotFound (no id
    exists), and `add` raises StoreError: offline code must never learn from memory.
    """

    def add(self, ex: MemoryExample) -> MemoryExample:
        raise StoreError("NullMemoryStore is read-only: live memory is disabled offline")

    def active(self, since: datetime | None = None) -> list[MemoryExample]:
        return []

    def deactivate(self, id: str) -> None:
        raise NotFound(f"memory example {id} not found (NullMemoryStore is always empty)")

    def stats(self) -> MemoryStats:
        return MemoryStats(active=0, total=0, by_category={}, last_added_at=None)

    def neighbors(self, embedding: Sequence[float], k: int, min_sim: float) -> list[Neighbor]:
        return []
