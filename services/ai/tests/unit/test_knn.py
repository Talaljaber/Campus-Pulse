"""M2-kNN `ExampleIndex`, `KnnClassifier` and the OOD score (P1.11)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import numpy as np
from fixtures.fakes import HashingEncoder

from campuspulse_ai.adapters.models.knn import ExampleIndex, IndexEntry, KnnClassifier
from campuspulse_ai.adapters.models.ood import ood_score
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang, MemoryStats, Neighbor

ROWS = [
    ("the projector is broken", "Facilities", "medium"),
    ("the projector in the hall does not work", "Facilities", "medium"),
    ("where is the bus timetable", "Transportation", "low"),
    ("the bus is late", "Transportation", "medium"),
    ("i was charged twice", "Finance", "medium"),
    ("my email password expired", "IT Support", "medium"),
]
KNN = {"k": 3, "memory_weight_cap": 0.6, "max_memory_neighbors": 2, "memory_min_sim": 0.0,
       "laplace_mass": 1.0}


def _index(enc: HashingEncoder) -> ExampleIndex:
    index = ExampleIndex(LocalNumpyVectorStore(enc.dim))
    embs = enc.encode([t for t, _, _ in ROWS])
    index.add([
        IndexEntry(f"r{i}", t, tuple(e), c, p, Lang.EN, "official", f"S{i}", f"G{i}")
        for i, ((t, c, p), e) in enumerate(zip(ROWS, embs, strict=True))
    ])
    return index


def _knn(target: str, index: ExampleIndex, enc: HashingEncoder) -> KnnClassifier:
    return KnnClassifier(target, index, enc, KNN["k"], KNN["memory_weight_cap"],  # type: ignore[arg-type]
                         KNN["max_memory_neighbors"], memory_min_sim=KNN["memory_min_sim"],
                         laplace_mass=KNN["laplace_mass"])


class _Memory:
    """A MemoryStore that always returns the given neighbours (only `neighbors` is used here)."""

    def __init__(self, neighbors: Sequence[Neighbor]) -> None:
        self._n = list(neighbors)

    def add(self, ex: MemoryExample) -> MemoryExample:
        raise NotImplementedError

    def active(self, since: datetime | None = None) -> list[MemoryExample]:
        return []

    def deactivate(self, id: str) -> None:
        raise NotImplementedError

    def stats(self) -> MemoryStats:
        return MemoryStats(0, 0, {})

    def neighbors(self, embedding: Sequence[float], k: int, min_sim: float) -> list[Neighbor]:
        return self._n[:k]


def test_neighbors_sorted_desc() -> None:
    enc = HashingEncoder()
    index = _index(enc)
    hits = index.query(enc.encode(["the projector is broken again"])[0], k=4)
    sims = [n.sim for n in hits]
    assert sims == sorted(sims, reverse=True)
    assert hits[0].text == "the projector is broken"
    assert hits[0].category is Category.FACILITIES and hits[0].source == "train"


def test_laplace_no_zero_probs() -> None:
    enc = HashingEncoder()
    knn = _knn("category", _index(enc), enc)
    p, neighbors = knn.predict_from_embedding(enc.encode(["the projector is broken"])[0], None)
    assert all(v > 0 for v in p.values)
    assert p.argmax() == "Facilities"
    assert abs(sum(p.values) - 1.0) < 1e-9
    assert len(neighbors) == KNN["k"]


def test_memory_none_uses_train_only() -> None:
    enc = HashingEncoder()
    knn = _knn("priority", _index(enc), enc)
    emb = enc.encode(["the bus is late"])[0]
    p_none, n_none = knn.predict_from_embedding(emb, None)
    assert all(n.source == "train" for n in n_none)
    flip = [Neighbor("the bus is late", Category.TRANSPORTATION, Priority.HIGH, 1.0, "memory")] * 2
    p_mem, n_mem = knn.predict_from_embedding(emb, _Memory(flip))
    assert sum(n.source == "memory" for n in n_mem) == KNN["max_memory_neighbors"]
    assert p_mem.prob("high") > p_none.prob("high")
    # memory's share of the vote is capped: train votes still hold at least 1 - cap of the mass
    train_mass = sum(max(n.sim, 0.0) for n in n_none)
    assert p_mem.prob("high") < KNN["memory_weight_cap"] + (1.0 / 3) / (train_mass + 1.0)
    assert knn.predict_proba(["the bus is late"])[0].values == p_none.values


def test_ood_equals_max_sim() -> None:
    enc = HashingEncoder()
    index = _index(enc)
    emb = enc.encode(["my email password expired yesterday"])[0]
    sims = [float(np.dot(emb, e)) for e in enc.encode([t for t, _, _ in ROWS])]
    assert abs(ood_score(index, emb) - max(sims)) < 1e-6
    assert abs(ood_score(index, enc.encode([ROWS[0][0]])[0]) - 1.0) < 1e-6
