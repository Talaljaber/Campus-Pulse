"""P3.7: `InMemoryMemoryStore` with the memory-aware kNN merge (the store a correction writes to).

The merge itself lives in `KnnClassifier.predict_from_embedding` (ML, P1.11); these tests drive it
through a real store: a memory item shifts the vote but never beyond `memory_weight_cap`, a
deactivated item has no effect, OOD ignores memory, and the store refuses a wrong-width vector.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fixtures.fakes import HashingEncoder

from campuspulse_ai.adapters.memory.inmemory import InMemoryMemoryStore
from campuspulse_ai.adapters.models.knn import ExampleIndex, IndexEntry, KnnClassifier
from campuspulse_ai.adapters.models.ood import ood_score
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang

ROWS = [
    ("the projector is broken", "Facilities", "medium"),
    ("the projector in the hall does not work", "Facilities", "medium"),
    ("where is the bus timetable", "Transportation", "low"),
    ("the bus is late", "Transportation", "medium"),
    ("i was charged twice", "Finance", "medium"),
]
K, CAP, MAX_MEMORY, MIN_SIM, LAPLACE = 3, 0.6, 2, 0.8, 1.0
QUERY = "the bus is late"
WHEN = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def enc() -> HashingEncoder:
    return HashingEncoder()


def knn(enc: HashingEncoder) -> KnnClassifier:
    index = ExampleIndex(LocalNumpyVectorStore(enc.dim))
    embs = enc.encode([t for t, _, _ in ROWS])
    index.add([IndexEntry(f"r{i}", t, tuple(e), c, p, Lang.EN, "official", f"S{i}", f"G{i}")
               for i, ((t, c, p), e) in enumerate(zip(ROWS, embs, strict=True))])  # fmt: skip
    return KnnClassifier("priority", index, enc, K, CAP, MAX_MEMORY, memory_min_sim=MIN_SIM,
                         laplace_mass=LAPLACE)  # fmt: skip


def example(enc: HashingEncoder, text: str, priority: Priority, id: str = "") -> MemoryExample:
    return MemoryExample(id=id, text_norm=text, lang=Lang.EN, embedding=tuple(enc.encode([text])[0]),
                         category=Category.TRANSPORTATION, priority=priority, author_id="staff-1",
                         created_at=WHEN)  # fmt: skip


def test_a_close_memory_item_shifts_the_vote_but_never_past_the_cap(enc: HashingEncoder) -> None:
    model, memory = knn(enc), InMemoryMemoryStore(enc.dim)
    emb = enc.encode([QUERY])[0]
    before, _ = model.predict_from_embedding(emb, memory)
    memory.add(example(enc, QUERY, Priority.HIGH))
    after, neighbors = model.predict_from_embedding(emb, memory)
    assert after.prob("high") > before.prob("high")
    assert [n.source for n in neighbors].count("memory") == 1
    train_mass = sum(max(n.sim, 0.0) for n in neighbors if n.source != "memory")
    # memory holds at most CAP of the raw vote; the Laplace mass only dilutes it further
    assert after.prob("high") <= CAP * (train_mass / (1 - CAP)) / (train_mass / (1 - CAP) + LAPLACE) + 1e-9


def test_a_deactivated_item_has_no_effect(enc: HashingEncoder) -> None:
    model, memory = knn(enc), InMemoryMemoryStore(enc.dim)
    emb = enc.encode([QUERY])[0]
    before, _ = model.predict_from_embedding(emb, memory)
    saved = memory.add(example(enc, QUERY, Priority.HIGH))
    memory.deactivate(saved.id)
    after, neighbors = model.predict_from_embedding(emb, memory)
    assert after.values == before.values and all(n.source != "memory" for n in neighbors)
    with pytest.raises(NotFound):
        memory.deactivate("missing")


def test_items_below_memory_min_sim_do_not_vote(enc: HashingEncoder) -> None:
    model, memory = knn(enc), InMemoryMemoryStore(enc.dim)
    memory.add(example(enc, "i was charged twice for parking", Priority.HIGH))
    _, neighbors = model.predict_from_embedding(enc.encode([QUERY])[0], memory)
    assert all(n.source != "memory" for n in neighbors)


def test_ood_is_unchanged_by_memory(enc: HashingEncoder) -> None:
    model, memory = knn(enc), InMemoryMemoryStore(enc.dim)
    emb = enc.encode(["completely unrelated words about cooking pasta"])[0]
    before = ood_score(model.index, emb)
    memory.add(example(enc, "completely unrelated words about cooking pasta", Priority.HIGH))
    assert ood_score(model.index, emb) == before


def test_a_wrong_width_embedding_is_refused(enc: HashingEncoder) -> None:
    memory = InMemoryMemoryStore(enc.dim)
    bad = MemoryExample(id="", text_norm="x", lang=Lang.EN, embedding=(1.0, 0.0), category=Category.FINANCE,
                        priority=Priority.LOW, author_id="", created_at=WHEN)  # fmt: skip
    with pytest.raises(StoreError):
        memory.add(bad)
    assert memory.stats().total == 0


def test_stats_and_attribution(enc: HashingEncoder) -> None:
    memory = InMemoryMemoryStore(enc.dim)
    saved = memory.add(example(enc, QUERY, Priority.HIGH))
    stats = memory.stats()
    assert (stats.active, stats.total, stats.last_added_at) == (1, 1, WHEN)
    [row] = memory.active()
    assert row.id == saved.id and row.author_id == "staff-1" and row.created_at == WHEN
