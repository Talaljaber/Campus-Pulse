"""`config.paths`: root discovery and the holdout guard (P0.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from campuspulse_ai.config import paths


def test_repo_root_has_data_and_config() -> None:
    assert (paths.REPO_ROOT / "data").is_dir()
    assert (paths.REPO_ROOT / "config").is_dir()
    assert paths.DATA_CLEAN == paths.REPO_ROOT / "data" / "clean"


@pytest.mark.parametrize(
    "path",
    [
        Path("data/our_test/our_test.csv"),
        Path("data/robustness/probes.csv"),
        Path("DATA/Our_Test/x.csv"),
        Path("data/augmented/copy_of_our_test.csv"),
    ],
)
def test_holdout_paths_detected(path: Path) -> None:
    assert paths.is_holdout(path)


@pytest.mark.parametrize(
    "path",
    [Path("data/clean/train_val_combined.csv"), Path("data/augmented/arabizi.csv")],
)
def test_training_paths_not_holdout(path: Path) -> None:
    assert not paths.is_holdout(path)


def test_env_override_must_be_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.ROOT_ENV_VAR, str(tmp_path))
    with pytest.raises(RuntimeError):
        paths.find_repo_root()
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    assert paths.find_repo_root() == tmp_path.resolve()


def test_no_root_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(paths.ROOT_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError):
        paths.find_repo_root(start=tmp_path)
