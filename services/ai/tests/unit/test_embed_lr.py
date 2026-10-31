"""M2-LR `EmbedLR` with the deterministic `HashingEncoder` (P1.11)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fixtures.fakes import HashingEncoder

from campuspulse_ai.adapters.models.embed_lr import EmbedLR
from campuspulse_ai.domain.labels import PRIORITY_LABELS
from campuspulse_ai.domain.ports import ProbabilisticClassifier

TEXTS = [
    "where is the bus timetable", "how do i find my advisor office hours", "where can i print my transcript",
    "the projector is broken", "the wifi in the library keeps disconnecting", "my grade is wrong",
    "the last bus was cancelled and students are stranded", "water is leaking near the socket",
    "my exam portal crashed during the online exam today",
]
LABELS = ["low", "low", "low", "medium", "medium", "medium", "high", "high", "high"]


def test_fit_predict_with_hashing_encoder() -> None:
    enc = HashingEncoder()
    m = EmbedLR("priority", enc, C=8.0, seed=42)
    m.fit(TEXTS, LABELS)
    assert isinstance(m, ProbabilisticClassifier)
    probs = m.predict_proba(["where is the timetable for the bus", "the projector in room 2 is broken"])
    assert [p.labels for p in probs] == [PRIORITY_LABELS, PRIORITY_LABELS]
    assert probs[0].argmax() == "low" and probs[1].argmax() == "medium"
    emb = np.asarray(enc.encode(["the projector in room 2 is broken"]), dtype=np.float32)
    assert m.predict_proba_from_embeddings(emb)[0].values == probs[1].values


def test_save_load(tmp_path: Path) -> None:
    enc = HashingEncoder()
    m = EmbedLR("priority", enc, C=8.0, seed=42)
    m.fit(TEXTS, LABELS, sample_weight=[1.0] * len(TEXTS))
    m.save(tmp_path / "m2lr")
    loaded = EmbedLR.load(tmp_path / "m2lr", encoder=enc)
    q = ["students stranded at the bus stop", "where do i pay fees"]
    assert [p.values for p in loaded.predict_proba(q)] == [p.values for p in m.predict_proba(q)]
    assert loaded.dim == enc.dim
