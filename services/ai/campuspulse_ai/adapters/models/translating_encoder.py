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
    ) -> None:
        if not 0.0 < min_arabic_ratio <= 1.0:
            raise ValueError("min_arabic_ratio must be in (0, 1]")
        self.inner = inner
        self.translator = translator
        self.min_arabic_ratio = min_arabic_ratio
        self.dim: int = inner.dim
        self.model_id: str = inner.model_id

    def __getattr__(self, name: str) -> Any:
        if name == "inner":  # not set yet (copy/pickle): do not recurse
            raise AttributeError(name)
        return getattr(self.inner, name)

    def prepare(self, texts: Sequence[str]) -> list[str]:
        """The texts the encoder will see: Arabic-script ones translated, the rest unchanged."""
        out = list(texts)
        idx = [i for i, t in enumerate(out) if needs_translation(t, self.min_arabic_ratio)]
        if idx:
            for i, translated in zip(idx, self.translator.translate([out[i] for i in idx]), strict=True):
                out[i] = translated
        return out

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return self.inner.encode(self.prepare(texts))
