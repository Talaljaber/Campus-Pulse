"""`train.py --retune` (P2.7/P2.10): stage-B OOF-score keys only, from the frozen oof.npz, no refit."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from campuspulse_ai.adapters.artifacts.io import FileArtifactStore
from campuspulse_ai.adapters.training.stages import RETUNE_KEYS, retune
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.composition.training import TrainOptions, make_pool
from campuspulse_ai.domain.errors import ArtifactVersionMismatch

TINY = Path(__file__).resolve().parents[1] / "fixtures" / "tiny_train.csv"


def test_retune_reuses_oof_and_changes_only_stage_b_keys(tiny_model_dir: Path, tmp_path: Path) -> None:
    model = tmp_path / "v1"
    shutil.copytree(tiny_model_dir, model)
    before = json.loads((model / "config.json").read_text(encoding="utf-8"))
    sha_m1 = FileArtifactStore().load_manifest(model).files["m1/category/model.joblib"]
    cfg = TrainCfg.load()
    pool, _ = make_pool(TrainOptions(data=(TINY,), encoder="hashing"), cfg)
    cfg15 = dataclasses.replace(cfg, alpha_priority=0.15)
    _, manifest, changed = retune(model, cfg15, pool)
    after = json.loads((model / "config.json").read_text(encoding="utf-8"))
    assert "conformal.alpha_priority" in changed and set(changed) <= set(RETUNE_KEYS)
    for section in before:
        if section not in ("conformal", "thresholds", "trained_at"):
            assert before[section] == after[section], section
    assert manifest.files["m1/category/model.joblib"] == sha_m1  # no model was refitted
    FileArtifactStore().load_manifest(model)  # every hash still verifies
    other, _ = make_pool(TrainOptions(data=(TINY,), encoder="hashing", toggles=dataclasses.replace(
        TrainOptions().toggles, strip_wrappers=False)), cfg)
    if other.model_text != pool.model_text:
        with pytest.raises(ArtifactVersionMismatch):
            retune(model, cfg, other)
