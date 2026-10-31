"""FrozenConfig: strict schema, trained thresholds, member weights (P1.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixtures.frozen_config import valid_config_dict  # services/ai/tests is the rootdir on sys.path

from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.domain.errors import ArtifactVersionMismatch


def _write(path: Path, data: dict[str, object]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_rejects_zero_thresholds(tmp_path: Path) -> None:
    for key in ("tau_ood", "tau_faq", "tau_inc", "tau_injection", "tau_safety", "human_review_maxprob"):
        data = valid_config_dict()
        data["thresholds"][key] = 0.0
        with pytest.raises(ArtifactVersionMismatch, match="thresholds not trained"):
            FrozenConfig.load(_write(tmp_path / f"{key}.json", data))


def test_roundtrip_identical(tmp_path: Path) -> None:
    original = FrozenConfig.load(_write(tmp_path / "in.json", valid_config_dict()))
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    original.save(first)
    reloaded = FrozenConfig.load(first)
    reloaded.save(second)
    assert reloaded == original
    assert first.read_bytes() == second.read_bytes()
    assert b"\r\n" not in first.read_bytes()
    assert list(json.loads(first.read_text(encoding="utf-8"))) == sorted(json.loads(first.read_text("utf-8")))


def test_unknown_member_in_weights_rejected(tmp_path: Path) -> None:
    data = valid_config_dict()
    data["ensemble"]["weights_category"] = {"m1": 0.5, "m2lr": 0.25, "m9": 0.25}
    with pytest.raises(ArtifactVersionMismatch, match="weights_category"):
        FrozenConfig.load(_write(tmp_path / "w.json", data))
    data = valid_config_dict()
    data["ensemble"]["members"] = ["m1", "m9"]
    with pytest.raises(ArtifactVersionMismatch):
        FrozenConfig.load(_write(tmp_path / "m.json", data))


def test_weights_sum_to_one(tmp_path: Path) -> None:
    config = FrozenConfig.load(_write(tmp_path / "ok.json", valid_config_dict()))
    assert sum(config.ensemble.weights_category.values()) == pytest.approx(1.0, abs=1e-6)
    assert sum(config.ensemble.weights_priority.values()) == pytest.approx(1.0, abs=1e-6)
    data = valid_config_dict()
    data["ensemble"]["weights_priority"] = dict.fromkeys(data["ensemble"]["members"], 0.5)
    with pytest.raises(ArtifactVersionMismatch, match="sum to 1"):
        FrozenConfig.load(_write(tmp_path / "bad.json", data))


def test_prototype_member_rules(tmp_path: Path) -> None:
    """m2proto (D-014) has no priority opinion and needs its `prototype` section."""
    data = valid_config_dict()
    data["ensemble"] = {"members": ["m1", "m2proto"], "weights_category": {"m1": 0.5, "m2proto": 0.5},
                        "weights_priority": {"m1": 0.5, "m2proto": 0.5}}
    data["prototype"] = {"parts": ["learned", "office"], "mix": 0.5, "temperature": 0.02}
    with pytest.raises(ArtifactVersionMismatch, match="no priority opinion"):
        FrozenConfig.load(_write(tmp_path / "pri.json", data))
    data["ensemble"]["weights_priority"] = {"m1": 1.0, "m2proto": 0.0}
    assert FrozenConfig.load(_write(tmp_path / "ok.json", data)).prototype is not None
    del data["prototype"]
    with pytest.raises(ArtifactVersionMismatch, match="prototype"):
        FrozenConfig.load(_write(tmp_path / "missing.json", data))
