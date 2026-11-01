"""P8.1 retrain tools: scratch-only model-reviewed training, score_holdout sha guard, rc_compare."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from campuspulse_ai.composition.training import _is_scratch
from campuspulse_ai.config.paths import REPO_ROOT
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scratch_dir_is_outside_models() -> None:
    assert not _is_scratch(REPO_ROOT / "models" / "frozen" / "v1")
    assert _is_scratch(REPO_ROOT / ".tmp" / "rc5" / "C1")


def test_score_holdout_refuses_a_file_with_another_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load("score_holdout")
    holdout = tmp_path / "h.csv"
    header = "id,lang,text,category,priority,wrapper\n"
    holdout.write_text(header + "X1,en,hello,Finance,low,0\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["score_holdout.py", "--model-dir", str(tmp_path), "--mode", "offline",
                                      "--holdout", str(holdout)])
    assert mod.main() == 2


def test_score_holdout_score_is_the_weighted_sum() -> None:
    mod = _load("score_holdout")
    rows = [{"category": "Finance", "pred_category": "Finance", "priority": "low", "pred_priority": "low"}]
    out = mod.score_rows(rows)
    expected = 0.7 * out["category_macro_f1"] + 0.3 * out["priority_macro_f1"]
    assert out["score"] == pytest.approx(expected)
    assert mod.bucket("1", "1") == "auto"
    assert mod.bucket("2", "1") == "ask"
    assert mod.bucket("3", "1") == "review"


def test_rc_compare_skips_augmented_rows(tmp_path: Path) -> None:
    mod = _load("rc_compare")
    n = 4
    cat = np.zeros((n, len(CATEGORY_LABELS)))
    cat[np.arange(n), [0, 1, 2, 3]] = 1.0
    pri = np.zeros((n, len(PRIORITY_LABELS)))
    pri[:, 0] = 1.0
    np.savez(
        tmp_path / "oof.npz",
        request_id=np.array(["a", "b", "c", "d"]),
        cv_group=np.array(["g1", "g1", "g2", "g3"]),
        lang=np.array(["en", "en", "ar", "en"]),
        category=np.array([CATEGORY_LABELS[i] for i in (0, 1, 2, 3)]),
        priority=np.array([PRIORITY_LABELS[0]] * n),
        is_official=np.array([True, True, True, False]),
        ensemble__category=cat,
        final__priority=pri,
    )
    rows = mod.load(tmp_path)
    assert sorted(rows) == ["a", "b", "c"]
    res = mod.compare(rows, rows)
    assert res["all"]["category"]["delta"] == 0.0 and res["all"]["n"] == 3


def test_category_only_rows_calibrate_category_not_priority() -> None:
    """P8.1c: the priority conformal quantile ignores category-only rows; the category one uses them."""
    from campuspulse_ai.adapters.training.stages import quantiles
    from campuspulse_ai.adapters.training.train_config import TrainCfg

    cfg = TrainCfg.load()
    n = 40
    p_cat = np.zeros((n, len(CATEGORY_LABELS)))
    p_cat[:, 0] = 1.0
    p_pri = np.zeros((n, len(PRIORITY_LABELS)))
    p_pri[:, 0] = 1.0
    y_cat = [CATEGORY_LABELS[0]] * 30 + [CATEGORY_LABELS[1]] * 10  # last 10 rows are wrong for both targets
    y_pri = [PRIORITY_LABELS[0]] * 30 + [PRIORITY_LABELS[1]] * 10
    groups = [f"g{i}" for i in range(n)]
    only = [False] * 30 + [True] * 10
    q_cat, q_pri = quantiles(p_cat, p_pri, y_cat, y_pri, groups, cfg, only)
    assert q_cat == pytest.approx(1.0) and q_pri == pytest.approx(0.0)
    assert quantiles(p_cat, p_pri, y_cat, y_pri, groups, cfg)[1] == pytest.approx(1.0)
