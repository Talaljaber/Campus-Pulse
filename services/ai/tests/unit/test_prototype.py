"""The department-prototype member m2proto (D-014)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from campuspulse_ai.adapters.models.hashing_encoder import HashingEncoder
from campuspulse_ai.adapters.models.prototype import (
    PrototypeClassifier,
    PrototypeSet,
    category_scores,
    learned_prototypes,
    office_lines,
    office_prototypes,
    softmax,
)
from campuspulse_ai.adapters.preprocess.wrappers import normalize_text, script_lang
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS

OFFICE_YAML = CONFIG_DIR / "office_descriptions.yaml"


def _unit(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def test_learned_prototypes_average_scenarios_not_rows() -> None:
    emb = _unit(np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.6, 0.8]]))
    cats = ["Finance", "Finance", "Finance", "Finance", "Registration"]
    scen = ["S1", "S1", "S1", "S2", "S3"]  # S1 has three wrapper variants, S2 one
    protos = learned_prototypes(emb.astype(np.float32), cats, scen)
    assert protos.labels == ("Registration", "Finance") or set(protos.labels) == {"Finance", "Registration"}
    fin = protos.vectors[list(protos.labels).index("Finance")]
    assert np.allclose(fin, _unit(np.array([[1.0, 1.0]]))[0], atol=1e-6)  # S1 and S2 weigh the same


def test_scores_mix_parts_and_softmax_keeps_argmax() -> None:
    learned = PrototypeSet(np.eye(6, 4, dtype=np.float32)[:2], ("Finance", "Registration"), ("learned",) * 2)
    office = PrototypeSet(np.eye(6, 4, dtype=np.float32)[1:3], ("Registration", "Finance"), ("office",) * 2)
    both = PrototypeSet.concat([learned, office], 4)
    x = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    s = category_scores(x, both, mix=0.5)
    fin, reg = CATEGORY_LABELS.index("Finance"), CATEGORY_LABELS.index("Registration")
    assert s[0, fin] == pytest.approx(0.5 * 1.0 + 0.5 * 0.0) and s[0, reg] == pytest.approx(0.0)
    p = softmax(s, 0.01)
    assert np.argmax(p) == fin and p.sum() == pytest.approx(1.0)
    assert np.argmax(category_scores(x, both.only(["learned"]), 0.5)) == fin


def test_office_descriptions_cover_every_category_and_copy_no_dataset_text() -> None:
    lines = office_lines(OFFICE_YAML)
    assert {c for c, _ in lines} == set(CATEGORY_LABELS)
    official = pd.read_csv(DATA_CLEAN / "train_val_combined.csv", dtype=str, keep_default_na=False)
    norms = set(official.text_norm)
    copied = [t for _, t in lines if normalize_text(t, script_lang(t)) in norms]
    assert copied == []


def test_save_load_roundtrip_and_uniform_priority(tmp_path: Path) -> None:
    enc = HashingEncoder(dim=64, seed=42)
    protos = office_prototypes(enc, OFFICE_YAML)
    cat = PrototypeClassifier("category", protos, 0.02, 0.5, enc)
    pri = PrototypeClassifier("priority", None, 0.02, 0.5, enc)
    cat.save(tmp_path / "category")
    pri.save(tmp_path / "priority")
    again = PrototypeClassifier.load(tmp_path / "category", enc)
    texts = ["the projector in the lecture hall is broken", "وين بدفع الرسوم"]
    a = [v.values for v in cat.predict_proba(texts)]
    b = [v.values for v in again.predict_proba(texts)]
    assert np.allclose(a, b)
    uniform = PrototypeClassifier.load(tmp_path / "priority", enc).predict_proba(texts)
    assert all(v.values == tuple(1.0 / len(PRIORITY_LABELS) for _ in PRIORITY_LABELS) for v in uniform)
    with pytest.raises(ValueError):
        cat.fit(texts, ["Finance", "Finance"])
