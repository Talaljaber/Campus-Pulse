"""P7.1 measurement tools: scripts/scratch_model.py and scripts/dev_eval.py (6-row fixture)."""
# ruff: noqa: E501

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from campuspulse_ai.adapters.artifacts.io import FileArtifactStore
from campuspulse_ai.config.paths import REPO_ROOT


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


DEV_HEADER = ["dev_id", "split", "lang", "block", "probe_type", "family", "category", "priority", "scenario_id"]
DEV = [
    ["D1", "tune", "en", "headline", "", "", "Finance", "low", "D1"],
    ["D2", "tune", "en", "implicit_urgency", "", "power", "Facilities", "high", "D2"],
    ["D3", "tune", "en", "probe", "distress", "", "", "", "D3"],
    ["D4", "tune", "ar", "headline", "", "", "IT Support", "medium", "D4"],
    ["D5", "check", "ar", "implicit_urgency", "", "bus", "Transportation", "high", "D5"],
    ["D6", "check", "ar", "probe", "injection", "", "Finance", "low", "D6"],
]
PRED_HEADER = ["request_id", "category", "priority", "set_cat", "set_pri", "flags"]
PRED_TUNE_EN = [
    ["D1", "Finance", "low", "1", "1", ""],
    ["D2", "Facilities", "medium", "1", "2", "needs_review"],
    ["D3", "Academic Support", "low", "0", "1", "empty_set;empty_set_cat;distress"],
]
PRED_TUNE_AR = [["D4", "IT Support", "medium", "1", "1", ""]]
PRED_CHECK_AR = [
    ["D5", "Transportation", "high", "1", "1", "safety"],
    ["D6", "Finance", "low", "1", "1", "injection_attempt"],
]


@pytest.fixture
def pred_dir(tmp_path: Path) -> Path:
    d = tmp_path / "pred"
    d.mkdir()
    _write(d / "tune_en.csv", PRED_HEADER, PRED_TUNE_EN)
    _write(d / "tune_ar.csv", PRED_HEADER, PRED_TUNE_AR)
    _write(d / "check_ar.csv", PRED_HEADER, PRED_CHECK_AR)
    return d


def test_dev_eval_scores_the_fixture(tmp_path: Path, pred_dir: Path) -> None:
    ev = _load("dev_eval")
    dev_csv = tmp_path / "dev.csv"
    _write(dev_csv, DEV_HEADER, DEV)
    out = tmp_path / "score.json"
    assert ev.main(["score", "--pred", str(pred_dir), "--dev", str(dev_csv), "--out", str(out)]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["n_rows"] == 6 and set(res["languages"]) == {"en", "ar", "pooled"}
    pooled = res["languages"]["pooled"]
    assert pooled["routing"]["buckets"] == {"0": 1, "1": 4, "2": 1, "3": 0}
    assert pooled["routing"]["auto_graded"] == 4 and pooled["routing"]["auto_joint_accuracy"] == 1.0
    assert pooled["high_recall_by_family"] == {"bus": {"n": 1, "recall": 1.0}, "power": {"n": 1, "recall": 0.0}}
    assert pooled["flags"]["probes"]["distress"]["distress"] == 1.0
    assert pooled["flags"]["probes"]["injection"]["injection_attempt"] == 1.0
    assert pooled["flags"]["non_probe_false_hits"]["safety"] == pytest.approx(1 / 4)
    assert pooled["quality"]["headline"]["category_accuracy"] == 1.0
    assert out.with_suffix(".md").read_text(encoding="utf-8").startswith("# dev_fixes score")
    tune = ev.score(ev.read_csv(dev_csv), ev.load_predictions(pred_dir, "tune"), "tune")
    assert tune["n_rows"] == 4


def test_dev_eval_bootstrap_against_a_base(tmp_path: Path, pred_dir: Path) -> None:
    ev = _load("dev_eval")
    dev_csv = tmp_path / "dev.csv"
    _write(dev_csv, DEV_HEADER, DEV)
    base = tmp_path / "base"
    shutil.copytree(pred_dir, base)
    better = [["D1", "Finance", "low", "1", "1", ""], ["D2", "Facilities", "high", "1", "1", ""],
              ["D3", "Academic Support", "low", "1", "1", ""]]
    _write(base / "tune_en.csv", PRED_HEADER, better)
    res = ev.score(ev.read_csv(dev_csv), ev.load_predictions(pred_dir, "all"), "all",
                   ev.load_predictions(base, "all"))
    delta = res["languages"]["pooled"]["vs_base"]["priority"]
    assert delta["n"] == 5 and delta["delta"] < 0 and delta["ci_low"] <= delta["ci_high"]


def test_dev_eval_refuses_forbidden_paths(tmp_path: Path) -> None:
    ev = _load("dev_eval")
    for bad in (Path(r"C:\Users\hp\Desktop\campuspulse_eval") / "preds", REPO_ROOT / "data" / "our_test" / "x",
                REPO_ROOT / "data" / "robustness"):
        with pytest.raises(ValueError, match="refused"):
            ev.check_allowed(bad)
    assert ev.main(["score", "--pred", str(REPO_ROOT / "data" / "our_test"), "--out", str(tmp_path / "o.json")]) == 2
    ev.check_allowed(tmp_path)


def test_scratch_model_copies_and_rewrites_manifest(tmp_path: Path) -> None:
    sm = _load("scratch_model")
    src = tmp_path / "frozen"
    (src / "lexicons").mkdir(parents=True)
    (src / "encoder").mkdir()
    (src / "config.json").write_text('{"artifact_version": "v1"}', encoding="utf-8")
    (src / "encoder" / "w.bin").write_bytes(b"weights")
    (src / "lexicons" / "safety.yaml").write_text("a: 1\n", encoding="utf-8")
    store = FileArtifactStore()
    store.write_manifest(src, [src / "config.json", src / "encoder" / "w.bin", src / "lexicons" / "safety.yaml"])
    lex = tmp_path / "lex"
    lex.mkdir()
    (lex / "safety.yaml").write_text("a: 2\n", encoding="utf-8")
    (lex / "extra.yaml").write_text("b: 1\n", encoding="utf-8")
    out = tmp_path / "scratch"
    sha = sm.build_scratch(out, lex, src, models_root=tmp_path / "models")
    manifest = store.load_manifest(out)  # verifies every hash
    assert manifest.sha == sha and sha != store.load_manifest(src).sha
    assert set(manifest.files) == {"config.json", "encoder/w.bin", "lexicons/safety.yaml", "lexicons/extra.yaml"}
    assert (src / "lexicons" / "safety.yaml").read_text(encoding="utf-8") == "a: 1\n"
    with pytest.raises(ValueError, match="never go there"):
        sm.build_scratch(tmp_path / "models" / "x", lex, src, models_root=tmp_path / "models")
    with pytest.raises(ValueError, match="already exists"):
        sm.build_scratch(out, lex, src, models_root=tmp_path / "models")
