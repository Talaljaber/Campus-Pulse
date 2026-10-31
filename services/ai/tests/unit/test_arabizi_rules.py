"""Arabizi rule paths beyond the golden pairs: proclitics, char-map fallback, config validation."""

from __future__ import annotations

import pytest

from campuspulse_ai.adapters.preprocess.arabizi import ArabiziTransliterator
from campuspulse_ai.adapters.preprocess.langid import LangIdentifier, latin_tokens
from campuspulse_ai.config.paths import LEXICONS
from campuspulse_ai.domain.values import Lang


@pytest.fixture(scope="module")
def translit() -> ArabiziTransliterator:
    return ArabiziTransliterator.from_yaml(LEXICONS / "arabizi.yaml")


def test_attached_and_stacked_proclitics(translit: ArabiziTransliterator) -> None:
    assert translit.transliterate("elbus") == "الباص"
    assert translit.transliterate("w el edafe") == "والاضافه"
    assert translit.transliterate("ana w el") == "انا وال"  # trailing proclitic is kept


def test_char_map_fallback(translit: ArabiziTransliterator) -> None:
    # not in the lexicon: digraph "sh" + char map; short vowel "e" is dropped
    assert translit.transliterate("shebek") == "شبك"
    assert translit.transliterate("7mar") == "حمار"


def test_arabic_and_symbols_pass_through(translit: ArabiziTransliterator) -> None:
    assert translit.transliterate("mesh 3arif 😕") == "مش عارف 😕"
    assert translit.transliterate("wein الباص") == "وين الباص"


def test_digit_words_alone_trigger_arabizi() -> None:
    langid = LangIdentifier.from_yaml(LEXICONS / "arabizi.yaml")
    assert langid.identify("7abibi sa3edni") is Lang.ARABIZI  # two digit-words, no lexicon needed
    assert langid.identify("sa3edni") is Lang.ARABIZI  # lexicon hit
    assert langid.identify("ok") is Lang.EN


def test_evidence_and_guard_overlap_rejected() -> None:
    with pytest.raises(ValueError):
        LangIdentifier(frozenset({"the"}), frozenset({"the"}), frozenset({"3"}), 2, 1)


def test_latin_tokens() -> None:
    tokens = latin_tokens("Wein el BUS?? 24/7 sha3'al, cs-201.")
    assert tokens == ["wein", "el", "bus", "24/7", "sha3'al", "cs-201"]
