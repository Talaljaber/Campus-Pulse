"""P3.10: ClarifyUseCase (ARCHITECTURE §2.1b, LD-29) with FakeCore."""

from __future__ import annotations

import pytest
from fixtures.backend_fakes import FakeCore, make_core
from fixtures.containers import BackendTestContainer, build_test

from campuspulse_ai.application.dto import ClarifyRequest, TriageRequest, TriageResponse
from campuspulse_ai.domain.errors import ClarificationBudgetExceeded, InvalidInput, NotFound
from campuspulse_ai.domain.values import ClarificationConstraint

TEXT = "my registration page is broken"
REG_OR_IT = make_core(
    {"Registration": 0.55, "IT Support": 0.4}, {"high": 0.9}, set_cat=["Registration", "IT Support"]
)
BOTH_AMBIGUOUS = make_core(
    {"Registration": 0.55, "IT Support": 0.4},
    {"medium": 0.5, "high": 0.45},
    set_cat=["Registration", "IT Support"],
    set_pri=["medium", "high"],
)


def start(core_result: object = REG_OR_IT, text: str = TEXT) -> tuple[BackendTestContainer, TriageResponse]:
    c = build_test(core=FakeCore().add(text, core_result))  # type: ignore[arg-type]
    r = c.triage.run(TriageRequest(text=text, student_alias="demo-17"))
    return c, r


def answer(
    c: BackendTestContainer,
    r: TriageResponse,
    option: str | None = None,
    text: str | None = None,
    question: str | None = None,
) -> TriageResponse:
    qid = question or (r.clarification.question_id if r.clarification else "")
    return c.clarify.run(r.request_id, ClarifyRequest(question_id=qid, option_id=option, free_text=text))


def test_registration_chip_decides_registration() -> None:
    c, r = start()
    done = answer(c, r, "registration")
    assert done.status == "decided" and done.category is not None
    assert (done.category.label, done.category.set) == ("Registration", ["Registration"])
    assert done.explanation is not None and done.explanation.trace.policy_path == ["d_ask", "c_accept"]
    assert done.explanation.trace.clarified is True
    assert c.core.calls[-1][2] == (ClarificationConstraint("category", "Registration"),)
    [q] = c.repo.clarifications_for(r.request_id)
    assert q.answer == "registration" and q.answered_at is not None


def test_not_sure_on_the_first_answer_allows_a_second_question() -> None:
    c, r = start(BOTH_AMBIGUOUS)
    assert r.clarification is not None and r.clarification.question_id == "cat:Registration|IT Support"
    second = answer(c, r, "not_sure")
    assert second.status == "needs_clarification" and second.clarification is not None
    assert second.clarification.question_id == "pri:deadline"


def test_after_two_answers_it_never_asks_again() -> None:
    c, r = start(BOTH_AMBIGUOUS)
    second = answer(c, r, "not_sure")
    final = answer(c, second, "yes_today")
    assert final.status == "human_review" and final.clarification is None
    assert final.priority is not None and final.priority.label == "high"
    assert final.explanation is not None and final.explanation.trace.policy_path == [
        "d_ask",
        "d_ask",
        "f_human",
    ]
    with pytest.raises(ClarificationBudgetExceeded):
        answer(c, final, "registration", question="cat:Registration|IT Support")


def test_a_definite_first_answer_spends_the_budget() -> None:
    c, r = start(BOTH_AMBIGUOUS)
    done = answer(c, r, "registration")  # priority still {medium, high}, but no second question
    assert (
        done.status == "human_review" and done.category is not None and done.category.label == "Registration"
    )


def test_free_text_reruns_normalisation_on_the_longer_text() -> None:
    c, r = start()
    answer(c, r, text="  I can't log in at all ")
    raw, _, constraints, _ = c.core.calls[-1]
    assert raw == f"{TEXT} I can't log in at all" and constraints == ()
    [q] = c.repo.clarifications_for(r.request_id)
    assert q.answer == "text:I can't log in at all"


def test_topic_chip_resolves_out_of_scope() -> None:
    c, r = start(make_core(flags=frozenset({"gibberish"})), "asdf qwer")
    assert r.status == "out_of_scope"
    done = answer(c, r, "Finance")
    assert done.status == "decided" and done.category is not None and done.category.label == "Finance"
    assert "gibberish" not in done.flags
    assert done.explanation is not None and done.explanation.trace.policy_path == ["a_gibberish", "c_accept"]


def test_errors() -> None:
    c, r = start()
    with pytest.raises(InvalidInput):
        answer(c, r, "registration", question="pri:deadline")
    with pytest.raises(NotFound):
        answer(c, r, "no_such_option")
    with pytest.raises(InvalidInput):
        answer(c, r, text="   ")
    with pytest.raises(NotFound):
        c.clarify.run("00000000-0000-4000-8000-000000000000", ClarifyRequest(question_id="x", option_id="y"))
    answer(c, r, "it")
    with pytest.raises(ClarificationBudgetExceeded):
        answer(c, r, "it", question="cat:Registration|IT Support")


def test_decided_after_clarification_still_acts() -> None:
    c, r = start()
    done = answer(c, r, "it")
    assert done.action is not None and done.action.ticket_id is not None
    assert c.sink.calls == [("create", done.action.ticket_id)]
    assert c.repo.get_request(r.request_id).status == "decided"
