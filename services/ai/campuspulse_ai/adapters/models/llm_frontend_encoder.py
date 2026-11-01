"""`LlmFrontendEncoder`: the LLM front end in front of the encoder only (P7.4, D-050).

Arabic-script and Arabizi requests are replaced by the LLM's English before they are embedded; English
requests are never altered. Every request is sent in one call that also yields the internal explanation
(kept in `records`, keyed by the source text; never in a user-facing field). A failed or invalid call leaves
the text unchanged, so the inner encoder (the shipped opus-mt translate-test for Arabic) takes over exactly as
without this wrapper. Guards, langid, M1, floors and conformal read the original text in `TriageCore`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from campuspulse_ai.adapters.llm.frontend import FrontendResult, LlmFrontend
from campuspulse_ai.adapters.models.llm_arabizi_encoder import split_arabizi
from campuspulse_ai.adapters.models.translating_encoder import arabic_ratio, needs_translation
from campuspulse_ai.domain.ports import SentenceEncoder

_MAX_ENGLISH_ARABIC = 0.3


def classify_source(model_text: str) -> tuple[str, str]:
    """(language kind `en`/`ar`/`az`, source text sent to the LLM) of an encoder input."""
    original = split_arabizi(model_text)
    if original is not None:
        return "az", original
    if needs_translation(model_text):
        return "ar", model_text
    return "en", model_text


class LlmFrontendEncoder:
    """Implements `SentenceEncoder`; other attributes come from `inner`."""

    def __init__(
        self,
        inner: SentenceEncoder,
        frontend: LlmFrontend,
        *,
        workers: int = 8,
        explain_english: bool = True,
    ) -> None:
        self.inner = inner
        self.frontend = frontend
        self.workers = max(1, workers)
        self.explain_english = explain_english
        self.dim: int = inner.dim
        self.model_id: str = inner.model_id
        self.records: dict[str, FrontendResult] = {}  # source text -> result (internal, never shown)
        self.attempted: set[str] = set()
        self.latency_ms: dict[str, list[float]] = {"en": [], "ar": [], "az": []}
        self.english_changed = 0  # English rows whose LLM `english` differs from the input (diagnostic)
        self.english_rows = 0
        self.used = {"ar": 0, "az": 0}
        self.fell_back = {"ar": 0, "az": 0}

    def __getattr__(self, name: str) -> Any:
        if name in ("inner", "frontend"):
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _call(self, kind: str, source: str) -> None:
        started = time.perf_counter()
        result = self.frontend.process(source)
        self.latency_ms[kind].append((time.perf_counter() - started) * 1000)
        if result is not None:
            self.records[source] = result

    def prepare(self, texts: Sequence[str]) -> list[str]:
        kinds = [classify_source(t) for t in texts]
        todo = {
            src: kind
            for kind, src in kinds
            if src not in self.attempted and (kind != "en" or self.explain_english)
        }
        self.attempted.update(todo)
        if todo:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                list(pool.map(lambda kv: self._call(kv[1], kv[0]), todo.items()))
        out = list(texts)
        for i, (kind, src) in enumerate(kinds):
            res = self.records.get(src)
            if kind == "en":
                if res is not None and src in todo:
                    self.english_rows += 1
                    self.english_changed += res.english != " ".join(src.split())
                continue
            if res is not None and arabic_ratio(res.english) < _MAX_ENGLISH_ARABIC:
                out[i] = res.english
                self.used[kind] += src in todo
            elif src in todo:
                self.fell_back[kind] += 1
        return out

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return self.inner.encode(self.prepare(texts))
