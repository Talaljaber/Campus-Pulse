"""Edge cases for FrozenConfig and FileArtifactStore beyond the P1.4 acceptance suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fixtures.frozen_config import valid_config_dict  # services/ai/tests is the rootdir on sys.path

from campuspulse_ai.adapters.artifacts.io import MANIFEST_NAME, FileArtifactStore
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch


def _load(tmp_path: Path, data: object) -> FrozenConfig:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return FrozenConfig.load(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["priority_head"]["features"].append("stated_urgency"),  # §3.8 invariant
        lambda d: d.update(unexpected_key=1),  # extra="forbid"
        lambda d: d["guards"].pop("max_tokens"),  # missing key
        lambda d: d["priors"]["category"].pop("Finance"),  # priors must cover every label
        lambda d: d["thresholds"].update(human_review_maxprob=1.5),
        lambda d: d["m1"].update(char_ngram=[5, 2]),
        lambda d: d["conformal"].update(alpha_category=0.0),
        lambda d: d["ensemble"].update(members=["m1", "m1", "m2lr"]),
    ],
)
def test_invalid_configs_raise_version_mismatch(tmp_path: Path, mutate: object) -> None:
    data = valid_config_dict()
    mutate(data)  # type: ignore[operator]
    with pytest.raises(ArtifactVersionMismatch):
        _load(tmp_path, data)


def test_schema_version_and_io_errors(tmp_path: Path) -> None:
    data = valid_config_dict()
    data["schema_version"] = 2
    with pytest.raises(ArtifactVersionMismatch, match="schema_version"):
        _load(tmp_path, data)
    with pytest.raises(ArtifactMissing, match="fetch_models"):
        FrozenConfig.load(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactVersionMismatch):
        FrozenConfig.load(bad)


def test_config_is_frozen(tmp_path: Path) -> None:
    config = _load(tmp_path, valid_config_dict())
    with pytest.raises(ValueError):
        config.seed = 1  # type: ignore[misc]


def test_train_yaml_has_every_p1_4_key() -> None:
    train = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
    assert train["seed"] == 42 and train["cv"]["k"] == 5
    assert set(train["alpha"]) == {"category", "priority"}
    assert set(train["grids"]) == {"m1_C", "m2lr_C", "weight_step"}
    for key in ("tau_ood_percentile", "tau_margin", "human_review_min_acc", "ask_rate_max",
                "alpha_priority_fallback"):
        assert key in train
    assert set(train["mondrian"]) == {"min_cov_minority", "min_cov_en"}
    m3_keys = {"min_gain", "max_predict_s_per_1000", "time_box_h", "max_download_mb", "max_rss_mb"}
    assert set(train["m3"]) == m3_keys
    assert train["encoder"]["query_prefix"] == "query: "
    hand = yaml.safe_load((CONFIG_DIR / "hand_tuned.yaml").read_text(encoding="utf-8"))
    assert set(hand) == {"tau_faq", "tau_inc"}


def test_manifest_rejects_bad_inputs(tmp_path: Path) -> None:
    store = FileArtifactStore()
    model_dir = tmp_path / "v1"
    model_dir.mkdir()
    (model_dir / "a.bin").write_bytes(b"a")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError):
        store.write_manifest(model_dir, [outside])
    with pytest.raises(ArtifactMissing):
        store.write_manifest(model_dir, [Path("missing.bin")])
    with pytest.raises(ArtifactMissing, match="fetch_models"):
        store.load_manifest(model_dir)  # no manifest yet
    manifest = store.write_manifest(model_dir, [Path("a.bin")])
    assert manifest.artifact_version == "v1"  # no config.json: the directory name
    with pytest.raises(ValueError):
        store.write_manifest(model_dir, [Path(MANIFEST_NAME)])
    (model_dir / MANIFEST_NAME).write_text(json.dumps({"artifact_version": "v1"}), encoding="utf-8")
    with pytest.raises(ArtifactVersionMismatch):
        store.load_manifest(model_dir)
    unsafe = {"artifact_version": "v1", "created_at": "x", "files": {"../outside.bin": "0" * 64}}
    (model_dir / MANIFEST_NAME).write_text(json.dumps(unsafe), encoding="utf-8")
    with pytest.raises(ArtifactVersionMismatch, match="unsafe"):
        store.load_manifest(model_dir)


def test_manifest_version_must_match_config(tmp_path: Path) -> None:
    model_dir = tmp_path / "v1"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"artifact_version": "v1"}), encoding="utf-8")
    store = FileArtifactStore()
    store.write_manifest(model_dir, [Path("config.json")])
    data = json.loads((model_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    data["artifact_version"] = "v2"
    (model_dir / MANIFEST_NAME).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtifactVersionMismatch, match="artifact_version"):
        store.load_manifest(model_dir)
