"""Live memory never reaches the offline path (P1.18, ARCHITECTURE §3.11; P3 adds part (c))."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fixtures.fakes import HashingEncoder

from campuspulse_ai.adapters.memory.null import NullMemoryStore
from campuspulse_ai.composition.offline import build_offline
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang


def test_offline_memory_is_null_and_add_raises(tiny_model_dir: Path) -> None:
    container = build_offline(tiny_model_dir, encoder_override=HashingEncoder())
    memory = container.core.memory
    assert isinstance(memory, NullMemoryStore)
    example = MemoryExample(id="m1", text_norm="the bus is late", lang=Lang.EN, embedding=(0.0,) * 384,
                            category=Category.TRANSPORTATION, priority=Priority.HIGH, author_id="staff",
                            created_at=datetime(2026, 11, 1, tzinfo=UTC))
    with pytest.raises(StoreError):
        memory.add(example)
    assert memory.neighbors((0.0,) * 384, 5, 0.0) == []
