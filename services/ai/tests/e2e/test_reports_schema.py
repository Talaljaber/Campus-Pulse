"""The P2.8 report files have the shape the report, the notebooks and the Model lab rely on.

Run after `python services/ai/evaluate.py --all` (they read `reports/`, never recompute).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from campuspulse_ai.config.paths import REPORTS
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS

pytestmark = pytest.mark.artifacts
HEADER = ("artifact_version", "sha", "generated_at", "protocol")
REQUIRED_MODELS = {
    "M1",
    "M2-LR",
    "M2-kNN",
    "M3",
    "Ensemble (tier 0)",
    "Ensemble + router",
    "LLM zero-shot (M4)",
}
SPEC_ARMS = {
    "full",
    "-wrapper_stripping",
    "-augmentation",
    "-urgency_features",
    "hard_targets",
    "mask_deadline",
}
MEMBER_ARMS = {"-m1", "-m2lr", "-m2knn", "-m2proto"}


def _load(name: str) -> dict[str, Any]:
    path = REPORTS / name
    if not path.is_file():
        pytest.skip(f"{path} missing: run `python services/ai/evaluate.py --all`")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    for key in HEADER:
        assert key in data, f"{name} lacks {key}"
    return data


def test_metrics() -> None:
    m = _load("metrics.json")
    assert m["counts"]["oof_official"] == 432 and m["counts"]["our_test"] >= 60
    assert {"our_test_set1", "our_test_set2", "our_test_set3"} <= set(m["counts"])
    assert 0.0 <= m["ask_proxy_rate"] <= 1.0


def test_benchmark() -> None:
    rows = _load("metrics.json")["benchmark"]
    assert {r["model"] for r in rows} >= REQUIRED_MODELS
    status = {(r["model"], r["dataset"], r["target"]): r["status"] for r in rows}
    assert status[("M3", "oof_official", "category")] == "cut"
    assert status[("Ensemble + router", "our_test", "priority")] == "n/a"
    ens = [r for r in rows if r["model"] == "Ensemble (tier 0)" and r["status"] == "ok"]
    assert all(r["n_rows"] > 0 and r["n_groups"] for r in ens)
    assert (REPORTS / "benchmark.md").read_text(encoding="utf-8").startswith("# Benchmark")


def test_coverage() -> None:
    cov = _load("coverage.json")
    keys = {(r["target"], r["lang"]) for r in cov["rows"] if r["dataset"] == "our_test"}
    for target in ("category", "priority"):
        assert {(target, lang) for lang in ("all", "en", "ar", "arabizi")} <= keys
    assert all(r["n_rows"] > 0 and r["n_groups"] for r in cov["rows"])
    assert {"alpha_priority", "mondrian_by_lang"} <= set(cov["config"])
    assert len(cov["calibration_our_test"]) == 2


def test_fairness() -> None:
    fair = _load("fairness.json")
    test = [s for s in fair["slices"] if s["dataset"] == "our_test"]
    assert {s["slice"] for s in test} == {"en", "ar", "arabizi"}
    assert all(s["n_rows"] > 0 and s["n_groups"] for s in fair["slices"])
    assert fair["max_gap"]


def test_ablations() -> None:
    abl = _load("ablations.json")
    arms = abl["arms"]
    assert set(arms) >= SPEC_ARMS | MEMBER_ARMS and len(arms) >= 9
    for name, arm in arms.items():
        for dataset in ("oof_official", "our_test"):
            for target in ("category", "priority"):
                assert 0.0 <= arm[dataset][target]["macro_f1"] <= 1.0, (name, dataset, target)
        assert "ci90" in arm["oof_official"]["category"]


def test_confusions() -> None:
    files = sorted((REPORTS / "confusions").glob("*.json"))
    if not files:
        pytest.skip("no confusion matrices yet")
    for path in files:
        c = json.loads(path.read_text(encoding="utf-8"))
        labels = CATEGORY_LABELS if c["target"] == "category" else PRIORITY_LABELS
        assert c["labels"] == list(labels) and len(c["matrix"]) == len(labels)
        assert all(len(row) == len(labels) for row in c["matrix"])


def test_errors() -> None:
    err = _load("errors.json")
    for row in err["our_test"]:
        assert {"request_id", "test_set", "lang", "gold", "pred", "set_category", "set_priority"} <= set(row)
    assert isinstance(err["oof_official_groups"], list)


def test_eda() -> None:
    eda = _load("eda.json")
    assert eda["official"]["rows"] == 432 and eda["official"]["groups"] == 30
    assert eda["our_test"]["rows"] >= 60 and "augmented" in eda


def test_model_lab_matches_the_dto() -> None:
    from campuspulse_ai.application import dto

    path = Path(REPORTS / "model_lab.json")
    if not path.is_file():
        pytest.skip("no model_lab.json")
    lab = json.loads(path.read_text(encoding="utf-8"))
    datasets = {r["dataset"] for r in lab["benchmark"]}
    assert {"our_test_set1", "our_test_set2", "our_test_set3", "our_test", "oof_official"} <= datasets
    for row in lab["benchmark"]:
        dto.BenchmarkRowOut.model_validate(row)
