"""load_pool details beyond the P1.8 acceptance tests: augmentation filtering, schema errors, ablations."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest
import yaml

from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.cv import group_folds
from campuspulse_ai.adapters.training.pool import AUGMENTED_COLUMNS, NO_FOLD, OFFICIAL_CSV, load_pool
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.values import Lang


@pytest.fixture(scope="module")
def normalizer() -> DefaultNormalizer:
    return DefaultNormalizer.from_lexicons(LEXICONS, 256)


def _aug(path: Path, rows: list[list[str]], header: tuple[str, ...] = AUGMENTED_COLUMNS) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_official_pool_matches_clean_data(normalizer: DefaultNormalizer) -> None:
    pool = load_pool([OFFICIAL_CSV], normalizer)
    clean = pd.read_csv(OFFICIAL_CSV, dtype=str, keep_default_na=False)
    assert len(pool) == 432 and all(pool.is_official) and set(pool.source) == {"official"}
    assert list(pool.text_norm) == list(clean.text_norm)
    assert list(pool.model_text) == list(clean.text_norm)  # no Arabizi in official data
    assert list(pool.lang_script) == list(clean.lang)
    assert {lang.value for lang in pool.lang} == {"en", "ar"}
    assert min(pool.cv_fold) == 0


def test_augmented_rows_reviewed_only(tmp_path: Path, normalizer: DefaultNormalizer) -> None:
    path = _aug(tmp_path / "aug.csv", [
        ["AUG-AZ-0001", "wein jadwal el basat", "arabizi", "arabizi_rule", "TR-S15", "TR-S15", "False",
         "rule", "Transportation", "low"],
        ["AUG-AZ-0002", "wein el bus", "arabizi", "arabizi_rule", "TR-S15", "TR-S15", "True", "rule",
         "Transportation", "low"],
        ["AUG-NS-0001", "The library printer is jammed", "en", "new_scenario", "NEW-S01", "NEW-S01", "false",
         "llm:x", "IT Support", "medium"],
    ])
    pool = load_pool([OFFICIAL_CSV, path], normalizer)
    assert len(pool) == 434 and pool.request_id[-2:] == ("AUG-AZ-0001", "AUG-NS-0001")
    i = pool.request_id.index("AUG-AZ-0001")
    assert pool.lang[i] is Lang.ARABIZI and " | " in pool.model_text[i] and pool.lang_script[i] == "en"
    assert pool.scenario_id[i] == "TR-S15" and not pool.is_official[i]
    fold_tr_s15 = pool.cv_fold[pool.scenario_id.index("TR-S15")]
    assert pool.cv_fold[i] == fold_tr_s15  # inherits the official group's fold
    assert pool.cv_fold[-1] == NO_FOLD  # NEW-S01 not placed by make_folds yet
    with pytest.raises(InvalidInput, match="make_folds"):
        group_folds(pool, 5)
    assert len(load_pool([OFFICIAL_CSV, path], normalizer, use_augmentation=False)) == 432
    # only check_leakage and the labelled "unreviewed" ablation arm ever see the unchecked row
    everything = load_pool([OFFICIAL_CSV, path], normalizer, include_unreviewed=True)
    assert len(everything) == 435 and "AUG-AZ-0002" in everything.request_id


def test_schema_and_row_errors(tmp_path: Path, normalizer: DefaultNormalizer) -> None:
    good = ["AUG-AZ-0001", "wein el bus", "arabizi", "arabizi_rule", "TR-S15", "TR-S15", "False", "rule",
            "Transportation", "low"]
    cases = {
        "missing_sid": [good[:4] + [""] + good[5:]],
        "bad_flag": [good[:6] + ["maybe"] + good[7:]],
        "bad_label": [good[:8] + ["Parking", "low"]],
    }
    for name, rows in cases.items():
        with pytest.raises(InvalidInput):
            load_pool([OFFICIAL_CSV, _aug(tmp_path / f"{name}.csv", rows)], normalizer)
    with pytest.raises(InvalidInput, match="schema"):
        load_pool([_aug(tmp_path / "other.csv", [["x"]], header=("foo",))], normalizer)
    with pytest.raises(InvalidInput, match="duplicate"):
        load_pool([OFFICIAL_CSV, OFFICIAL_CSV], normalizer)


def test_strip_wrappers_false_keeps_wrappers(normalizer: DefaultNormalizer) -> None:
    pool = load_pool([OFFICIAL_CSV], normalizer, strip_wrappers=False)
    clean = pd.read_csv(OFFICIAL_CSV, dtype=str, keep_default_na=False)
    wrapped = clean.index[clean.prefix != ""][0]
    assert pool.model_text[wrapped] != pool.text_norm[wrapped]
    assert pool.model_text[wrapped].startswith(clean.prefix[wrapped].lower().rstrip(":,").split()[0])


def test_augmented_columns_match_datasets_yaml() -> None:
    cfg = yaml.safe_load((CONFIG_DIR / "datasets.yaml").read_text(encoding="utf-8"))
    assert tuple(cfg["augmented"]["columns"]) == AUGMENTED_COLUMNS
    assert (DATA_CLEAN / "cv_folds.csv").is_file()


def test_model_reviewed_arm_is_separate_default_off(tmp_path: Path, normalizer: DefaultNormalizer) -> None:
    rows = [
        ["AUG-AZ-0001", "wein jadwal el basat", "arabizi", "arabizi_rule", "TR-S15", "TR-S15", "True", "rule",
         "Transportation", "low"],
        ["AUG-AZ-0002", "wein el bus", "arabizi", "arabizi_rule", "TR-S15", "TR-S15", "True", "rule",
         "Transportation", "low"],
    ]
    path = _aug(tmp_path / "aug.csv", rows)
    panel = tmp_path / "model_panel_v1.csv"
    panel.write_text("request_id,decision,review_status\nAUG-AZ-0001,keep,model_panel_v1\nAUG-AZ-0002,,\n",
                     encoding="utf-8")
    assert len(load_pool([OFFICIAL_CSV, path], normalizer, model_panel_csv=panel)) == 432  # default off
    arm = load_pool([OFFICIAL_CSV, path], normalizer, include_model_reviewed=True, model_panel_csv=panel)
    assert len(arm) == 433 and "AUG-AZ-0001" in arm.request_id and "AUG-AZ-0002" not in arm.request_id


def test_category_only_rows_stay_out_of_every_priority_input(
    tmp_path: Path, normalizer: DefaultNormalizer
) -> None:
    """P8.1c (D-054): with `model_reviewed_priority=False` the priority training inputs equal the official
    pool's (C0) and the category inputs also hold the model-reviewed row."""
    from types import SimpleNamespace

    from campuspulse_ai.adapters.models.soft_targets import SoftTargetExpander
    from campuspulse_ai.adapters.training.oof import expanded, priority_rows

    rows = [["AUG-AZ-0001", "wein jadwal el basat", "arabizi", "arabizi_rule", "TR-S15", "TR-S15", "True",
             "rule", "Transportation", "low"]]
    path = _aug(tmp_path / "aug.csv", rows)
    panel = tmp_path / "model_panel_v1.csv"
    panel.write_text("request_id,decision,review_status\nAUG-AZ-0001,keep,model_panel_v1\n", encoding="utf-8")
    c0 = load_pool([OFFICIAL_CSV], normalizer)
    c1 = load_pool([OFFICIAL_CSV, path], normalizer, include_model_reviewed=True, model_panel_csv=panel)
    c3 = load_pool([OFFICIAL_CSV, path], normalizer, include_model_reviewed=True, model_panel_csv=panel,
                   model_reviewed_priority=False)
    assert not any(c0.category_only) and not any(c1.category_only)
    assert [r for r, c in zip(c3.request_id, c3.category_only, strict=True) if c] == ["AUG-AZ-0001"]
    kit = SimpleNamespace(expander=SoftTargetExpander(DATA_CLEAN / "label_flags.csv"))
    all3, all0 = list(range(len(c3))), list(range(len(c0)))
    pri3 = expanded(kit, c3, "priority", all3, True)  # type: ignore[arg-type]
    pri0 = expanded(kit, c0, "priority", all0, True)  # type: ignore[arg-type]
    pri1 = expanded(kit, c1, "priority", list(range(len(c1))), True)  # type: ignore[arg-type]
    assert pri3 == pri0 and pri1 != pri0  # (a) identical to C0; C1 would have one more row
    cat3 = expanded(kit, c3, "category", all3, True)  # type: ignore[arg-type]
    assert len(c3) - 1 in cat3[0]  # (b) the reviewed row is a category input
    assert priority_rows(c3, all3) == all0
