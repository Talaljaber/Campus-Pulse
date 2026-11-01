"""`LlmArabiziEncoder`: LLM-translated Arabizi in front of the encoder only (P2.20, D-025).

Optional and off by default.

The encoder sees Arabizi requests as `"<arabic-letter transliteration> | <original>"` (see
`adapters/preprocess/arabizi.py`). Where the optional LLM translator returns an English translation of the
original half, the encoder receives that English text instead. Everything else (English, Arabic, a failed
or rejected translation) passes through unchanged, exactly as without this wrapper. The guards, langid, M1
(TF-IDF), priority rules and conformal groups never see the translation: they read `TriageCore`'s own copy.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from campuspulse_ai.adapters.llm.arabizi_translator import LlmArabiziTranslator
from campuspulse_ai.adapters.models.translating_encoder import arabic_ratio
from campuspulse_ai.adapters.preprocess.arabizi import MODEL_TEXT_SEPARATOR
from campuspulse_ai.domain.ports import SentenceEncoder

log = logging.getLogger(__name__)


def split_arabizi(model_text: str) -> str | None:
    """The Latin original of an Arabizi `model_text`, or None when it is not one."""
    head, sep, tail = model_text.rpartition(MODEL_TEXT_SEPARATOR)
    if not sep or not head or not tail.strip():
        return None
    if arabic_ratio(head) < 0.5 or arabic_ratio(tail) > 0.0 or not any(c.isalpha() for c in tail):
        return None
    return tail.strip()


class LlmArabiziEncoder:
    """Implements `SentenceEncoder`; other attributes come from `inner`."""

    def __init__(self, inner: SentenceEncoder, translator: LlmArabiziTranslator) -> None:
        self.inner = inner
        self.translator = translator
        self.dim: int = inner.dim
        self.model_id: str = inner.model_id
        self.last_used: dict[str, str] = {}  # original -> translation used (debug)

    def __getattr__(self, name: str) -> Any:
        if name in ("inner", "translator"):
            raise AttributeError(name)
        return getattr(self.inner, name)

    def prepare(self, texts: Sequence[str]) -> list[str]:
        out = list(texts)
        for i, t in enumerate(out):
            original = split_arabizi(t)
            if original is None:
                continue
            translated = self.translator.translate_one(original)
            if translated is not None:
                self.last_used[original] = translated
                log.debug("arabizi llm translation used: %r -> %r", original, translated)
                out[i] = translated
        return out

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return self.inner.encode(self.prepare(texts))
