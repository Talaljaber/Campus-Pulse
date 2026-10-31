"""Extra WrapperStripper behaviour beyond the P1.1 parity suite: no over-stripping of real content."""

from __future__ import annotations

import pytest

from campuspulse_ai.adapters.preprocess.wrappers import (
    WrapperStripper,
    collapse_ws,
    normalize_text,
    script_lang,
)
from campuspulse_ai.config.paths import LEXICONS
from campuspulse_ai.domain.values import StripResult


def run(stripper: WrapperStripper, raw: str) -> StripResult:
    return stripper.strip(raw)


@pytest.fixture(scope="module")
def stripper() -> WrapperStripper:
    return WrapperStripper.from_yaml(LEXICONS / "wrappers.yaml")


@pytest.mark.parametrize(
    "raw",
    [
        "Urgently need the bus timetable",  # \b in urgent_regex: "Urgently" is content
        "Please help me reset my password",  # a bare wrapper base is never stripped
        "Hello",  # a wrapper with nothing after it is kept (clean_data rule)
        "Hi team the projector is broken",
    ],
)
def test_content_is_not_stripped(stripper: WrapperStripper, raw: str) -> None:
    assert run(stripper, raw).core == collapse_ws(raw)


def test_stacked_wrappers_and_glued_suffix(stripper: WrapperStripper) -> None:
    result = run(stripper, "Hello, hi team, URGENT: The bus is late Please respond when possible.")
    assert result.core == "The bus is late"
    assert result.prefix == "Hello, hi team, URGENT:"
    assert result.suffix == "Please respond when possible."
    assert result.stated_urgency is True


def test_arabic_variants(stripper: WrapperStripper) -> None:
    assert run(stripper, "مرحبا, الباص تأخر").core == "الباص تأخر"
    assert run(stripper, "مرحبا، الباص تأخر وشكرا.").core == "الباص تأخر"
    assert run(stripper, "لو سمحت، الباص تأخر").core == "الباص تأخر"


def test_normalize_helpers() -> None:
    assert collapse_ws("  a\xa0 b\t\nc ") == "a b c"
    assert script_lang("mesh 3arif wein el bus") == "en"
    assert script_lang("وين الباص") == "ar"
    assert normalize_text("كيف بغير كلمة السر؟", "ar") == "كيف بغير كلمه السر"
    english = normalize_text("Where can I meet my academic advisor?", "en")
    assert english == "where can i meet my academic advisor"
    assert normalize_text("أَحْمَد إلى آخر مسؤول", "ar") == "احمد الي اخر مسوول"
