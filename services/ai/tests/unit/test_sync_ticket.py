"""P4.9: SyncTicketUseCase (ARCHITECTURE §2.2): the real LinearSink inbound path, InMemoryRepository."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fixtures.backend_fakes import FakeSink, FrozenClock
from fixtures.containers import STUDENT_INBOX, BackendTestContainer, build_test
from fixtures.lifecycle import ALIAS, offline_linear, seed_ticket, signature, webhook_body

from campuspulse_ai.domain.errors import InvalidInput, NotFound, SinkError, Unauthorized
from campuspulse_ai.domain.values import TicketStatus


@dataclass(frozen=True)
class Caller:
    role: str
    office: str | None = None
    alias: str | None = None


REGISTRAR = Caller("staff", "registrar")


def linear_container() -> BackendTestContainer:
    """Sinks: the offline LinearSink (inbound HMAC path) and a FakeSink `other` that records mirrors."""
    other = FakeSink(name="other")
    c = build_test(sinks=[offline_linear(FrozenClock()), other])
    c.sink = other
    return c


def counts(c: BackendTestContainer) -> tuple[int, int, int]:
    return (len(c.notifications()), len(c.events()), len(c.outbox()))


def test_signed_state_change_resolves_the_ticket_and_tells_the_student() -> None:
    c = linear_container()
    ticket = seed_ticket(c)
    issue = ticket.links[0].external_id
    raw = webhook_body(c.clock, issue)
    saved = c.sync.run("linear", raw, signature(raw))
    assert saved is not None and saved.status == TicketStatus.SOLVED
    stored = c.repo.get_ticket(ticket.id)
    assert stored.status == TicketStatus.SOLVED and stored.resolved_at is not None
    [note] = c.notifications()
    assert (note["alias"], note["kind"]) == (ALIAS, "ticket_status")
    assert note["payload"] == {"ticket_id": ticket.id, "status": "solved", "title": ticket.title}
    [email] = c.email.sent
    assert email.to_address == STUDENT_INBOX and "Resolved" in email.subject
    assert c.events("ticket.status")[0]["payload"]["source"] == "linear"
    assert ("update_status", ticket.id) in c.sink.calls  # mirrored to the other sinks, not back to Linear


@pytest.mark.parametrize("bad", ["", "deadbeef", "0" * 64])
def test_bad_signature_is_unauthorized_and_writes_nothing(bad: str) -> None:
    c = linear_container()
    ticket = seed_ticket(c)
    before = counts(c)
    raw = webhook_body(c.clock, ticket.links[0].external_id)
    with pytest.raises(Unauthorized):
        c.sync.apply_inbound("linear", raw, bad)
    assert counts(c) == before and c.repo.get_ticket(ticket.id).status == TicketStatus.NEW


def test_stale_webhook_and_non_json_body() -> None:
    c = linear_container()
    ticket = seed_ticket(c)
    stale = webhook_body(c.clock, ticket.links[0].external_id, webhookTimestamp=0)
    with pytest.raises(Unauthorized):
        c.sync.apply_inbound("linear", stale, signature(stale))
    with pytest.raises(InvalidInput):
        c.sync.apply_inbound("linear", b"not json", signature(b"not json"))


def test_backward_or_equal_inbound_changes_are_ignored() -> None:
    """Our own close comes back from Linear as `completed` -> resolved: a closed ticket stays closed."""
    c = linear_container()
    closed = seed_ticket(c, status=TicketStatus.CLOSED)
    raw = webhook_body(c.clock, closed.links[0].external_id, "completed")
    assert c.sync.run("linear", raw, signature(raw)) is None
    progress = seed_ticket(c, status=TicketStatus.IN_PROGRESS)
    back = webhook_body(c.clock, progress.links[0].external_id, "unstarted")
    same = webhook_body(c.clock, progress.links[0].external_id, "started")
    assert c.sync.run("linear", back, signature(back)) is None
    assert c.sync.run("linear", same, signature(same)) is None
    assert c.repo.get_ticket(closed.id).status == TicketStatus.CLOSED
    assert c.repo.get_ticket(progress.id).status == TicketStatus.IN_PROGRESS
    assert c.notifications() == []


def test_unknown_issue_and_unconfigured_sink() -> None:
    c = linear_container()
    raw = webhook_body(c.clock, "issue-we-never-created")
    assert c.sync.apply_inbound("linear", raw, signature(raw)) is None
    with pytest.raises(Unauthorized):
        build_test().sync.apply_inbound("github", raw, signature(raw))


def test_dashboard_change_by_the_tickets_office() -> None:
    c = build_test()
    ticket = seed_ticket(c)
    saved = c.sync.from_dashboard(ticket.id, TicketStatus.IN_PROGRESS, REGISTRAR, note=" On it. ")
    assert saved.status == TicketStatus.IN_PROGRESS and saved.resolved_at is None
    assert c.sink.calls == [("update_status", ticket.id)]  # the dashboard change reaches Linear
    [note] = c.notifications()
    assert note["payload"]["message"] == "On it." and note["payload"]["status"] == "in_progress"
    assert c.email.sent == []  # only `resolved` emails the student


def test_dashboard_change_by_other_office_staff_or_a_student_is_forbidden() -> None:
    c = build_test()
    ticket = seed_ticket(c)
    for caller in (Caller("staff", "it"), Caller("staff", None), Caller("student", alias=ALIAS)):
        with pytest.raises(Unauthorized):
            c.sync.change_status(ticket.id, TicketStatus.SOLVED, caller)
    assert c.repo.get_ticket(ticket.id).status == TicketStatus.NEW and c.sink.calls == []
    admin = c.sync.change_status(ticket.id, TicketStatus.SOLVED, Caller("admin"))
    assert admin.changed and admin.ticket.resolved_at == c.clock.at


def test_dashboard_reopen_clears_resolved_at_and_same_status_is_a_no_op() -> None:
    c = build_test()
    ticket = seed_ticket(c, status=TicketStatus.SOLVED)
    same = c.sync.change_status(ticket.id, TicketStatus.SOLVED, REGISTRAR)
    assert not same.changed
    c.sync.propagate(same)
    assert c.notifications() == [] and c.sink.calls == []
    reopened = c.sync.from_dashboard(ticket.id, TicketStatus.IN_PROGRESS, REGISTRAR)
    assert reopened.status == TicketStatus.IN_PROGRESS and reopened.resolved_at is None
    with pytest.raises(NotFound):
        c.sync.change_status("00000000-0000-0000-0000-000000000000", TicketStatus.CLOSED, REGISTRAR)


def test_propagation_failures_never_escape() -> None:
    sink = FakeSink(name="linear", script=[SinkError("Linear down", retryable=True)])
    c = build_test(sinks=[sink])
    ticket = seed_ticket(c)
    saved = c.sync.from_dashboard(ticket.id, TicketStatus.SOLVED, REGISTRAR)
    assert saved.status == TicketStatus.SOLVED
    [link] = c.repo.get_ticket(ticket.id).links
    assert link.error == "Linear down"
    assert c.notifications()  # the student is still told
