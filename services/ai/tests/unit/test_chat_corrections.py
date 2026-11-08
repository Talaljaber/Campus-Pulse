"""P10.18: status cards, corrections (replace or keep both), closing a request, from the chat.

The agent's `ticket_refs` are only hints: every test that names someone else's ticket checks that it is
never shown, replaced or closed. The H302 -> H203 conversation runs end to end with the fakes."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from fixtures.chat import (
    KEY,
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
from campuspulse_ai.application.use_cases.chat_ports import AgentReply, Intent
from campuspulse_ai.application.use_cases.issue_context import PreparedIssue
from campuspulse_ai.application.use_cases.proposals import ProposalClaims, sign, verify
from campuspulse_ai.domain.journey import ticket_number
from campuspulse_ai.domain.values import TicketStatus

WRONG = "The projector in room H302 is broken"
RIGHT = "The projector in room H203 is broken"
FIX = "Sorry, I meant H203, not H302"
OTHER = "demo-99"


def agent_says(text: str, intent: Intent, refs: tuple[str, ...] = (), corrected: str = "") -> AgentReply:
    return AgentReply(reply=text, intent=intent, ticket_refs=refs, corrected_text=corrected)


def harness(*replies: AgentReply, preparer: FakePreparer | None = None) -> ChatHarness:
    agent = ScriptedAgent(replies=list(replies))
    agent.phrase_text = lambda facts: f"I can send this to {facts.department}. Shall I record it?"
    t = build_chat(agent=agent, preparer=preparer)
    t.c.repo.add_profile(OTHER, "student", display_name="Omar Nasser")
    return t


def open_ticket(t: ChatHarness, text: str, alias: str | None = None) -> str:
    """A ticket opened through the plain form path (preview + confirm). Returns its id."""
    caller = Caller(alias=alias) if alias else Caller()
    proposal = t.uc.preview(dto.ChatPreviewRequest(text=text), caller)
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=proposal.token), caller)
    assert done.ticket_id is not None
    t.c.clock.at += timedelta(seconds=5)
    return done.ticket_id


def status_of(t: ChatHarness, ticket_id: str) -> TicketStatus:
    return t.c.repo.get_ticket(ticket_id).status


def thread(t: ChatHarness, ticket_id: str) -> list[tuple[str, str]]:
    return [(a.kind, a.body) for a in t.h.journey.activity_for(ticket_id)]


def correct_turn(
    t: ChatHarness, old_id: str, *, messages: tuple[dto.ChatMessage, ...] | None = None
) -> dto.ChatTurnResponse:
    t.agent.replies.append(  # type: ignore[union-attr]
        agent_says("Thanks for the fix.", "correct", (ticket_number(old_id),), RIGHT)
    )
    return t.uc.turn(turn_of(*(messages or (user(FIX),))), Caller())


# --------------------------------------------------------------------------- status


def test_status_shows_cards_for_every_own_ticket_and_keeps_clean_model_words() -> None:
    t = harness(agent_says("Both of your requests were received.", "status"))
    a = open_ticket(t, WRONG)
    b = open_ticket(t, "My e-learning account is locked")
    r = t.uc.turn(turn_of(user("what's the status of my requests?")), Caller())
    assert r.reply == "Both of your requests were received."
    assert [c.ticket_id for c in r.tickets] == [b, a]  # newest first
    card = r.tickets[1]
    assert card.number == ticket_number(a) and card.status == "new" and card.office == "it"
    assert r.proposal is None and r.withdraw is None and r.correction is None


def test_status_with_a_ref_shows_only_that_ticket() -> None:
    t = harness()
    a = open_ticket(t, WRONG)
    open_ticket(t, "My e-learning account is locked")
    t.agent.replies.append(agent_says("x", "status", (f"#{ticket_number(a).lower()}",)))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user("how is my projector request going?")), Caller())
    assert [c.ticket_id for c in r.tickets] == [a]


def test_status_never_shows_another_persons_ticket() -> None:
    t = harness()
    mine = open_ticket(t, WRONG)
    theirs = open_ticket(t, "My parking permit is missing", alias=OTHER)
    ref = ticket_number(theirs)
    t.agent.replies.append(agent_says(f"Request #{ref} is solved.", "status", (ref,)))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user(f"status of #{ref}?")), Caller())
    assert [c.ticket_id for c in r.tickets] == [mine]
    assert ref not in r.reply and r.reply == "Here is where your requests stand."  # template, not the claim


def test_status_without_tickets_and_the_30_day_window() -> None:
    t = harness(agent_says("x", "status"), agent_says("x", "status"))
    assert t.uc.turn(turn_of(user("status?")), Caller()).reply.startswith("You have no requests")
    old = open_ticket(t, WRONG)
    ticket = t.c.repo.get_ticket(old)
    t.c.repo.save_ticket(
        dataclasses.replace(ticket, status=TicketStatus.CLOSED, resolved_at=t.c.clock.at - timedelta(days=40))
    )
    assert t.uc.turn(turn_of(user("status?")), Caller()).tickets == []


def test_the_agent_sees_the_persons_requests_as_data() -> None:
    t = harness(says("Hi", "chat"))
    a = open_ticket(t, WRONG)
    open_ticket(t, "My parking permit is missing", alias=OTHER)
    t.uc.turn(turn_of(user("hello")), Caller())
    ctx = t.agent.reply_calls[-1][0]  # type: ignore[union-attr]
    [line] = ctx.requests
    assert line.startswith(f"#{ticket_number(a)} | status: new | office: IT Support | created: ")
    assert line.endswith(f"text: {WRONG}")


# --------------------------------------------------------------------------- withdraw


def test_withdraw_asks_to_close_an_own_open_ticket_and_closes_nothing() -> None:
    t = harness()
    a = open_ticket(t, WRONG)
    t.agent.replies.append(agent_says("I closed it.", "withdraw", (ticket_number(a),)))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user("please cancel my projector request")), Caller())
    assert r.withdraw is not None and r.withdraw.ticket_id == a
    assert r.reply == f"Close request #{ticket_number(a)}? Nothing is closed until you confirm."
    assert status_of(t, a) == TicketStatus.NEW


def test_withdraw_of_someone_elses_or_a_closed_ticket_offers_the_own_open_ones() -> None:
    t = harness()
    mine = open_ticket(t, WRONG)
    done = open_ticket(t, "My e-learning account is locked")
    t.c.repo.save_ticket(
        dataclasses.replace(t.c.repo.get_ticket(done), status=TicketStatus.CLOSED, resolved_at=t.c.clock.at)
    )
    theirs = open_ticket(t, "My parking permit is missing", alias=OTHER)
    for ref in (theirs, done):
        t.agent.replies.append(agent_says("x", "withdraw", (ticket_number(ref),)))  # type: ignore[union-attr]
        r = t.uc.turn(turn_of(user("cancel it")), Caller())
        assert r.withdraw is None and [c.ticket_id for c in r.tickets] == [mine]
        assert r.reply == "Which request do you want to close? Pick it below."
    assert status_of(t, theirs) == TicketStatus.NEW


def test_withdraw_without_open_tickets() -> None:
    t = harness(agent_says("x", "withdraw"))
    r = t.uc.turn(turn_of(user("cancel my request")), Caller())
    assert r.reply == "You have no open requests to close." and r.withdraw is None


# --------------------------------------------------------------------------- correct, replace, separate


def test_h302_to_h203_end_to_end_in_the_chat() -> None:
    """The real bug: H302 recorded, H203 meant. The assistant asks, the student says yes, the wrong ticket
    is closed with a comment and the corrected one is open."""
    t = harness(says("I will prepare a request.", "request"), says("Okay.", "confirm"))
    first = t.uc.turn(turn_of(user(WRONG)), Caller())
    assert first.proposal is not None
    history = (user(WRONG), assistant("Shall I?", "proposal"), user("yes"))
    recorded = t.uc.turn(turn_of(*history, token=first.proposal.token), Caller())
    old = recorded.ticket_id
    assert old is not None and status_of(t, old) == TicketStatus.NEW

    later = (*history, assistant(recorded.reply, "ticket"), user(FIX))
    r = correct_turn(t, old, messages=later)
    assert r.proposal is not None and r.correction is not None
    assert r.proposal.text == RIGHT and r.correction.ticket.ticket_id == old
    assert r.correction.old_text == WRONG
    number = ticket_number(old)
    assert r.reply.startswith(f"Did you mean to fix request #{number}?") and "keep both" in r.reply
    assert verify(KEY, r.proposal.token, Caller().alias or "", t.c.clock.now()).replaces == old
    assert len(t.tickets()) == 1  # nothing recorded or closed yet

    t.agent.replies.append(says("Done, closed and recorded!", "confirm"))  # type: ignore[union-attr]
    yes = (*later, assistant(r.reply, "proposal"), user("yes"))
    done = t.uc.turn(turn_of(*yes, token=r.proposal.token), Caller())
    new = done.ticket_id
    assert new is not None and new != old and done.clear_proposal
    assert status_of(t, old) == TicketStatus.CLOSED and status_of(t, new) == TicketStatus.NEW
    assert done.reply == (
        f"Request recorded: #{ticket_number(new)} for IT Support (demo, no real department was contacted). "
        f"Request #{number} is closed."
    )
    [closed] = done.tickets
    assert closed.ticket_id == old and closed.status == "closed" and closed.resolved_at is not None
    comment = f"Closed by the requester: replaced by #{ticket_number(new)} (corrected details)."
    assert ("comment", comment) in thread(t, old)
    assert [k for k, _ in thread(t, old)][-2:] == ["comment", "student_action"]


def test_confirm_endpoint_with_replace_true_fills_closed_ticket() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    proposal = correct_turn(t, old).proposal
    assert proposal is not None
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=proposal.token, replace=True), Caller())
    assert done.closed_ticket is not None and done.closed_ticket.ticket_id == old
    assert status_of(t, old) == TicketStatus.CLOSED and done.ticket_id is not None
    assert status_of(t, done.ticket_id) == TicketStatus.NEW


def test_replace_false_keeps_both() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    proposal = correct_turn(t, old).proposal
    assert proposal is not None
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=proposal.token), Caller())
    assert done.closed_ticket is None and status_of(t, old) == TicketStatus.NEW
    assert len(t.tickets()) == 2


def test_separate_in_the_chat_keeps_both() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    proposal = correct_turn(t, old).proposal
    assert proposal is not None
    t.agent.replies.append(agent_says("Okay, both.", "separate", (ticket_number(old),)))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user(FIX), user("no, it is a different projector"), token=proposal.token), Caller())
    assert r.ticket_id is not None and r.tickets == [] and r.clear_proposal
    assert status_of(t, old) == TicketStatus.NEW and status_of(t, r.ticket_id) == TicketStatus.NEW
    assert "is closed" not in r.reply


def test_separate_without_a_pending_correction_is_an_ordinary_request() -> None:
    t = harness(agent_says("x", "separate"))
    r = t.uc.turn(turn_of(user(RIGHT)), Caller())
    assert r.proposal is not None and r.correction is None and t.tickets() == []


def test_replace_true_is_ignored_without_the_replaces_claim() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    proposal = t.uc.preview(dto.ChatPreviewRequest(text=RIGHT), Caller())
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=proposal.token, replace=True), Caller())
    assert done.closed_ticket is None and status_of(t, old) == TicketStatus.NEW


def test_replace_does_not_close_a_ticket_that_is_no_longer_open() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    proposal = correct_turn(t, old).proposal
    assert proposal is not None
    t.c.repo.save_ticket(dataclasses.replace(t.c.repo.get_ticket(old), status=TicketStatus.SOLVED))
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=proposal.token, replace=True), Caller())
    assert done.closed_ticket is None and status_of(t, old) == TicketStatus.SOLVED
    assert done.ticket_id is not None  # the corrected request is still recorded
    assert not any(k == "comment" for k, _ in thread(t, old))


def test_replace_never_closes_another_persons_ticket_even_in_a_signed_token() -> None:
    t = harness()
    theirs = open_ticket(t, WRONG, alias=OTHER)
    exp = int(t.c.clock.now().timestamp()) + 600
    claims = ProposalClaims(Caller().alias or "", RIGHT, "IT Support", "medium", "it", None, exp, theirs)
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=sign(KEY, claims), replace=True), Caller())
    assert done.ticket_id is not None and done.closed_ticket is None
    assert status_of(t, theirs) == TicketStatus.NEW and thread(t, theirs) == []


def test_correct_with_a_ref_to_someone_elses_ticket_is_an_ordinary_request() -> None:
    t = harness()
    theirs = open_ticket(t, WRONG, alias=OTHER)
    t.agent.replies.append(agent_says("x", "correct", (ticket_number(theirs),), RIGHT))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user(RIGHT)), Caller())
    assert r.proposal is not None and r.correction is None
    assert verify(KEY, r.proposal.token, Caller().alias or "", t.c.clock.now()).replaces is None


def test_correct_without_corrected_text_uses_the_old_text_with_the_new_room() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    t.agent.replies.append(agent_says("x", "correct", (ticket_number(old),)))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user(FIX)), Caller())
    assert r.proposal is not None and r.proposal.text == RIGHT


def test_a_correction_with_the_same_words_is_only_a_repeat() -> None:
    t = harness()
    old = open_ticket(t, WRONG)
    t.agent.replies.append(agent_says("x", "correct", (ticket_number(old),), WRONG))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user(WRONG)), Caller())
    assert r.proposal is None and "already have an open request" in r.reply


def test_a_repeat_in_another_room_becomes_a_correction_not_a_comment() -> None:
    """The preparer says "this is about the open ticket", but the room differs: ask, do not comment."""
    p = FakePreparer(PreparedIssue(WRONG, None, ()))
    t = harness(preparer=p)
    old = open_ticket(t, WRONG)
    p.result = PreparedIssue(RIGHT, None, (), ticket_number(old))
    t.agent.replies.append(says("I will prepare a request.", "request"))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user("The projector in H203 is broken")), Caller())
    assert r.correction is not None and r.correction.ticket.ticket_id == old
    assert r.proposal is not None and r.proposal.text == RIGHT
    assert thread(t, old) == []  # no follow-up comment on the wrong ticket


def test_the_same_room_is_still_a_plain_follow_up() -> None:
    p = FakePreparer(PreparedIssue(WRONG, None, ()))
    t = harness(preparer=p)
    old = open_ticket(t, WRONG)
    p.result = PreparedIssue(WRONG, None, (), ticket_number(old))
    t.agent.replies.append(says("x", "request"))  # type: ignore[union-attr]
    r = t.uc.turn(turn_of(user("the H302 projector is still broken")), Caller())
    assert r.correction is None and r.proposal is None and "already have an open request" in r.reply


def test_arabic_correction_and_replace_use_the_arabic_templates() -> None:
    t = harness()
    old = open_ticket(t, "البروجكتر بقاعة H302 خربان")
    number = ticket_number(old)
    t.agent.replies.append(  # type: ignore[union-attr]
        agent_says("x", "correct", (number,), "البروجكتر بقاعة H203 خربان")
    )
    r = t.uc.turn(turn_of(user("غلطت، البروجكتر بقاعة H203 مش H302")), Caller())
    assert r.proposal is not None and r.reply.startswith(f"قصدك تصلّح الطلب رقم #{number}؟")
    t.agent.replies.append(says("تمام", "confirm"))  # type: ignore[union-attr]
    said = user("غلطت، البروجكتر بقاعة H203 مش H302")
    done = t.uc.turn(turn_of(said, user("اه"), token=r.proposal.token), Caller())
    assert done.reply.endswith(f"الطلب رقم #{number} تسكّر.") and status_of(t, old) == TicketStatus.CLOSED


# --------------------------------------------------------------------------- tokens and claims


def _old_format_token(claims: ProposalClaims) -> str:
    """A token exactly as `sign` wrote it before P10.18 (seven fields, no `replaces`)."""
    names = ("alias", "text", "category", "priority", "office", "hint_id", "exp")
    body = json.dumps({n: getattr(claims, n) for n in names}, sort_keys=True, separators=(",", ":"))
    payload = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{payload}.{hmac.new(KEY, payload.encode('ascii'), hashlib.sha256).hexdigest()}"


def test_tokens_signed_before_p10_18_still_verify_and_confirm() -> None:
    t = harness()
    exp = int(t.c.clock.now().timestamp()) + 600
    claims = ProposalClaims(Caller().alias or "", RIGHT, "IT Support", "medium", "it", None, exp)
    token = _old_format_token(claims)
    assert sign(KEY, claims) == token  # no `replaces`: the very same bytes as before
    assert verify(KEY, token, Caller().alias or "", t.c.clock.now()) == claims
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=token, replace=True), Caller())
    assert done.ticket_id is not None and done.closed_ticket is None


def test_replaces_round_trips_and_is_signed() -> None:
    claims = ProposalClaims("demo-17", RIGHT, "IT Support", "medium", "it", None, 2_000_000_000, "abc")
    token = sign(KEY, claims)
    assert verify(KEY, token, "demo-17", datetime(2026, 11, 8, tzinfo=UTC)).replaces == "abc"
    assert token != _old_format_token(claims)


def test_a_chat_reply_that_claims_a_closed_ticket_is_replaced_by_the_template() -> None:
    t = harness(says("I have closed your request.", "chat"), says("تم إغلاق طلبك", "chat"))
    generic = "I can help with campus requests. Tell me what you need."
    assert t.uc.turn(turn_of(user("ok")), Caller()).reply == generic
    assert t.uc.turn(turn_of(user("تمام")), Caller()).reply == "بقدر أساعدك بطلبات الجامعة. احكيلي شو بدك."
