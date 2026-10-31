"""InMemoryMemoryStore: live-learning memory held in a dict (tests, offline red team).

Same contract as PgVectorMemoryStore (tests/contracts/test_memory_store_contract.py): cosine
neighbours over active examples, sim descending, ties broken by id.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

import numpy as np

from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.values import MemoryStats, Neighbor


class InMemoryMemoryStore:
    """MemoryStore over a dict of MemoryExample.

    - `add` stores a copy (a fresh UUID when `ex.id` is empty) and returns it.
    - `active(since)` lists active examples by (created_at, id).
    - `deactivate` raises NotFound for an unknown id.
    - `neighbors` returns active examples with cosine >= min_sim (source="memory").
    - `stats`: total/active counts, active count per category, newest created_at.

    `dim` (optional, P3.7): when given, `add` raises StoreError for an embedding of another width,
    like pgvector's `vector(384)` column does.
    """

    def __init__(self, dim: int | None = None) -> None:
        self._items: dict[str, MemoryExample] = {}
        self._dim = dim

    def add(self, ex: MemoryExample) -> MemoryExample:
        if self._dim is not None and len(ex.embedding) != self._dim:
            raise StoreError(f"memory embedding has {len(ex.embedding)} dimensions, expected {self._dim}")
        saved = dataclasses.replace(ex, id=ex.id or str(uuid.uuid4()), embedding=tuple(ex.embedding))
        self._items[saved.id] = saved
        return dataclasses.replace(saved)

    def active(self, since: datetime | None = None) -> list[MemoryExample]:
        rows = [ex for ex in self._items.values() if ex.active and (since is None or ex.created_at >= since)]
        return [dataclasses.replace(ex) for ex in sorted(rows, key=lambda ex: (ex.created_at, ex.id))]

    def deactivate(self, id: str) -> None:
        if id not in self._items:
            raise NotFound(f"memory example {id} not found")
        self._items[id] = dataclasses.replace(self._items[id], active=False)

    def stats(self) -> MemoryStats:
        active = [ex for ex in self._items.values() if ex.active]
        return MemoryStats(
            active=len(active),
            total=len(self._items),
            by_category=dict(Counter(str(ex.category) for ex in active)),
            last_added_at=max((ex.created_at for ex in self._items.values()), default=None),
        )

    def neighbors(self, embedding: Sequence[float], k: int, min_sim: float) -> list[Neighbor]:
        active = [ex for ex in self._items.values() if ex.active]
        if k <= 0 or not active:
            return []
        q = np.asarray(embedding, dtype=np.float64)
        matrix = np.asarray([ex.embedding for ex in active], dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1) * float(np.linalg.norm(q))
        with np.errstate(divide="ignore", invalid="ignore"):
            sims = np.where(norms > 0, (matrix @ q) / norms, 0.0)
        scored = sorted(
            ((float(s), ex) for s, ex in zip(sims, active, strict=True) if s >= min_sim),
            key=lambda t: (-t[0], t[1].id),
        )[:k]
        return [
            Neighbor(ex.text_norm, ex.category, ex.priority, sim, "memory", ex.created_at)
            for sim, ex in scored
        ]
