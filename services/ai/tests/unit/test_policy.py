"""P3.1: DefaultDecisionPolicy, table-driven over ARCHITECTURE §2.1 [7] rules a-f (14 cases)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.ports import DecisionPolicy
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    ClarificationBudget,
    EvidenceVector,
    GuardVerdict,
    Outcome,
    PredictionSet,
    ProbVector,
    Tier,
)

TAU_OOD = 0.40  # test value; production reads FrozenConfig.thresholds.tau_ood
ABOVE, BELOW = 0.75, 0.20
FRESH = ClarificationBudget(max_questions=1, asked=0)
SPENT = ClarificationBudget(max_questions=1, asked=1)


def _uniform(labels: tuple[str, ...]) -> ProbVector:
    return ProbVector(tuple(1.0 / len(labels) for _ in labels), labels)


def core(n_cat: int, n_pri: int, *, ood: float = ABOVE, flags: frozenset[str] = frozenset()) -> CoreResult:
    """A CoreResult whose only policy-relevant fields are the set sizes, OOD score and flags."""
    return CoreResult(
        p_cat=_uniform(CATEGORY_LABELS),
        p_pri=_uniform(PRIORITY_LABELS),
        per_model={},
        flags=flags,
        set_cat=PredictionSet(frozenset(CATEGORY_LABELS[:n_cat])),
        set_pri=PredictionSet(frozenset(PRIORITY_LABELS[:n_pri])),
        ood_score=ood,
        neighbors=(),
        evidence=EvidenceVector(flags={}),
        guard=GuardVerdict(kind="none"),
        safety=False,
        floors_applied=(),
        tier=Tier.TIER0,
        latency_ms=0,
        artifact=ArtifactVersion(name="v1", sha256="0" * 64),
    )


@dataclass(frozen=True)
class Case:
    id: str
    core: CoreResult
    budget: ClarificationBudget
    llm: bool
    expected: Outcome
    path: tuple[str, ...]
    after_escalation: bool = False


FULL = ("a_gibberish", "b_ood")
CASES = (
    Case(
        "a_gibberish",
        core(1, 1, flags=frozenset({"gibberish"})),
        FRESH,
        True,
        Outcome.OUT_OF_SCOPE,
        ("a_gibberish",),
    ),
    Case("b_ood_wide_set", core(3, 1, ood=BELOW), FRESH, True, Outcome.OUT_OF_SCOPE, FULL),
    Case(
        "c_accept_singletons_unknown_flag_ignored",
        core(1, 1, flags=frozenset({"not_a_real_flag"})),
        SPENT,
        False,
        Outcome.ACCEPT,
        (*FULL, "c_accept"),
    ),
    Case("d_ask_category_pair", core(2, 1), FRESH, True, Outcome.ASK, (*FULL, "c_accept", "d_ask")),
    Case("d_ask_priority_pair", core(1, 2), FRESH, False, Outcome.ASK, (*FULL, "c_accept", "d_ask")),
    Case(
        "e_escalate_pair_budget_spent",
        core(2, 1),
        SPENT,
        True,
        Outcome.ESCALATE,
        (*FULL, "c_accept", "d_ask", "e_escalate"),
    ),
    Case(
        "e_escalate_wide_set_in_distribution",
        core(4, 1),
        FRESH,
        True,
        Outcome.ESCALATE,
        (*FULL, "c_accept", "d_ask", "e_escalate"),
    ),
    Case(
        "f_human_pair_budget_spent_llm_off",
        core(2, 1),
        SPENT,
        False,
        Outcome.HUMAN_REVIEW,
        (*FULL, "c_accept", "d_ask", "e_escalate", "f_human"),
    ),
    Case(
        "empty_set_already_replaced_by_argmax_singleton",
        core(1, 1, flags=frozenset({"empty_set"})),
        FRESH,
        True,
        Outcome.ACCEPT,
        (*FULL, "c_accept"),
    ),
    Case(
        "gibberish_beats_ood",
        core(6, 3, ood=BELOW, flags=frozenset({"gibberish"})),
        FRESH,
        True,
        Outcome.OUT_OF_SCOPE,
        ("a_gibberish",),
    ),
    Case(
        "wide_set_ood_above_tau_llm_off",
        core(3, 1),
        FRESH,
        False,
        Outcome.HUMAN_REVIEW,
        (*FULL, "c_accept", "d_ask", "e_escalate", "f_human"),
    ),
    Case(
        "ood_below_tau_but_pair_is_not_out_of_scope",
        core(2, 1, ood=BELOW),
        FRESH,
        True,
        Outcome.ASK,
        (*FULL, "c_accept", "d_ask"),
    ),
    Case(
        "after_escalation_singletons_accept",
        core(1, 1),
        FRESH,
        True,
        Outcome.ACCEPT,
        ("c_accept",),
        after_escalation=True,
    ),
    Case(
        "after_escalation_still_ambiguous_never_asks",
        core(2, 2, ood=BELOW),
        FRESH,
        True,
        Outcome.HUMAN_REVIEW,
        ("c_accept", "f_human"),
        after_escalation=True,
    ),
)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_policy_table(case: Case) -> None:
    policy = DefaultDecisionPolicy(tau_ood=TAU_OOD)
    assert isinstance(policy, DecisionPolicy)
    outcome, path = policy.decide_with_path(
        case.core, case.budget, case.llm, after_escalation=case.after_escalation
    )
    assert outcome is case.expected
    assert path == case.path
    if not case.after_escalation:
        assert policy.decide(case.core, case.budget, case.llm) is case.expected
