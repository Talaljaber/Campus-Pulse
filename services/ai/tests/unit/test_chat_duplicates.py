"""One student, one issue, one ticket: a repeat or a follow-up never opens a second ticket."""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from fixtures.backend_fakes import make_core
from fixtures.chat import (
    Caller,
    ChatHarness,
    FakePreparer,
    ScriptedAgent,
    assistant,
    build_chat,
    says,
    turn_of,
    user,
)

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.chat import DuplicateOpenTicket
from campuspulse_ai.application.use_cases.issue_context import PreparedIssue
from campuspulse_ai.domain.journey import ticket_number
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.values import TicketStatus

FIRST = "e-learning is not working"
FOLLOW_UP = "I cannot log in to e-learning and I have an exam in one hour"
EVIDENCE = ("exam in one hour",)


def requesting(times: int = 4) -> ScriptedAgent:
    agent = ScriptedAgent(replies=[says("I will prepare a request.", "request") for _ in range(times)])
    agent.phrase_text = lambda facts: f"I can send this to {facts.department}. Shall I record it?"
    return agent


def open_first_ticket(t: ChatHarness, text: str = FIRST) -> str:
    """The student asks, confirms, and has one ticket (medium). Returns its id."""
    proposal = t.uc.turn(turn_of(user(text)), Caller()).proposal
    assert proposal is not None
    t.uc.confirm(dto.ChatConfirmRequest(proposal_token=proposal.token), Caller())
    [ticket] = t.tickets()
    return str(ticket["id"])


def follow_up(t: ChatHarness, text: str = FOLLOW_UP) -> dto.ChatTurnResponse:
    messages = (user(FIRST), assistant("Sent."), user(text))
    return t.uc.turn(turn_of(*messages), Caller())


def harness(preparer: FakePreparer | None = None) -> ChatHarness:
    return build_chat(agent=requesting(), preparer=preparer)


def test_a_follow_up_with_urgency_raises_the_existing_ticket_instead_of_opening_another() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    ticket_id = open_first_ticket(t)
    p.result = PreparedIssue(FOLLOW_UP, "high", EVIDENCE, ticket_number(ticket_id))
    later: list = []  # type: ignore[type-arg]
    r = t.uc.turn(turn_of(user(FIRST), assistant("Sent."), user(FOLLOW_UP)), Caller(), later)
    assert r.proposal is None and r.ticket_id is None and r.clear_proposal
    assert ticket_number(ticket_id) in r.reply and "raised" in r.reply and "high" in r.reply
    [ticket] = t.tickets()
    assert str(ticket["priority"]) == "high"
    assert any(a.kind == "priority" and a.to_priority == "high" for a in t.h.journey.activity_for(ticket_id))


def test_the_same_issue_at_the_same_priority_only_tells_the_student_it_is_open() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    ticket_id = open_first_ticket(t)
    p.result = PreparedIssue("e-learning does not work for me", None, (), ticket_number(ticket_id))
    r = follow_up(t, "still not working")
    assert r.proposal is None and "already have an open request" in r.reply
    assert ticket_number(ticket_id) in r.reply and "I did not open another one" in r.reply
    [ticket] = t.tickets()
    assert str(ticket["priority"]) == "medium"


def test_a_ticket_that_is_in_progress_is_raised_too() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    ticket_id = open_first_ticket(t)
    ticket = t.c.repo.get_ticket(ticket_id)
    t.c.repo.save_ticket(dataclasses.replace(ticket, status=TicketStatus.IN_PROGRESS))
    p.result = PreparedIssue(FOLLOW_UP, "high", EVIDENCE, ticket_number(ticket_id))
    r = follow_up(t)
    assert "raised" in r.reply
    assert t.c.repo.get_ticket(ticket_id).priority == Priority.HIGH and len(t.tickets()) == 1


def test_the_same_words_are_a_repeat_even_without_the_preparer() -> None:
    t = harness(None)
    ticket_id = open_first_ticket(t)
    r = t.uc.turn(turn_of(user("E-learning is NOT working!")), Caller())
    assert r.proposal is None and ticket_number(ticket_id) in r.reply and len(t.tickets()) == 1


def test_a_different_kind_of_problem_is_a_new_request_even_if_the_preparer_says_repeat() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    ticket_id = open_first_ticket(t)
    t.core.add("I need a copy of my payment receipt", make_core({"Finance": 0.9}, {"medium": 0.9}))
    p.result = PreparedIssue("I need a copy of my payment receipt", None, (), ticket_number(ticket_id))
    r = follow_up(t, "I need a copy of my payment receipt")
    assert r.proposal is not None and r.proposal.category == "Finance"


def test_an_unknown_ticket_number_from_the_preparer_is_ignored() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    open_first_ticket(t)
    p.result = PreparedIssue("my laptop will not start", None, (), "DEADBEEF")
    assert follow_up(t, "my laptop will not start").proposal is not None


def test_another_students_ticket_is_never_a_repeat() -> None:
    t = harness(None)
    open_first_ticket(t)
    t.c.repo.add_profile("demo-99", "student", display_name="Omar Nasser")
    r = t.uc.turn(turn_of(user(FIRST)), Caller(alias="demo-99"))
    assert r.proposal is not None


@pytest.mark.parametrize("status", [TicketStatus.SOLVED, TicketStatus.CLOSED])
def test_a_finished_ticket_does_not_block_a_new_one(status: TicketStatus) -> None:
    t = harness(None)
    ticket_id = open_first_ticket(t)
    t.c.repo.save_ticket(dataclasses.replace(t.c.repo.get_ticket(ticket_id), status=status))
    assert t.uc.turn(turn_of(user(FIRST)), Caller()).proposal is not None


def test_the_preparer_is_shown_the_students_open_tickets() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    ticket_id = open_first_ticket(t)
    follow_up(t)
    seen = p.open_seen[-1]
    assert [(o.number, o.priority, o.status) for o in seen] == [(ticket_number(ticket_id), "medium", "new")]
    assert FIRST in seen[0].text


def test_a_second_confirmation_of_the_same_text_opens_no_second_ticket() -> None:
    t = harness(None)
    first = t.uc.turn(turn_of(user(FIRST)), Caller()).proposal
    t.c.clock.at += timedelta(seconds=5)  # a later proposal carries its own expiry, so its own token
    second = t.uc.turn(turn_of(user(FIRST)), Caller()).proposal
    assert first is not None and second is not None and first.token != second.token
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=first.token), Caller())
    with pytest.raises(DuplicateOpenTicket, match="already have an open request"):
        t.uc.confirm(dto.ChatConfirmRequest(proposal_token=second.token), Caller())
    assert len(t.tickets()) == 1
    again = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=first.token), Caller())
    assert again == done and len(t.tickets()) == 1


def test_confirming_a_repeat_in_the_chat_answers_with_the_open_ticket() -> None:
    agent = requesting(2)
    agent.replies.append(says("Done.", "confirm"))
    t = build_chat(agent=agent)
    first = t.uc.turn(turn_of(user(FIRST)), Caller()).proposal
    t.c.clock.at += timedelta(seconds=5)
    second = t.uc.turn(turn_of(user(FIRST)), Caller()).proposal
    assert first is not None and second is not None and first.token != second.token
    t.uc.confirm(dto.ChatConfirmRequest(proposal_token=first.token), Caller())
    history = (user(FIRST), assistant("..", "proposal"), user("yes"))
    r = t.uc.turn(turn_of(*history, token=second.token), Caller())
    assert r.ticket_id is None and r.clear_proposal and "already have an open request" in r.reply
    assert len(t.tickets()) == 1


def test_arabic_replies_use_the_arabic_wording() -> None:
    p = FakePreparer(PreparedIssue(FIRST, None, ()))
    t = harness(p)
    ticket_id = open_first_ticket(t)
    p.result = PreparedIssue(FOLLOW_UP, "high", EVIDENCE, ticket_number(ticket_id))
    messages = (user("الايلرنينق مش شغال"), assistant("تمام"), user("عندي امتحان بعد ساعة"))
    r = t.uc.turn(turn_of(*messages), Caller())
    assert "رفعت أولويته" in r.reply and "عالية" in r.reply and ticket_number(ticket_id) in r.reply
