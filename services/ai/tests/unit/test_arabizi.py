"""ArabiziTransliterator: lexicon-first transliteration and the model_text format (P1.2)."""

from __future__ import annotations

import pandas as pd
import pytest

from campuspulse_ai.adapters.preprocess.arabizi import ArabiziTransliterator
from campuspulse_ai.adapters.preprocess.wrappers import normalize_text
from campuspulse_ai.config.paths import LEXICONS, REPO_ROOT

GOLDEN = REPO_ROOT / "services" / "ai" / "tests" / "fixtures" / "arabizi_golden.csv"


@pytest.fixture(scope="module")
def translit() -> ArabiziTransliterator:
    return ArabiziTransliterator.from_yaml(LEXICONS / "arabizi.yaml")


def test_mesh_3arif(translit: ArabiziTransliterator) -> None:
    assert translit.transliterate("mesh 3arif") == "مش عارف"


def test_golden_pairs_exact(translit: ArabiziTransliterator) -> None:
    golden = pd.read_csv(GOLDEN, encoding="utf-8", dtype=str)
    assert len(golden) >= 20
    wrong = [
        (src, translit.transliterate(src), normalize_text(dst, "ar"))
        for src, dst in zip(golden.arabizi, golden.arabic, strict=True)
        if translit.transliterate(src) != normalize_text(dst, "ar")
    ]
    assert wrong == []


def test_model_text_format(translit: ArabiziTransliterator) -> None:
    assert translit.model_text("wein el bus") == "وين الباص | wein el bus"
