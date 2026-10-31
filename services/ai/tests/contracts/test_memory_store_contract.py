"""MemoryStore contract (P4.2 step 5): the same cases run against every live-learning store.

PgVectorMemoryStore runs when SUPABASE_TEST_URL / SUPABASE_TEST_SERVICE_ROLE_KEY are set.
InMemoryMemoryStore (Backend P3.7) joins automatically once it exists.
"""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pytest
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import NotFound
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import MemoryStore
from campuspulse_ai.domain.values import Lang

DIM = 384


def unit_vector(seed: int) -> tuple[float, ...]:
    rng = random.Random(seed)
    v = [rng.gauss(0.0, 1.0) for _ in range(DIM)]
    norm = math.sqrt(sum(x * x for x in v))
    return tuple(x / norm for x in v)


def example(
    seed: int, *, created_at: datetime | None = None, category: Category = Category.FACILITIES
) -> MemoryExample:
    return MemoryExample(
        id="",
        text_norm=f"memory contract {seed}",
        lang=Lang.EN,
        embedding=unit_vector(seed),
        category=category,
        priority=Priority.HIGH,
        author_id="",
        created_at=created_at or datetime.now(UTC),
    )


class Harness(Protocol):
    store: MemoryStore

    def track(self, ex: MemoryExample) -> MemoryExample: ...
    def cleanup(self) -> None: ...


class PgHarness:
    """Tracks every example it adds and deletes them all in cleanup()."""

    def __init__(self) -> None:
        from campuspulse_ai.adapters.memory.pgvector_memory import PgVectorMemoryStore
        from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

        self.client: Any = supabase_test_client()
        self.store = PgVectorMemoryStore(PgVectorStore(self.client, DIM), self.client)
        self._ids: list[str] = []

    def track(self, ex: MemoryExample) -> MemoryExample:
        self._ids.append(ex.id)
        return ex

    def cleanup(self) -> None:
        if self._ids:
            self.client.table("memory_examples").delete().in_("id", self._ids).execute()


class InMemoryHarness:
    def __init__(self) -> None:
        inmemory = pytest.importorskip(
            "campuspulse_ai.adapters.memory.inmemory", reason="InMemoryMemoryStore (P3.7)"
        )
        self.store = inmemory.InMemoryMemoryStore()

    def track(self, ex: MemoryExample) -> MemoryExample:
        return ex

    def cleanup(self) -> None:
        pass


@pytest.fixture(
    params=[pytest.param(PgHarness, marks=pytest.mark.supabase), pytest.param(InMemoryHarness)],
    ids=["pgvector", "inmemory"],
)
def harness(request: pytest.FixtureRequest) -> Iterator[Harness]:
    h: Harness = request.param()
    try:
        yield h
    finally:
        h.cleanup()


def test_store_satisfies_port(harness: Harness) -> None:
    assert isinstance(harness.store, MemoryStore)


def test_add_assigns_id_and_is_active(harness: Harness) -> None:
    saved = harness.track(harness.store.add(example(101)))
    assert saved.id
    active = {ex.id: ex for ex in harness.store.active()}
    assert saved.id in active
    got = active[saved.id]
    assert (got.text_norm, got.category, got.priority, got.lang) == (
        saved.text_norm,
        Category.FACILITIES,
        Priority.HIGH,
        Lang.EN,
    )
    assert got.embedding == pytest.approx(saved.embedding, abs=1e-6)


def test_neighbors_return_memory_labels(harness: Harness) -> None:
    saved = harness.track(harness.store.add(example(102)))
    hits = harness.store.neighbors(saved.embedding, k=1, min_sim=0.99)
    assert len(hits) == 1
    hit = hits[0]
    assert (hit.text, hit.category, hit.priority, hit.source) == (
        saved.text_norm,
        Category.FACILITIES,
        Priority.HIGH,
        "memory",
    )
    assert hit.sim == pytest.approx(1.0, abs=1e-4)


def test_deactivate_hides_from_neighbors_and_active(harness: Harness) -> None:
    saved = harness.track(harness.store.add(example(103)))
    harness.store.deactivate(saved.id)
    assert saved.id not in {ex.id for ex in harness.store.active()}
    assert harness.store.neighbors(saved.embedding, k=5, min_sim=0.99) == []


def test_deactivate_unknown_id_raises_not_found(harness: Harness) -> None:
    with pytest.raises(NotFound):
        harness.store.deactivate(str(uuid.uuid4()))


def test_active_since_excludes_older_examples(harness: Harness) -> None:
    now = datetime.now(UTC)
    old = harness.track(harness.store.add(example(104, created_at=now - timedelta(days=30))))
    new = harness.track(harness.store.add(example(105, created_at=now)))
    ids = {ex.id for ex in harness.store.active(since=now - timedelta(days=1))}
    assert new.id in ids
    assert old.id not in ids


def test_stats_count_adds_and_deactivations(harness: Harness) -> None:
    before = harness.store.stats()
    saved = harness.track(harness.store.add(example(106, category=Category.TRANSPORTATION)))
    mid = harness.store.stats()
    assert (mid.total, mid.active) == (before.total + 1, before.active + 1)
    assert mid.by_category.get("Transportation", 0) == before.by_category.get("Transportation", 0) + 1
    assert mid.last_added_at is not None
    harness.store.deactivate(saved.id)
    after = harness.store.stats()
    assert (after.total, after.active) == (before.total + 1, before.active)
