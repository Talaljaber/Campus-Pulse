"""P2.17 arm C: `translate.arabizi` translates the Arabic-letter half of an Arabizi `model_text` only."""

from __future__ import annotations

from collections.abc import Sequence

from fixtures.tiny_core import build_tiny_core

from campuspulse_ai.adapters.models.translating_encoder import TranslatingEncoder
from campuspulse_ai.adapters.models.translator import NoopTranslator
from campuspulse_ai.composition.translation import wrap_encoder
from campuspulse_ai.config.frozen import TranslateCfg
from campuspulse_ai.domain.values import Lang

BENIGN = "the projector in the lecture room is broken"
ARABIZI_DANGER = "el tolab 3al2aneen bel mas3ad"


class SpyTranslator:
    model_id = "spy"
    revision = "0"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def translate(self, texts: Sequence[str]) -> list[str]:
        self.seen.extend(texts)
        return [BENIGN for _ in texts]


class SpyEncoder:
    dim = 4
    model_id = "spy-encoder"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.seen.extend(texts)
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def test_flag_off_keeps_the_joined_text_route() -> None:
    inner, spy = SpyEncoder(), SpyTranslator()
    joined = "الطلاب عالقين | el tolab 3al2aneen"
    TranslatingEncoder(inner, spy).encode([joined])
    assert spy.seen == [joined]  # rc3 behaviour: the joined text passes the 30 % gate


def test_flag_translates_only_the_arabic_letter_half() -> None:
    inner, spy = SpyEncoder(), SpyTranslator()
    enc = TranslatingEncoder(inner, spy, translate_arabizi=True)
    texts = ["الطلاب عالقين | el tolab 3al2aneen", "the bus is late", "الباص متأخر", "mesh | mesh"]
    enc.encode(texts)
    assert spy.seen == ["الطلاب عالقين", "الباص متأخر"]
    assert inner.seen == [BENIGN, "the bus is late", BENIGN, "mesh | mesh"]


def test_flag_never_changes_what_the_guards_read() -> None:
    spy = SpyTranslator()
    plain = build_tiny_core()
    core = build_tiny_core(lambda enc: TranslatingEncoder(enc, spy, translate_arabizi=True))
    req, result = core.classify(ARABIZI_DANGER)
    base_req, base = plain.classify(ARABIZI_DANGER)
    assert req.lang is Lang.ARABIZI and spy.seen  # the transliteration was translated
    assert req.model_text == base_req.model_text and ARABIZI_DANGER in req.model_text
    assert BENIGN not in req.model_text
    assert result.safety == base.safety and result.flags == base.flags
    assert result.floors_applied == base.floors_applied
    assert result.per_model["m1.category"] == base.per_model["m1.category"]


def test_cfg_defaults_off_and_reaches_the_wrapper() -> None:
    assert TranslateCfg().arabizi is False
    base = {"enabled": True, "model": "m", "revision": "r"}
    on = wrap_encoder(SpyEncoder(), NoopTranslator(), TranslateCfg(**base, arabizi=True))
    off = wrap_encoder(SpyEncoder(), NoopTranslator(), TranslateCfg(**base))
    assert isinstance(on, TranslatingEncoder) and on.translate_arabizi
    assert isinstance(off, TranslatingEncoder) and not off.translate_arabizi
