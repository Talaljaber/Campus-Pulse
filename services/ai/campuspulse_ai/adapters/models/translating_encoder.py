"""`TranslatingEncoder`: translate-test in front of a `SentenceEncoder` (P2.15, D-019).

Every input whose letters are at least `min_arabic_ratio` Arabic script is replaced by its English translation
before it is embedded; everything else (English, Arabizi, whose Latin letters dominate) passes through. It
wraps the encoder only. The injection and safety guards, priority rules, language id, M1 (TF-IDF) and the
conformal groups read the original text in `TriageCore`, never the translation. Train and test time use the
same wrapper, so the training pool, office descriptions, exemplar indexes and live requests share one space.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from campuspulse_ai.adapters.preprocess.arabizi import MODEL_TEXT_SEPARATOR
from campuspulse_ai.domain.ports import SentenceEncoder, Translator

_ARABIC = re.compile("[؀-ۿݐ-ݿ]")
DEFAULT_MIN_ARABIC_RATIO = 0.3


def arabic_ratio(text: str) -> float:
    """Share of the letters of `text` that are Arabic script (0.0 when it has no letters)."""
    letters = sum(c.isalpha() for c in text)
    return len(_ARABIC.findall(text)) / letters if letters else 0.0


def needs_translation(text: str, min_ratio: float = DEFAULT_MIN_ARABIC_RATIO) -> bool:
    ratio = arabic_ratio(text)
    return ratio > 0.0 and ratio >= min_ratio


class TranslatingEncoder:
    """Implements `SentenceEncoder`; other attributes (`revision`, `encode_array`) come from `inner`."""

    def __init__(
        self,
        inner: SentenceEncoder,
        translator: Translator,
        min_arabic_ratio: float = DEFAULT_MIN_ARABIC_RATIO,
        translate_arabizi: bool = False,
    ) -> None:
        if not 0.0 < min_arabic_ratio <= 1.0:
            raise ValueError("min_arabic_ratio must be in (0, 1]")
        self.inner = inner
        self.translator = translator
        self.min_arabic_ratio = min_arabic_ratio
        self.translate_arabizi = translate_arabizi
        self.dim: int = inner.dim
        self.model_id: str = inner.model_id

    def __getattr__(self, name: str) -> Any:
        if name == "inner":  # not set yet (copy/pickle): do not recurse
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _arabizi_source(self, text: str) -> str | None:
        """The Arabic-letter half of an Arabizi `model_text` (`transliteration | original`), else None."""
        left, sep, right = text.partition(MODEL_TEXT_SEPARATOR)
        if not sep or arabic_ratio(right) > 0.0:
            return None
        return left if needs_translation(left, self.min_arabic_ratio) else None

    def prepare(self, texts: Sequence[str]) -> list[str]:
        """The texts the encoder will see: Arabic-script ones translated, the rest unchanged.

        With `translate_arabizi`, an Arabizi `model_text` is replaced by the translation of its
        transliteration alone (never of the joined text, which derails the decoder). Without it, Arabizi
        is passed through as before.
        """
        out = list(texts)
        src: dict[int, str] = {}
        for i, t in enumerate(out):
            arabizi = self._arabizi_source(t) if self.translate_arabizi else None
            if arabizi is not None:
                src[i] = arabizi
            elif needs_translation(t, self.min_arabic_ratio):
                src[i] = t
        if src:
            idx = list(src)
            for i, translated in zip(idx, self.translator.translate([src[i] for i in idx]), strict=True):
                out[i] = translated
        return out

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return self.inner.encode(self.prepare(texts))
