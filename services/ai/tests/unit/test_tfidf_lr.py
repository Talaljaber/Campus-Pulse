"""M1 `TfidfLR` (P1.10)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from campuspulse_ai.adapters.models.tfidf_lr import TfidfLR
from campuspulse_ai.domain.labels import CATEGORY_LABELS
from campuspulse_ai.domain.ports import ProbabilisticClassifier

TEXTS = [
    "the projector in the lecture room is broken",
    "the classroom projector does not turn on",
    "i cannot log in to the university email",
    "my portal password expired and i am locked out",
    "the bus to campus was late again",
    "when does the last bus leave campus",
    "i was charged twice for tuition",
    "how do i pay the tuition fee in installments",
    "البروجكتور بالقاعة خربان",
    "الباص اتأخر اليوم",
]
LABELS = ["Facilities", "Facilities", "IT Support", "IT Support", "Transportation", "Transportation",
          "Finance", "Finance", "Facilities", "Transportation"]


def _model() -> TfidfLR:
    return TfidfLR("category", (2, 5), (1, 2), C=4.0, seed=42)


def test_proba_shape_and_sum() -> None:
    m = _model()
    m.fit(TEXTS, LABELS)
    probs = m.predict_proba(["the projector is broken", "bus late"])
    assert isinstance(m, ProbabilisticClassifier)
    assert len(probs) == 2
    for p in probs:
        assert p.labels == CATEGORY_LABELS
        assert math.isclose(sum(p.values), 1.0, abs_tol=1e-9)
    assert probs[0].argmax() == "Facilities"
    assert probs[1].argmax() == "Transportation"
    # classes absent from training get probability 0
    assert probs[0].prob("Registration") == 0.0


def test_save_load_identical_probs(tmp_path: Path) -> None:
    m = _model()
    m.fit(TEXTS, LABELS)
    m.save(tmp_path / "m1")
    loaded = TfidfLR.load(tmp_path / "m1")
    queries = ["my email is locked", "الباص تأخر"]
    assert [p.values for p in loaded.predict_proba(queries)] == [p.values for p in m.predict_proba(queries)]
    assert loaded.target == "category" and loaded.C == 4.0


def test_token_contributions_top_token() -> None:
    m = _model()
    m.fit(TEXTS, LABELS)
    contributions = m.token_contributions("Help, the projector stopped")
    assert contributions[0][0] == "projector"
    assert contributions == sorted(contributions, key=lambda kv: -kv[1])
    assert m.token_contributions("   ") == []


def test_sample_weight_equals_duplication() -> None:
    weighted, duplicated = _model(), _model()
    weighted.fit(TEXTS, LABELS, sample_weight=[2.0] + [1.0] * (len(TEXTS) - 1))
    duplicated.fit([TEXTS[0], *TEXTS], [LABELS[0], *LABELS])
    q = ["the lecture room projector", "i paid twice"]
    for a, b in zip(weighted.predict_proba(q), duplicated.predict_proba(q), strict=True):
        assert a.values == pytest.approx(b.values, abs=1e-5)
