"""`WeightedEnsemble` over M1, M2-LR and M2-kNN with the `HashingEncoder` (P1.13)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fixtures.fakes import HashingEncoder

from campuspulse_ai.adapters.models.embed_lr import EmbedLR
from campuspulse_ai.adapters.models.ensemble import WeightedEnsemble
from campuspulse_ai.adapters.models.knn import ExampleIndex, IndexEntry, KnnClassifier
from campuspulse_ai.adapters.models.tfidf_lr import TfidfLR
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.errors import ArtifactVersionMismatch
from campuspulse_ai.domain.ports import Ensemble, ProbabilisticClassifier
from campuspulse_ai.domain.values import Lang

ROWS = [
    ("the projector is broken", "Facilities", "medium"),
    ("where is the lost and found office", "Facilities", "low"),
    ("where is the bus timetable", "Transportation", "low"),
    ("the last bus was cancelled and we are stranded", "Transportation", "high"),
    ("i was charged twice for tuition", "Finance", "medium"),
    ("how do i pay in installments", "Finance", "low"),
    ("my email password expired", "IT Support", "medium"),
    ("the exam portal crashed during my online exam", "IT Support", "high"),
]


def _members(enc: HashingEncoder) -> tuple[dict[str, tuple[ProbabilisticClassifier, ProbabilisticClassifier]],
                                           ExampleIndex]:
    texts = [t for t, _, _ in ROWS]
    cats, pris = [c for _, c, _ in ROWS], [p for _, _, p in ROWS]
    m1 = (TfidfLR("category", (2, 5), (1, 2), 4.0, 42), TfidfLR("priority", (2, 5), (1, 2), 4.0, 42))
    m2 = (EmbedLR("category", enc, 4.0, 42), EmbedLR("priority", enc, 4.0, 42))
    for (a, b) in (m1, m2):
        a.fit(texts, cats)
        b.fit(texts, pris)
    index = ExampleIndex(LocalNumpyVectorStore(enc.dim))
    index.add([IndexEntry(f"r{i}", t, tuple(e), c, p, Lang.EN, "official", f"S{i}", f"G{i}")
               for i, ((t, c, p), e) in enumerate(zip(ROWS, enc.encode(texts), strict=True))])
    knn = (KnnClassifier("category", index, enc, 3, 0.6, 2, memory_min_sim=0.8, laplace_mass=1.0),
           KnnClassifier("priority", index, enc, 3, 0.6, 2, memory_min_sim=0.8, laplace_mass=1.0))
    return {"m1": m1, "m2lr": m2, "m2knn": (knn[0], knn[1])}, index


def _even(names: list[str]) -> dict[str, float]:
    return {n: 1.0 / len(names) for n in names}


def test_weights_sum_to_one() -> None:
    enc = HashingEncoder()
    members, index = _members(enc)
    ens = WeightedEnsemble(members, enc, index, _even(list(members)), _even(list(members)))
    assert isinstance(ens, Ensemble)
    out = ens.predict(["the projector does not work", "stranded after the bus was cancelled"], None)
    for o in out:
        assert math.isclose(sum(o.p_cat.values), 1.0, abs_tol=1e-9)
        assert math.isclose(sum(o.p_pri_model.values), 1.0, abs_tol=1e-9)
        expected = np.mean([o.per_model[f"{m}.category"].values for m in members], axis=0)
        assert np.allclose(o.p_cat.values, expected)
    with pytest.raises(ArtifactVersionMismatch):
        WeightedEnsemble(members, enc, index, {"m1": 0.5, "m2lr": 0.2, "m2knn": 0.2}, _even(list(members)))


def test_removing_member_from_config_still_predicts() -> None:
    enc = HashingEncoder()
    members, index = _members(enc)
    del members["m2knn"]
    ens = WeightedEnsemble(members, enc, index, _even(list(members)), _even(list(members)))
    out = ens.predict(["the projector is broken"], None)[0]
    assert ens.members == ("m1", "m2lr")
    assert out.p_cat.argmax() == "Facilities"
    assert out.neighbors == ()  # no kNN member, no neighbours
    assert 0.0 < out.ood_score <= 1.0 + 1e-6
    with pytest.raises(ArtifactVersionMismatch):
        WeightedEnsemble(members, enc, index, _even(["m1", "m2lr", "m2knn"]), _even(list(members)))


def test_per_model_keys() -> None:
    enc = HashingEncoder()
    members, index = _members(enc)
    ens = WeightedEnsemble(members, enc, index, _even(list(members)), _even(list(members)))
    out = ens.predict(["where is the bus timetable"], None)[0]
    assert set(out.per_model) == {f"{m}.{t}" for m in members for t in ("category", "priority")}
    assert len(out.embedding) == enc.dim
    assert out.neighbors and out.neighbors[0].text == "where is the bus timetable"
    assert out.ood_score == pytest.approx(1.0, abs=1e-6)
