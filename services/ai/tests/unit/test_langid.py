"""LangIdentifier: zero Arabizi false positives on official data, golden Arabizi detected (P1.2)."""

from __future__ import annotations

import pandas as pd
import pytest

from campuspulse_ai.adapters.preprocess.langid import LangIdentifier
from campuspulse_ai.config.paths import DATA_CLEAN, LEXICONS, REPO_ROOT
from campuspulse_ai.domain.values import Lang

GOLDEN = REPO_ROOT / "services" / "ai" / "tests" / "fixtures" / "arabizi_golden.csv"


@pytest.fixture(scope="module")
def langid() -> LangIdentifier:
    return LangIdentifier.from_yaml(LEXICONS / "arabizi.yaml")


@pytest.fixture(scope="module")
def official() -> pd.DataFrame:
    path = DATA_CLEAN / "train_val_combined.csv"
    return pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False)


def test_zero_arabizi_on_432_official(langid: LangIdentifier, official: pd.DataFrame) -> None:
    assert len(official) == 432
    hits = [rid for rid, text in zip(official.request_id, official.text, strict=True)
            if langid.identify(text) is Lang.ARABIZI]
    assert hits == []


def test_ar_and_en_match_clean_lang(langid: LangIdentifier, official: pd.DataFrame) -> None:
    got = [langid.identify(text).value for text in official.text]
    assert got == list(official.lang)
    assert got.count("en") == 297 and got.count("ar") == 135


def test_golden_arabizi_detected(langid: LangIdentifier) -> None:
    golden = pd.read_csv(GOLDEN, encoding="utf-8", dtype=str)
    assert len(golden) >= 20
    missed = [t for t in golden.arabizi if langid.identify(t) is not Lang.ARABIZI]
    assert missed == []


ENGLISH_PROBES = (
    "I got a 2nd notice at 3pm",
    "My room is B3 and C5",
    "CS201 and MATH102 are both full",
    "Tuition fee for semester 2",
    "Fee payment failed",
    "Law faculty printer broken",
    "Sir, the AC is off",
    "2FA code not received",
    "Need ipv6 on campus network",
    "Exam in room A3 at 9am",
    "wifi down in lab M214",
)


def test_english_with_digits_stays_en(langid: LangIdentifier) -> None:
    wrong = [text for text in ENGLISH_PROBES if langid.identify(text) is not Lang.EN]
    assert wrong == []
