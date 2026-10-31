"""NullMemoryStore (§3.11): always empty; writing to it is an error."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from campuspulse_ai.adapters.memory.null import NullMemoryStore
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import MemoryStore
from campuspulse_ai.domain.values import Lang


def test_null_memory_is_empty_and_read_only() -> None:
    store = NullMemoryStore()
    assert isinstance(store, MemoryStore)
    ex = MemoryExample("", "t", Lang.EN, (1.0, 0.0), Category.FINANCE, Priority.LOW, "", datetime.now(UTC))
    with pytest.raises(StoreError):
        store.add(ex)
    with pytest.raises(NotFound):
        store.deactivate("any")
    assert store.active() == [] and store.neighbors((1.0, 0.0), k=5, min_sim=0.0) == []
    stats = store.stats()
    assert (stats.total, stats.active, dict(stats.by_category), stats.last_added_at) == (0, 0, {}, None)
