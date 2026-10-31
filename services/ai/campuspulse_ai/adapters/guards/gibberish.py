"""`GibberishGuard`: flags noise such as `???` or `asdf;;;;` (P1.5, ARCHITECTURE §2.0)."""

from __future__ import annotations

import logging

from campuspulse_ai.domain.values import GuardVerdict, NormalizedRequest

log = logging.getLogger(__name__)


class GibberishGuard:
    """Implements `domain.ports.Guard` (`name = "gibberish"`). Never raises.

    Reads `req.core` (the text after wrapper stripping, before punctuation trimming), because
    normalization would hide the symbol runs this guard measures. A request is gibberish when it has fewer
    than `min_tokens` whitespace tokens containing a letter, or when letters make up less than
    `min_letter_ratio` of its non-space characters. Arabic letters count as letters; Arabizi digits do not,
    but Arabizi words are mostly letters. The verdict `score` is the letter ratio.

    In batch the flag never changes a label (§2.0); online the decision policy sends it to OUT_OF_SCOPE.
    """

    name = "gibberish"

    def __init__(self, min_tokens: int, min_letter_ratio: float) -> None:
        """
        Args:
            min_tokens: `FrozenConfig.guards.gibberish_min_tokens`.
            min_letter_ratio: `FrozenConfig.guards.gibberish_min_letter_ratio`, in (0, 1].

        Raises:
            ValueError: `min_tokens` < 1 or `min_letter_ratio` outside (0, 1].
        """
        if min_tokens < 1:
            raise ValueError("min_tokens must be >= 1")
        if not 0.0 < min_letter_ratio <= 1.0:
            raise ValueError("min_letter_ratio must be in (0, 1]")
        self._min_tokens = min_tokens
        self._min_letter_ratio = min_letter_ratio

    def inspect(self, req: NormalizedRequest) -> GuardVerdict:
        try:
            return self._inspect(req.core)
        except Exception:  # a guard must never fail the request (port contract)
            log.warning("gibberish guard failed; verdict none", exc_info=True)
            return GuardVerdict(kind="none")

    def _inspect(self, text: str) -> GuardVerdict:
        visible = [ch for ch in text if not ch.isspace()]
        letters = sum(ch.isalpha() for ch in visible)
        ratio = letters / len(visible) if visible else 0.0
        words = [tok for tok in text.split() if any(ch.isalpha() for ch in tok)]
        if len(words) < self._min_tokens or ratio < self._min_letter_ratio:
            return GuardVerdict(kind="gibberish", score=ratio)
        return GuardVerdict(kind="none", score=ratio)
