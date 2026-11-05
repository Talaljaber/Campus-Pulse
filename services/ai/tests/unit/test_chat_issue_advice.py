"""The issue preparer in the chat: it runs for every message (English too), its priority advice can only
raise the proposal and the ticket, and a failing preparer never drops the chat to the plain form."""

from __future__ import annotations

from fixtures.backend_fakes import FakeCore, make_core
from fixtures.chat import Caller, FakePreparer, ScriptedAgent, build_chat, says, turn_of, user

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.issue_context import PreparedIssue

TEXT = "I cannot log in to e-learning and my exam starts in 20 minutes"
EVIDENCE = ("starts in 20 minutes",)


def advising(level: str | None, evidence: tuple[str, ...] = EVIDENCE) -> FakePreparer:
    return FakePreparer(PreparedIssue(TEXT, level, evidence if level else ()))


def agent() -> ScriptedAgent:
    a = ScriptedAgent(replies=[says("I will prepare a request.", "request")])
    a.phrase_text = lambda facts: f"I can send this to {facts.department}. Shall I record it?"
    return a


def propose(t, text: str = TEXT) -> dto.ProposalOut:  # type: ignore[no-untyped-def]
    proposal = t.uc.turn(turn_of(user(text)), Caller()).proposal
    assert proposal is not None
    return proposal


def test_a_high_recommendation_raises_the_proposal_priority() -> None:
    t = build_chat(agent=agent(), preparer=advising("high"))
    assert propose(t).priority == "high"


def test_without_a_recommendation_the_priority_is_the_models_own() -> None:
    t = build_chat(agent=agent(), preparer=advising(None))
    assert propose(t).priority == "medium"


def test_a_lower_recommendation_never_lowers_the_priority() -> None:
    t = build_chat(agent=agent(), preparer=advising("low"))
    assert propose(t).priority == "medium"


def test_the_preparer_runs_for_an_english_message_and_gets_the_conversation() -> None:
    p = advising("high")
    t = build_chat(agent=agent(), preparer=p)
    propose(t)
    assert len(p.calls) == 1 and [m.content for m in p.calls[0]] == [TEXT]


def test_a_failing_preparer_does_not_drop_the_chat_to_the_form() -> None:
    t = build_chat(agent=agent(), preparer=FakePreparer(None))
    r = t.uc.turn(turn_of(user(TEXT)), Caller())
    assert r.mode == "agent" and r.proposal is not None and r.proposal.priority == "medium"


def test_a_crashing_preparer_does_not_drop_the_chat_to_the_form() -> None:
    class Crashing:
        def prepare(self, messages, anchor):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    t = build_chat(agent=agent())
    t.uc._preparer = Crashing()  # type: ignore[assignment]
    r = t.uc.turn(turn_of(user(TEXT)), Caller())
    assert r.mode == "agent" and r.proposal is not None


def test_a_queue_jump_or_injection_flag_blocks_the_raise() -> None:
    for flag in ("queue_jump", "injection"):
        core = FakeCore(default=make_core({"IT Support": 0.9}, {"medium": 0.9}, flags=frozenset({flag})))
        t = build_chat(agent=agent(), core=core, preparer=advising("high"))
        proposal = t.uc.turn(turn_of(user(TEXT)), Caller()).proposal
        assert proposal is not None and proposal.priority == "medium", flag


def test_an_empty_prepared_text_asks_for_more_detail() -> None:
    t = build_chat(agent=agent(), preparer=FakePreparer(PreparedIssue("", None, ())))
    r = t.uc.turn(turn_of(user("yes")), Caller())
    assert r.proposal is None and r.mode == "agent"


def test_confirming_creates_the_ticket_at_the_reviewed_priority() -> None:
    t = build_chat(agent=agent(), preparer=advising("high"))
    token = propose(t).token
    done = t.uc.confirm(dto.ChatConfirmRequest(proposal_token=token), Caller())
    [ticket] = t.tickets()
    assert done.ticket_id == ticket["id"] and str(ticket["priority"]) == "high"
    activity = t.h.journey.activity_for(ticket["id"])
    assert any(a.kind == "priority" and a.to_priority == "high" for a in activity)
