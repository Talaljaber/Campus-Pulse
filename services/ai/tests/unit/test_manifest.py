"""FileArtifactStore: MANIFEST.json write/verify (P1.4, ARCHITECTURE §3.12)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from campuspulse_ai.adapters.artifacts.io import MANIFEST_NAME, FileArtifactStore, sha256_file
from campuspulse_ai.domain.errors import ArtifactChecksumMismatch, ArtifactMissing
from campuspulse_ai.domain.ports import ArtifactStore

FIXED = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


def _model_dir(tmp_path: Path) -> tuple[Path, list[Path]]:
    model_dir = tmp_path / "v1"
    (model_dir / "m1").mkdir(parents=True)
    (model_dir / "encoder").mkdir()
    (model_dir / "config.json").write_text(json.dumps({"artifact_version": "v1"}), encoding="utf-8")
    (model_dir / "m1" / "model.joblib").write_bytes(b"\x00weights\x01")
    (model_dir / "encoder" / "model_int8.onnx").write_bytes(b"onnx" * 1000)
    files = [Path("config.json"), Path("m1/model.joblib"), model_dir / "encoder" / "model_int8.onnx"]
    return model_dir, files


def test_write_then_load_ok(tmp_path: Path) -> None:
    model_dir, files = _model_dir(tmp_path)
    store = FileArtifactStore(now=lambda: FIXED)
    assert isinstance(store, ArtifactStore)
    written = store.write_manifest(model_dir, files)
    loaded = store.load_manifest(model_dir)
    assert loaded == written
    assert loaded.artifact_version == "v1"
    assert loaded.created_at == "2026-11-01T10:00:00+00:00"
    assert sorted(loaded.files) == ["config.json", "encoder/model_int8.onnx", "m1/model.joblib"]
    assert loaded.files["m1/model.joblib"] == sha256_file(model_dir / "m1" / "model.joblib")
    assert len(loaded.sha) == 64
    first = (model_dir / MANIFEST_NAME).read_bytes()
    store.write_manifest(model_dir, files)
    assert (model_dir / MANIFEST_NAME).read_bytes() == first  # byte-stable with a fixed clock


def test_tampered_file_raises_checksum_mismatch(tmp_path: Path) -> None:
    model_dir, files = _model_dir(tmp_path)
    store = FileArtifactStore(now=lambda: FIXED)
    store.write_manifest(model_dir, files)
    (model_dir / "m1" / "model.joblib").write_bytes(b"\x00weightz\x01")
    with pytest.raises(ArtifactChecksumMismatch, match="model.joblib"):
        store.load_manifest(model_dir)


def test_missing_file_raises_artifact_missing_with_fetch_hint(tmp_path: Path) -> None:
    model_dir, files = _model_dir(tmp_path)
    store = FileArtifactStore(now=lambda: FIXED)
    store.write_manifest(model_dir, files)
    (model_dir / "encoder" / "model_int8.onnx").unlink()
    with pytest.raises(ArtifactMissing, match=r"python scripts/fetch_models\.py"):
        store.load_manifest(model_dir)
