"""Shared pytest fixtures (ARCHITECTURE §1.5, LD-22).

`tiny_model_dir` (session): a complete frozen model directory built by the real `train.py` pipeline
(`--encoder hashing`) on `tests/fixtures/tiny_train.csv` (60 official rows, 2 per cv_group). Load it with
`build_offline(tiny_model_dir, encoder_override=HashingEncoder())`. No ONNX, no network; about 10 s.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from campuspulse_ai.composition.training import TrainOptions, run_training

TINY_TRAIN = Path(__file__).resolve().parent / "fixtures" / "tiny_train.csv"


def build_tiny_model_dir(root: Path) -> Path:
    """Train the tiny model into `root/v1` (report in `root/cv_tiny.json`) and return the model dir."""
    out = root / "v1"
    run_training(TrainOptions(out=out, report=root / "cv_tiny.json", encoder="hashing", data=(TINY_TRAIN,)))
    return out


@pytest.fixture(scope="session")
def tiny_model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_tiny_model_dir(tmp_path_factory.mktemp("tiny_models"))
