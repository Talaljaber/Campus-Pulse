"""Expected-information-gain clarifier (SPEC §5.1 [8], ARCHITECTURE §2.1 [8], P3.2).

`InfoGainStrategy` implements the `ClarificationStrategy` port over a `QuestionBank`. It reads only the
probability vectors and prediction sets of a `CoreResult`, so it works with any conformal predictor.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from typing import Protocol

from campuspulse_ai.adapters.clarify.bank import BankQuestion, QuestionBank
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.values import (
    ClarificationConstraint,
    ClarificationQuestion,
    Lang,
    PredictionSet,
    ProbVector,
)

# Expected set sizes are compared after rounding away float noise, so equal scores tie exactly and
# the documented tie-break (category first, then bank order) decides. Not a tuned threshold.
_SCORE_DECIMALS = 9


class QuestionRephraser(Protocol):
    """Optional natural rephrasing of a bank question in the student's register (SPEC §5.1 [8]).

    It may change the wording only, never the question, its id or its options. The LLM rephraser is
    cut (B-list); `NullRephraser` is the default and returns the bank text.
    """

    def rephrase(self, question: ClarificationQuestion) -> ClarificationQuestion: ...


class NullRephraser:
    """Returns the bank question unchanged (offline default)."""

    def rephrase(self, question: ClarificationQuestion) -> ClarificationQuestion:
        return question


def _set_and_probs(core: CoreResult, question: BankQuestion) -> tuple[PredictionSet, ProbVector]:
    if question.target == "category":
        return core.set_cat, core.p_cat
    return core.set_pri, core.p_pri


def expected_set_size(core: CoreResult, question: BankQuestion) -> float:
    """Expected size of the target set after the student answers `question`.

    E = Σₒ P(o)·|S ∩ labels(o)| + (1 − Σₒ P(o))·|S|, where P(o) is the probability mass of the option's
    labels inside the current set S, renormalised over S. The last term charges the mass of S that no
    option covers (the set would stay as it is); it is zero when the split equals S, which gives the
    SPEC formula exactly. "Not sure" options have no labels and are not scored.
    """
    current, probs = _set_and_probs(core, question)
    labels = sorted(current.labels)
    mass = {lab: (probs.prob(lab) if lab in probs.labels else 0.0) for lab in labels}
    total = math.fsum(mass.values())
    if total <= 0.0:  # degenerate vector: fall back to a uniform belief over S
        mass = dict.fromkeys(labels, 1.0)
        total = float(len(labels))
    expected = 0.0
    covered = 0.0
    for opt in question.options:
        inside = opt.labels & current.labels
        if not inside:
            continue
        p_o = math.fsum(mass[lab] for lab in inside) / total
        covered += p_o
        expected += p_o * len(inside)
    return expected + max(0.0, 1.0 - covered) * current.size


class InfoGainStrategy:
    """Picks the bank question that minimises the expected prediction-set size (implements
    `ClarificationStrategy`).

    `select(core, lang, asked)`:
      - candidates are `bank.applicable(...)` (split ⊆ the target set, `when_category` matches the top
        category), minus the ids in `asked` (a question is never repeated);
      - if any category question is a candidate, only category questions are considered (category
        splits go first when both sets are ambiguous);
      - returns the argmin of `expected_set_size`, ties broken by bank order, rendered in `lang`
        (Arabizi gets the Arabic text), with `expected_info_gain = |S| − E` (expected labels removed);
      - returns None when no question applies. The use case then continues the policy as if the
        budget were spent.

    `apply(core, question_id, option_id)` returns the core with the answered set restricted (category
    or priority effect) and the constraint list. A feature effect (e.g. `deadline_today`) leaves the core
    untouched: the ClarifyUseCase re-runs `TriageCore.classify(..., constraints)` so the priority head
    sees it (LD-29). "Not sure" returns `(core, ())`. Raises NotFound for an unknown question or option
    (HTTP 404). No I/O.
    """

    def __init__(self, bank: QuestionBank, rephraser: QuestionRephraser | None = None) -> None:
        self._bank = bank
        self._rephraser: QuestionRephraser = rephraser or NullRephraser()

    @property
    def bank(self) -> QuestionBank:
        return self._bank

    def select(self, core: CoreResult, lang: Lang, asked: Sequence[str]) -> ClarificationQuestion | None:
        """The best question for `core` in `lang`, or None."""
        already = set(asked)
        candidates = [
            q
            for q in self._bank.applicable(core.set_cat, core.set_pri, top_category=core.p_cat.argmax())
            if q.id not in already
        ]
        if not candidates:
            return None
        category_first = [q for q in candidates if q.target == "category"]
        pool = category_first or candidates
        scored = [(round(expected_set_size(core, q), _SCORE_DECIMALS), i, q) for i, q in enumerate(pool)]
        size, _, best = min(scored, key=lambda t: (t[0], t[1]))
        current, _ = _set_and_probs(core, best)
        rendered = best.render(lang, expected_info_gain=current.size - size)
        return self._rephraser.rephrase(rendered)

    def apply(
        self, core: CoreResult, question_id: str, option_id: str
    ) -> tuple[CoreResult, Sequence[ClarificationConstraint]]:
        """Apply one answer; see the class docstring. Raises NotFound."""
        option = self._bank.get(question_id).option(option_id)
        effect = option.effect
        if effect is None:
            return core, ()
        if effect.kind == "category":
            return dataclasses.replace(core, set_cat=PredictionSet(frozenset({effect.value}))), (effect,)
        if effect.kind == "priority":
            return dataclasses.replace(core, set_pri=PredictionSet(frozenset({effect.value}))), (effect,)
        return core, (effect,)

    def topic_question(self, lang: Lang) -> ClarificationQuestion:
        """The out_of_scope topic chips (question id `topic`) in `lang`. Raises InvalidInput if the bank
        has no topic list."""
        if self._bank.topic is None:
            raise InvalidInput("the question bank has no `topic` list")
        return self._bank.topic.render(lang)
