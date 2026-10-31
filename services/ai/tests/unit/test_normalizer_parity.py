"""Byte-for-byte parity of the package stripper/normalizer with scripts/clean_data.py (P1.1)."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pandas as pd
import pytest
import yaml

from campuspulse_ai.adapters.preprocess.wrappers import WrapperStripper, normalize_text, script_lang
from campuspulse_ai.config.paths import DATA_CLEAN, LEXICONS, REPO_ROOT
from campuspulse_ai.domain.values import StripResult


def _clean_data() -> ModuleType:
    """scripts/clean_data.py, imported read-only (its top level defines constants and functions only)."""
    spec = importlib.util.spec_from_file_location("clean_data", REPO_ROOT / "scripts" / "clean_data.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def run(stripper: WrapperStripper, raw: str) -> StripResult:
    return stripper.strip(raw)


@pytest.fixture(scope="module")
def stripper() -> WrapperStripper:
    return WrapperStripper.from_yaml(LEXICONS / "wrappers.yaml")


@pytest.fixture(scope="module")
def official() -> pd.DataFrame:
    path = DATA_CLEAN / "train_val_combined.csv"
    frame = pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False)
    assert len(frame) == 432
    return frame


def test_core_parity_432(stripper: WrapperStripper, official: pd.DataFrame) -> None:
    mismatches = []
    for row in official.itertuples():
        result = run(stripper, row.text)
        if (result.core, result.prefix, result.suffix) != (row.core, row.prefix, row.suffix):
            mismatches.append(row.request_id)
    assert mismatches == []


def test_text_norm_parity_432(stripper: WrapperStripper, official: pd.DataFrame) -> None:
    mismatches = [
        row.request_id
        for row in official.itertuples()
        if normalize_text(run(stripper, row.text).core, script_lang(row.text)) != row.text_norm
        or script_lang(row.text) != row.lang
    ]
    assert mismatches == []


def test_stated_urgency_matches_has_urgent_marker(stripper: WrapperStripper, official: pd.DataFrame) -> None:
    flagged = [run(stripper, t).stated_urgency for t in official["text"]]
    assert flagged == list(official["has_urgent_marker"] == "True")
    by_split = official.assign(flag=flagged).groupby("split")["flag"].sum().to_dict()
    assert by_split == {"train": 23, "val": 4}


def test_lowercase_urgent_prefix_stripped_and_flagged(stripper: WrapperStripper) -> None:
    result = run(stripper, "urgent: The bus is late")
    assert result.core == "The bus is late"
    assert result.stated_urgency is True


def test_yaml_lists_equal_clean_data_constants() -> None:
    cd = _clean_data()
    cfg = yaml.safe_load((LEXICONS / "wrappers.yaml").read_text(encoding="utf-8"))
    assert cfg["prefixes"] == cd.KNOWN_PREFIXES
    assert cfg["suffixes"] == cd.KNOWN_SUFFIXES


@pytest.mark.parametrize(
    "raw",
    [
        "urgent: The bus is late",
        "URGENT The bus is late",
        "Hello! The bus is late",
        "hi team, The bus is late",
    ],
)
def test_unseen_wrappers_stripped(stripper: WrapperStripper, raw: str) -> None:
    assert run(stripper, raw).core == "The bus is late"


def test_urgent_variants_set_stated_urgency(stripper: WrapperStripper) -> None:
    urgent = ["URGENT The bus is late", "Urgent! The bus is late", "urgent:the bus is late"]
    for raw in [*urgent, "عاجل الباص تأخر"]:
        assert run(stripper, raw).stated_urgency is True, raw
    for raw in ("The bus is late", "Hello, The bus is late", "Urgently need the bus timetable"):
        assert run(stripper, raw).stated_urgency is False, raw
