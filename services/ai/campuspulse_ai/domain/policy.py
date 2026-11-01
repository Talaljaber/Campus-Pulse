"""Pure domain policies.

- `RecipientPolicy`: the demo allow-list. Used by AllowlistedNotifier and booking attendees.
- `DefaultDecisionPolicy` (P3.1): ACCEPT / ASK / ESCALATE / HUMAN_REVIEW / OUT_OF_SCOPE / DISTRESS.
"""

from __future__ import annotations

import math

from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import RecipientNotAllowed
from campuspulse_ai.domain.values import ClarificationBudget, Outcome

# Rule ids, in evaluation order (ARCHITECTURE §2.1 [7] a-f). They go into explanation.trace.policy_path.
RULE_GIBBERISH = "a_gibberish"
RULE_OOD = "b_ood"
RULE_INJECTION = "b1_injection"
RULE_EMPTY = "b2_empty"
RULE_FAR = "b3_far_singleton"
RULE_ACCEPT = "c_accept"
RULE_ASK = "d_ask"
RULE_ESCALATE = "e_escalate"
RULE_HUMAN = "f_human"
POLICY_RULES: tuple[str, ...] = (
    RULE_GIBBERISH, RULE_OOD, RULE_INJECTION, RULE_EMPTY, RULE_FAR, RULE_ACCEPT, RULE_ASK, RULE_ESCALATE,
    RULE_HUMAN,
)
# P7.9: a singleton set on a request this far below the OOD threshold is not evidence (an off-topic text
# with an accidentally confident model). A hand-set rule parameter, not a learned threshold.
FAR_OOD_MARGIN = 0.03

# Set sizes are the rule structure of SPEC §5.1 [7], not tuned thresholds.
_SINGLETON = 1
_PAIR = 2
_WIDE = 3


class DefaultDecisionPolicy:
    """The deterministic decision policy (SPEC §5.1 [7], ARCHITECTURE §2.1 [7]); implements `DecisionPolicy`.

    Rules, first match wins:
      a. flag `gibberish` or `too_vague` (P7.9)                    -> OUT_OF_SCOPE
      b. `ood_score < tau_ood` and |S_cat| >= 3                    -> OUT_OF_SCOPE
      b1. flag `injection_attempt` (P7.9: never auto-answered)     -> HUMAN_REVIEW
      b2. flag `empty_set` (no label reached the conformal threshold) -> HUMAN_REVIEW
      b3. both sets singletons and `ood_score < tau_ood - 0.03` (P7.9) -> HUMAN_REVIEW
      c. |S_cat| == 1 and |S_pri| == 1                             -> ACCEPT
      d. (|S_cat| == 2 or |S_pri| == 2) and budget left            -> ASK
      e. llm_allowed and (|S_cat| >= 2 or |S_pri| >= 2)            -> ESCALATE
      f. otherwise                                                -> HUMAN_REVIEW (argmax + needs_review)

    After an escalation (`after_escalation=True`) only b2, c and f are evaluated (§2.1 [7e]).

    Reads only `core.flags`, `core.ood_score`, `core.set_cat` and `core.set_pri`. Pure: no I/O, no
    errors; unknown flags are ignored. Distress is not a policy outcome: the use case handles it before
    the policy runs (§2.1 [4']). The core replaces an empty conformal set with the argmax
    singleton and flag `empty_set` (labels unchanged); rule b2 routes that to review, since a singleton
    built from nothing is not evidence (P7.1).

    `tau_ood` comes from `FrozenConfig.thresholds.tau_ood` (wired in the composition root).
    """

    def __init__(self, tau_ood: float, far_ood_margin: float = FAR_OOD_MARGIN) -> None:
        if not math.isfinite(tau_ood):
            raise ValueError(f"tau_ood must be a finite number, got {tau_ood!r}")
        if not math.isfinite(far_ood_margin) or far_ood_margin < 0:
            raise ValueError(f"far_ood_margin must be a finite number >= 0, got {far_ood_margin!r}")
        self._tau_ood = tau_ood
        self._margin = far_ood_margin

    @property
    def tau_ood(self) -> float:
        """The OOD threshold this policy was built with."""
        return self._tau_ood

    def decide(self, core: CoreResult, budget: ClarificationBudget, llm_allowed: bool) -> Outcome:
        """The outcome for `core` (see the class docstring)."""
        return self.decide_with_path(core, budget, llm_allowed)[0]

    def decide_with_path(
        self,
        core: CoreResult,
        budget: ClarificationBudget,
        llm_allowed: bool,
        *,
        after_escalation: bool = False,
    ) -> tuple[Outcome, tuple[str, ...]]:
        """The outcome plus the rule ids evaluated, in order; the last id is the rule that fired.

        Use cases append that last id to `explanation.trace.policy_path` at each evaluation, so a
        clarified request reads `("d_ask", "c_accept")`.
        """
        n_cat = core.set_cat.size
        n_pri = core.set_pri.size
        ambiguous = n_cat >= _PAIR or n_pri >= _PAIR
        path: list[str] = []

        if not after_escalation:
            path.append(RULE_GIBBERISH)
            if "gibberish" in core.flags or "too_vague" in core.flags:
                return Outcome.OUT_OF_SCOPE, tuple(path)
            path.append(RULE_OOD)
            if core.ood_score < self._tau_ood and n_cat >= _WIDE:
                return Outcome.OUT_OF_SCOPE, tuple(path)

        # b1 and b3 are recorded in the path only when they fire (older traces keep their shape)
        if "injection_attempt" in core.flags:
            return Outcome.HUMAN_REVIEW, (*path, RULE_INJECTION)

        path.append(RULE_EMPTY)
        if "empty_set" in core.flags:
            return Outcome.HUMAN_REVIEW, tuple(path)

        if n_cat == _SINGLETON and n_pri == _SINGLETON and core.ood_score < self._tau_ood - self._margin:
            return Outcome.HUMAN_REVIEW, (*path, RULE_FAR)

        path.append(RULE_ACCEPT)
        if n_cat == _SINGLETON and n_pri == _SINGLETON:
            return Outcome.ACCEPT, tuple(path)

        if not after_escalation:
            path.append(RULE_ASK)
            if (n_cat == _PAIR or n_pri == _PAIR) and budget.remaining > 0:
                return Outcome.ASK, tuple(path)
            path.append(RULE_ESCALATE)
            if llm_allowed and ambiguous:
                return Outcome.ESCALATE, tuple(path)

        path.append(RULE_HUMAN)
        return Outcome.HUMAN_REVIEW, tuple(path)


class RecipientPolicy:
    """Allow-list check for every outgoing address. An empty allow-list rejects everything."""

    def __init__(self, allowlist: frozenset[str]) -> None:
        self._allowed = frozenset(self._canonical(a) for a in allowlist if a.strip())

    @staticmethod
    def _canonical(address: str) -> str:
        return address.strip().lower()

    def check(self, address: str) -> None:
        """Raise RecipientNotAllowed unless `address` is on the allow-list."""
        if self._canonical(address) not in self._allowed:
            raise RecipientNotAllowed(f"recipient not in DEMO allow-list: {address!r}")
