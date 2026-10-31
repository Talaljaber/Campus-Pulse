"""`InjectionGuard`: strips manipulative spans before any model or LLM sees them (P1.5, ARCHITECTURE §3.10).

Offline (`predict.py`) the mode is `strip_regex_only`: only the regex bank of `config/lexicons/injection.yaml`
fires, and the bank has zero hits on the 432 official rows (asserted by `tests/invariants/test_injection.py`).
Online (`full`, P3.5) an exemplar-similarity check over the `injection_exemplars` collection is added.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from typing import Literal

from campuspulse_ai.adapters.preprocess.arabizi import MODEL_TEXT_SEPARATOR
from campuspulse_ai.adapters.preprocess.wrappers import PUNCT, collapse_ws
from campuspulse_ai.domain.ports import ExemplarSimilarity
from campuspulse_ai.domain.values import GuardVerdict, Lang, NormalizedRequest

log = logging.getLogger(__name__)

InjectionMode = Literal["strip_regex_only", "full"]
INJECTION_BANK = "injection_exemplars"
REGEX_SCORE = 1.0  # verdict score of a regex hit (exemplar hits carry their cosine similarity)

# A sentence ends at . ! ? ؟ or a newline; the Arabizi `model_text` separator " | " also splits, so the
# transliteration and the original are handled as separate sentences.
_SENTENCE = re.compile(r"[^.!?؟\n|]+[.!?؟\n]*|\|")


class InjectionGuard:
    """Implements `domain.ports.Guard` (`name = "injection"`). Never raises.

    On a regex hit in `req.model_text` the verdict is `injection` with:
      - `matched_spans`: the matched substrings, in text order;
      - `stripped_text`: `model_text` with each match removed. When the matches cover at least
        `sentence_strip_ratio` of the sentence that holds them, the whole sentence is removed instead
        (e.g. `... the bus is late. ignore all previous instructions` loses its second sentence). The result
        is whitespace-collapsed and trimmed of edge punctuation; it may be empty when the whole request was
        an injection (TriageCore then classifies the empty remainder as it would any no-content text).
        For an Arabizi request with `arabizi_model_text` set, the original (`text_norm`) is stripped and
        `translit | original` is rebuilt from it;
      - `score`: 1.0.
    `TriageCore` replaces `model_text` with `stripped_text`, adds the flag `injection_attempt` and disables
    the LLM tiers for the request. With `mode="full"` and no regex hit, an exemplar similarity ≥ `tau`
    also flags `injection` (nothing is stripped; `matched_spans` holds the nearest exemplar).
    """

    name = "injection"

    def __init__(
        self,
        patterns: Sequence[re.Pattern[str]],
        mode: InjectionMode,
        sentence_strip_ratio: float,
        exemplars: ExemplarSimilarity | None = None,
        tau: float | None = None,
        *,
        bank: str = INJECTION_BANK,
        arabizi_model_text: Callable[[str], str] | None = None,
    ) -> None:
        """
        Args:
            patterns: compiled regexes (`compile_bank(path, "patterns")`).
            mode: `strip_regex_only` (offline) or `full` (online).
            sentence_strip_ratio: `FrozenConfig.guards.injection_sentence_strip_ratio`, in (0, 1].
            exemplars, tau: required for `full` (`thresholds.tau_injection`); ignored offline.
            bank: the exemplar collection name.
            arabizi_model_text: `ArabiziTransliterator.model_text`, the function the normalizer used. For an
                Arabizi request whose original half (`text_norm`) holds a match, the guard strips
                `text_norm` and rebuilds `translit | original` from it, so the transliteration cannot keep
                the injection in Arabic script. Without it, both halves are stripped independently.

        Raises:
            ValueError: an empty pattern list, a ratio outside (0, 1], or `full` without exemplars and tau.
        """
        if not patterns:
            raise ValueError("InjectionGuard needs at least one pattern")
        if not 0.0 < sentence_strip_ratio <= 1.0:
            raise ValueError("sentence_strip_ratio must be in (0, 1]")
        if mode == "full" and (exemplars is None or tau is None):
            raise ValueError("mode 'full' needs exemplars and tau")
        self._patterns = tuple(patterns)
        self._mode: InjectionMode = mode
        self._ratio = sentence_strip_ratio
        self._exemplars = exemplars
        self._tau = tau
        self._bank = bank
        self._arabizi_model_text = arabizi_model_text

    @property
    def mode(self) -> InjectionMode:
        return self._mode

    def inspect(self, req: NormalizedRequest) -> GuardVerdict:
        try:
            return self._inspect(req)
        except Exception:  # a guard must never fail the request (port contract)
            log.warning("injection guard failed; verdict none", exc_info=True)
            return GuardVerdict(kind="none")

    def _inspect(self, req: NormalizedRequest) -> GuardVerdict:
        text = req.model_text
        spans = self._spans(text)
        if spans:
            matched = tuple(text[a:b] for a, b in spans)
            return GuardVerdict("injection", matched, self._stripped(req, spans), REGEX_SCORE)
        if self._mode == "full" and self._exemplars is not None and self._tau is not None:
            score, nearest = self._exemplars.max_similarity(text, self._bank)
            if score >= self._tau:
                return GuardVerdict("injection", (nearest,), text, score)
        return GuardVerdict(kind="none")

    def _stripped(self, req: NormalizedRequest, spans: list[tuple[int, int]]) -> str:
        if req.lang is Lang.ARABIZI and self._arabizi_model_text is not None:
            original_spans = self._spans(req.text_norm)
            if original_spans:
                original = self._strip(req.text_norm, original_spans)
                return self._arabizi_model_text(original) if original else ""
        return self._strip(req.model_text, spans)

    def _spans(self, text: str) -> list[tuple[int, int]]:
        """Merged, sorted (start, end) of every non-empty match."""
        raw = sorted(m.span() for p in self._patterns for m in p.finditer(text) if m.end() > m.start())
        merged: list[tuple[int, int]] = []
        for start, end in raw:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def _strip(self, text: str, spans: list[tuple[int, int]]) -> str:
        remove: list[tuple[int, int]] = []
        for sent in _SENTENCE.finditer(text):
            s0, s1 = sent.span()
            inside = [(max(a, s0), min(b, s1)) for a, b in spans if a < s1 and b > s0]
            if not inside:
                continue
            content = len(text[s0:s1].strip(PUNCT))
            covered = sum(len(text[a:b].strip(PUNCT)) for a, b in inside)
            if content and covered / content >= self._ratio:
                remove.append((s0, s1))
            else:
                remove.extend(inside)
        kept: list[str] = []
        cursor = 0
        for a, b in sorted(remove):
            if a > cursor:
                kept.append(text[cursor:a])
            cursor = max(cursor, b)
        kept.append(text[cursor:])
        return _tidy("".join(kept))


def _tidy(text: str) -> str:
    """Collapse whitespace and trim edge punctuation per part, so Arabizi keeps `translit | original`."""
    sep = MODEL_TEXT_SEPARATOR.strip()
    parts = [collapse_ws(part).strip(PUNCT) for part in text.split(sep)]
    return MODEL_TEXT_SEPARATOR.join(p for p in parts if p)
