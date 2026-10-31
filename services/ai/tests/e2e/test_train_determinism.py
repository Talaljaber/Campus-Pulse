"""`train.py` determinism and the `tiny_model_dir` fixture (P1.16)."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import TINY_TRAIN
from fixtures.fakes import HashingEncoder

from campuspulse_ai.composition.offline import BatchRow, build_offline
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.frameworks.cli.train import main as train_main


def _cv_only(tmp: Path, name: str) -> dict[str, object]:
    report = tmp / f"{name}.json"
    argv = [
        "--cv-only",
        "--fast",
        "--encoder",
        "hashing",
        "--data",
        str(TINY_TRAIN),
        "--report",
        str(report),
        "--out",
        str(tmp / name),
    ]
    assert train_main(argv) == 0
    data: dict[str, object] = json.loads(report.read_text(encoding="utf-8"))
    return data


def test_cv_only_is_deterministic(tmp_path: Path) -> None:
    first, second = _cv_only(tmp_path, "a"), _cv_only(tmp_path, "b")
    assert first == second  # the report has no timestamps
    assert not (tmp_path / "a").exists()  # --cv-only freezes nothing
    counts = first["counts"]
    assert isinstance(counts, dict) and counts["official"] == {"rows": 60, "groups": 30, "distinct_texts": 33}


def test_tiny_model_dir_builds_offline_container(tiny_model_dir: Path) -> None:
    config = FrozenConfig.load(tiny_model_dir / "config.json")
    assert config.encoder.runtime == "hashing" and config.artifact_version == "v1"
    assert (tiny_model_dir.parent / "CURRENT").read_text(encoding="utf-8").strip() == "v1"
    container = build_offline(tiny_model_dir.parent, encoder_override=HashingEncoder())
    assert container.vectors.collections() == {"train", "injection_exemplars", "safety_exemplars"}
    out = container.batch.run(
        [BatchRow("A", "The bus is late"), BatchRow("B", "my exam portal crashed today")]
    )
    assert [p.request_id for p in out] == ["A", "B"]
    assert all(p.category in CATEGORY_LABELS and p.priority in PRIORITY_LABELS for p in out)
    assert container.manifest.sha == container.core.artifact.sha256
