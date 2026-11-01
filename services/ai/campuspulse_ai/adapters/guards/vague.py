"""`VagueGuard`: flags a request that has no content, only "I have a problem, please help" (P7.9).

The `vague` bank of `config/lexicons/injection.yaml` holds whole-text patterns made of filler and generic
help words. A request fires only when EVERY word is on the list, so a vague word next to a real topic
("I need help with registration") never fires. The verdict is `vague`; `TriageCore` adds the flag
`too_vague`, the decision policy treats it like `gibberish` (the student is asked what the request is
about), and batch labels are untouched. The guard reads `text_norm`, the original request text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from campuspulse_ai.domain.values import GuardVerdict, NormalizedRequest

log = logging.getLogger(__name__)


class VagueGuard:
    """Implements `domain.ports.Guard` (`name = "vague"`). Never raises; no patterns means never fires."""

    name = "vague"

    def __init__(self, patterns: Sequence[re.Pattern[str]]) -> None:
        self._patterns = tuple(patterns)

    def inspect(self, req: NormalizedRequest) -> GuardVerdict:
        try:
            text = req.text_norm.strip()
            if text and any(p.search(text) for p in self._patterns):
                return GuardVerdict(kind="vague", matched_spans=(text,), score=1.0)
        except Exception:  # a guard must never fail the request (port contract)
            log.warning("vague guard failed; verdict none", exc_info=True)
        return GuardVerdict(kind="none")
