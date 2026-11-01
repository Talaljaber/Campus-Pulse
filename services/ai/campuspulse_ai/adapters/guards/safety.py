"""`SafetyGuard`: physical danger (→ priority floor high) and personal distress (→ support flow) (P1.5).

LD-19: offline, `danger` comes from the lexicon only. Exemplar similarity (`thresholds.tau_safety`) may only
add `distress`, which never changes a batch label. A false `danger` hit in batch would raise a row to high,
so the danger lexicon has zero hits on every non-high official row (`tests/unit/test_safety.py`).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from campuspulse_ai.domain.ports import ExemplarSimilarity
from campuspulse_ai.domain.values import GuardVerdict, NormalizedRequest

log = logging.getLogger(__name__)

SAFETY_BANK = "safety_exemplars"
LEXICON_SCORE = 1.0  # verdict score of a lexicon hit (exemplar hits carry their cosine similarity)


class SafetyGuard:
    """Implements `domain.ports.Guard` (`name = "safety"`). Never raises.

    Inspects `req.model_text` (for Arabizi that is `transliteration | original`, so Arabic and Arabizi
    patterns both get a chance). One verdict, by precedence (the floor order in `domain/priority_rules.py`):
      1. a `distress` pattern → `distress` (the online use case stops and shows support; batch keeps going).
         The verdict also carries the danger matches of the same text in `danger_spans` (P7.8), so a request
         that is both is still tagged `safety`; `lexicon=True` marks the lexicon source (the distress floor);
      2. a `danger` pattern → `danger` (`TriageCore` sets `safety=True`; `PriorityFinalizer` floors to high);
      3. with exemplars and `tau_safety`: max similarity to the `safety_exemplars` bank ≥ tau → `distress`
         (never `danger`, LD-19);
      4. otherwise `none`.
    `matched_spans` holds the matched substrings (or the nearest exemplar); `score` is 1.0 for a lexicon
    hit and the cosine similarity for an exemplar hit.
    """

    name = "safety"

    def __init__(
        self,
        danger: Sequence[re.Pattern[str]],
        distress: Sequence[re.Pattern[str]],
        exemplars: ExemplarSimilarity | None = None,
        tau_safety: float | None = None,
        *,
        bank: str = SAFETY_BANK,
    ) -> None:
        """
        Args:
            danger, distress: compiled regexes (`compile_bank(path, "danger")` / `"distress"`).
            exemplars, tau_safety: optional exemplar check (both or neither); `thresholds.tau_safety`.
            bank: the exemplar collection name. P1.16 embeds `exemplars.distress` of `safety.yaml` into it,
                so a hit always means distress.

        Raises:
            ValueError: an empty danger or distress list, or only one of exemplars / tau_safety.
        """
        if not danger or not distress:
            raise ValueError("SafetyGuard needs danger and distress patterns")
        if (exemplars is None) != (tau_safety is None):
            raise ValueError("pass both exemplars and tau_safety, or neither")
        self._danger = tuple(danger)
        self._distress = tuple(distress)
        self._exemplars = exemplars
        self._tau = tau_safety
        self._bank = bank

    def inspect(self, req: NormalizedRequest) -> GuardVerdict:
        try:
            return self._inspect(req.model_text)
        except Exception:  # a guard must never fail the request (port contract)
            log.warning("safety guard failed; verdict none", exc_info=True)
            return GuardVerdict(kind="none")

    def _inspect(self, text: str) -> GuardVerdict:
        distress = _matches(self._distress, text)
        danger = _matches(self._danger, text)
        if distress:
            return GuardVerdict(
                "distress", distress, score=LEXICON_SCORE, danger_spans=danger, lexicon=True
            )
        if danger:
            return GuardVerdict("danger", danger, score=LEXICON_SCORE)
        if self._exemplars is not None and self._tau is not None:
            score, nearest = self._exemplars.max_similarity(text, self._bank)
            if score >= self._tau:
                return GuardVerdict("distress", (nearest,), score=score)
        return GuardVerdict(kind="none")


def _matches(patterns: Sequence[re.Pattern[str]], text: str) -> tuple[str, ...]:
    """Every non-empty match of every pattern, in (start, pattern) order, de-duplicated."""
    found = sorted((m.start(), m.group(0)) for p in patterns for m in p.finditer(text) if m.group(0))
    seen: dict[str, None] = {}
    for _, span in found:
        seen.setdefault(span, None)
    return tuple(seen)
