"""ClarifyUseCase: the answer to a clarifying question (ARCHITECTURE §2.1b, P3.10, LD-29)."""

from __future__ import annotations

from collections.abc import Sequence

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.ports import TriageClassifier
from campuspulse_ai.application.use_cases.triage import (
    DEFAULT_MAX_QUESTIONS,
    GIBBERISH,
    MAX_QUESTIONS_IF_UNSURE,
    DecisionFlow,
    with_flags,
)
from campuspulse_ai.domain.entities import Clarification
from campuspulse_ai.domain.errors import ClarificationBudgetExceeded, InvalidInput, NotFound
from campuspulse_ai.domain.policy import RULE_ASK, RULE_GIBBERISH, RULE_OOD
from campuspulse_ai.domain.ports import Clock, Repository
from campuspulse_ai.domain.values import ClarificationBudget, ClarificationConstraint, Location

TOPIC_QUESTION_ID = "topic"
"""The out_of_scope chip list (LD-36; `adapters/clarify/bank.TOPIC_QUESTION_ID`)."""
FREE_TEXT_PREFIX = "text:"
"""A free-text answer is stored in `clarifications.answer` as `text:<the text>`."""


class ClarifyUseCase:
    """`POST /v1/triage/{request_id}/clarify`: apply one answer and continue the decision from [7].

    `run(request_id, cmd)`:
    1. Load the request and its questions. The pending question is the last unanswered one.
    2. An option answer must be one of the pending question's saved options; it is stored and the
       constraints of **every** answer so far are collected (category/priority fix that set, a feature
       sets evidence for the priority head). A free-text answer is stored as `text:<text>` and appended
       to the request text, so normalization and the guards run again.
    3. The core is re-run: `classify(raw + free texts, picked location, constraints)` (LD-29). After a
       topic chip (out_of_scope) the `gibberish` flag is dropped: the student named the topic.
    4. Budget: one question, or two when the first answer was "not sure" (SPEC §5.1 [8]); every
       answered question counts, so after the budget the policy never asks again.
    5. `DecisionFlow.run(..., clarified=True)` with `policy_path` starting with the rule of each
       earlier question (`d_ask`, or `a_gibberish` / `b_ood` for the topic chips).

    Errors: `NotFound` (unknown request or option, 404); `ClarificationBudgetExceeded` when no question
    is pending, e.g. a third answer (409); `InvalidInput` when `question_id` is not the pending
    question or the free text is blank (422). Everything after step 3 is as in `DecisionFlow`.
    """

    def __init__(
        self,
        core: TriageClassifier,
        flow: DecisionFlow,
        repo: Repository,
        clock: Clock,
        *,
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        max_if_unsure: int = MAX_QUESTIONS_IF_UNSURE,
    ) -> None:
        self._core = core
        self._flow = flow
        self._repo = repo
        self._clock = clock
        self._max = max_questions
        self._max_if_unsure = max_if_unsure

    def run(
        self, request_id: str, cmd: dto.ClarifyRequest, *, debug_members: bool = False
    ) -> dto.TriageResponse:
        request = self._repo.get_request(request_id)
        history = self._repo.clarifications_for(request_id)
        pending = [c for c in history if c.answer is None]
        if not pending:
            raise ClarificationBudgetExceeded(f"no question is pending for request {request_id}")
        current = pending[-1]
        if cmd.question_id != current.question_id:
            raise InvalidInput(
                f"question {cmd.question_id!r} is not the pending question {current.question_id!r}"
            )
        answered = [c for c in history if c.answer is not None]
        if len(answered) >= self._max_if_unsure:
            raise ClarificationBudgetExceeded(f"request {request_id} already used its questions")

        current.answer = self._answer(current, cmd)
        current.answered_at = self._clock.now()
        self._repo.save_clarification(current)
        done = [*answered, current]

        constraints = _constraints(done)
        free_texts = [(c.answer or "").removeprefix(FREE_TEXT_PREFIX) for c in done if _is_free(c)]
        raw = " ".join([request.raw_text, *free_texts])
        normalized = request.normalized
        picked: Location | None = (
            normalized.location
            if normalized and normalized.location and normalized.location.source == "picked"
            else None
        )
        req, core = self._core.classify(raw, picked, constraints)

        path: list[str] = []
        for c in done:
            if c.question_id == TOPIC_QUESTION_ID:
                path.append(RULE_GIBBERISH if GIBBERISH in core.flags else RULE_OOD)
            else:
                path.append(RULE_ASK)
        if any(c.question_id == TOPIC_QUESTION_ID for c in done):
            core = with_flags(core, frozenset({GIBBERISH}))

        budget = ClarificationBudget(max_questions=self._budget_max(done), asked=len(done))
        return self._flow.run(
            request,
            req,
            core,
            budget=budget,
            asked=[c.question_id for c in history],
            path=path,
            clarified=True,
            debug_members=debug_members,
        )

    def _answer(self, question: Clarification, cmd: dto.ClarifyRequest) -> str:
        if cmd.option_id is not None:
            if not any(o.id == cmd.option_id for o in question.options):
                raise NotFound(f"unknown option {cmd.option_id!r} for question {question.question_id!r}")
            return cmd.option_id
        text = (cmd.free_text or "").strip()
        if not text:
            raise InvalidInput("free_text is blank")
        return f"{FREE_TEXT_PREFIX}{text}"

    def _budget_max(self, done: Sequence[Clarification]) -> int:
        """Two questions when the first real (non-topic) answer was "not sure", else one."""
        first = next((c for c in done if c.question_id != TOPIC_QUESTION_ID), None)
        if first is None or _is_free(first):
            return self._max
        option = next((o for o in first.options if o.id == first.answer), None)
        return self._max_if_unsure if option is not None and option.constraint is None else self._max


def _is_free(c: Clarification) -> bool:
    return c.answer is not None and c.answer.startswith(FREE_TEXT_PREFIX)


def _constraints(done: Sequence[Clarification]) -> list[ClarificationConstraint]:
    out: list[ClarificationConstraint] = []
    for c in done:
        for option in c.options:
            if option.id == c.answer and option.constraint is not None and option.constraint not in out:
                out.append(option.constraint)
    return out
