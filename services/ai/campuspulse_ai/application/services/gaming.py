"""GamingDetector: the anti-gaming signals, computed after the priority is final (P3.6).

ARCHITECTURE §2.1 [9b] and §3.10. It runs once per decided request and only ever *adds flags*:
- `urgency_unsupported`: this request claims urgency ("URGENT", "عاجل", ...) that neither the final
  priority nor any high-urgency evidence supports. A neutral, staff-only note.
- `priority_gaming_suspected`: this alias persistently claims urgency that the content does not
  support, or keeps trying prompt injection. Admin-only; there is no automatic penalty.

It never returns, reads back or changes a label: the priority is an input only, and `stated_urgency`
is never a model feature (it reaches the detector, never the models). Suspicion is computed here from
the counters `Repository.bump_student_signals` returns; the stored `gaming_flag` column is not used
(D-006). Both flags are removed from the student view by `application.dto.to_student_view`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable
from dataclasses import dataclass

from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.ports import Repository
from campuspulse_ai.domain.values import EvidenceVector, NormalizedRequest, StudentSignals

URGENCY_UNSUPPORTED = "urgency_unsupported"
GAMING_SUSPECTED = "priority_gaming_suspected"

# Evidence features that justify a claimed urgency even when the head settled below high
# (P3.6 step 1). Names are FrozenConfig.priority_head.features entries.
HIGH_EVIDENCE_FEATURES: frozenset[str] = frozenset(
    {"deadline_today", "exam_now", "safety_risk", "stranded", "enrollment_blocked"}
)
# P3.6 step 2: two injection attempts by one alias are enough for an admin flag.
DEFAULT_INJECTION_STRIKES = 2


@dataclass(frozen=True, slots=True)
class GamingResult:
    """The flags to add to the prediction and the alias's counters after this request.

    `signals.gaming_suspected` is the detector's verdict, not the stored database flag.
    """

    flags: frozenset[str]
    signals: StudentSignals


class GamingDetector:
    """Adds `urgency_unsupported` / `priority_gaming_suspected`; never touches a label.

    Inputs (constructor): the repository whose `bump_student_signals` keeps the per-alias counters,
    and the thresholds from Settings: `min_requests` (`GAMING_MIN_REQUESTS`), `claim_ratio`
    (`GAMING_CLAIM_RATIO`) and `high_ratio_max` (`GAMING_HIGH_RATIO_MAX`).

    Suspicion rule, evaluated on the counters *after* this request is counted:
    - `injection_attempts >= injection_strikes`, or
    - `requests >= min_requests` and `claimed_urgent / requests >= claim_ratio` and
      `supported / claimed_urgent <= high_ratio_max`, where `supported = claimed_urgent -
      claimed_urgent_not_high` (claims whose final priority really was high).

    The "high ratio" is measured over the alias's urgency claims, not over all requests, because
    the stored counters carry claimed-and-high but no plain high count (`StudentSignals`, frozen
    contract). When `claim_ratio` holds, claims are most of the requests, so the two readings differ
    only by the few unclaimed requests.

    Errors: `ValueError` on thresholds out of range (construction); `StoreError` from the
    repository propagates. Side effect: one `bump_student_signals` call per `check` with a
    non-empty alias. Anonymous requests (empty alias) are not counted and are never suspected.
    """

    def __init__(
        self,
        repo: Repository,
        min_requests: int,
        claim_ratio: float,
        high_ratio_max: float,
        *,
        injection_strikes: int = DEFAULT_INJECTION_STRIKES,
        high_evidence: Iterable[str] = HIGH_EVIDENCE_FEATURES,
    ) -> None:
        if min_requests < 1:
            raise ValueError(f"min_requests must be >= 1, got {min_requests}")
        if injection_strikes < 1:
            raise ValueError(f"injection_strikes must be >= 1, got {injection_strikes}")
        for name, ratio in (("claim_ratio", claim_ratio), ("high_ratio_max", high_ratio_max)):
            if not (math.isfinite(ratio) and 0.0 <= ratio <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {ratio!r}")
        self._repo = repo
        self._min_requests = min_requests
        self._claim_ratio = claim_ratio
        self._high_ratio_max = high_ratio_max
        self._injection_strikes = injection_strikes
        self._high_evidence = frozenset(high_evidence)

    def check(
        self,
        req: NormalizedRequest,
        priority: Priority,
        evidence: EvidenceVector,
        alias: str,
        injection: bool,
    ) -> GamingResult:
        """Count this request for `alias` and return the flags it earns (see the class docstring)."""
        flags: set[str] = set()
        claimed = req.stated_urgency
        was_high = priority == Priority.HIGH
        if claimed and not was_high and not self.has_high_evidence(evidence):
            flags.add(URGENCY_UNSUPPORTED)

        if not alias.strip():
            return GamingResult(frozenset(flags), _anonymous_signals())

        counted = self._repo.bump_student_signals(alias, claimed, was_high, injection)
        suspected = self.suspected(counted)
        if suspected:
            flags.add(GAMING_SUSPECTED)
        return GamingResult(frozenset(flags), dataclasses.replace(counted, gaming_suspected=suspected))

    def has_high_evidence(self, evidence: EvidenceVector) -> bool:
        """True when any high-urgency evidence feature fired."""
        return any(evidence.flags.get(name, False) for name in self._high_evidence)

    def suspected(self, s: StudentSignals) -> bool:
        """The suspicion rule over one alias's counters (pure; see the class docstring)."""
        if s.injection_attempts >= self._injection_strikes:
            return True
        if s.requests < self._min_requests or s.claimed_urgent == 0:
            return False
        claim_share = s.claimed_urgent / s.requests
        supported_share = (s.claimed_urgent - s.claimed_urgent_not_high) / s.claimed_urgent
        return claim_share >= self._claim_ratio and supported_share <= self._high_ratio_max


def _anonymous_signals() -> StudentSignals:
    return StudentSignals(
        alias="",
        requests=0,
        claimed_urgent=0,
        claimed_urgent_not_high=0,
        injection_attempts=0,
        gaming_suspected=False,
    )
