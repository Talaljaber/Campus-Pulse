"""P4.9: EscalateSlaUseCase, the SLA scanner (ARCHITECTURE §2.2)."""

from __future__ import annotations

from datetime import timedelta

from fixtures.backend_fakes import FakeSink
from fixtures.containers import build_test
from fixtures.lifecycle import seed_ticket

from campuspulse_ai.domain.errors import SinkError
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.values import TicketStatus


def test_an_overdue_ticket_is_flagged_exactly_once() -> None:
    c = build_test()
    now = c.clock.at
    ticket = seed_ticket(c, priority=Priority.MEDIUM, sla_due_at=now - timedelta(minutes=1))
    assert c.sla.run(now) == [ticket.id]
    saved = c.repo.get_ticket(ticket.id)
    assert (saved.status, saved.priority, saved.escalated_at) == (TicketStatus.NEW, Priority.MEDIUM, now)
    assert c.sla.run(now + timedelta(minutes=5)) == []
    # Staff move it to in_progress: still overdue, but never flagged twice.
    c.sync.change_status(ticket.id, TicketStatus.IN_PROGRESS, _Admin())
    assert c.sla.run(now + timedelta(minutes=10)) == []
    assert len(c.events("sla.escalated")) == 1


def test_priority_and_status_are_not_changed() -> None:
    c = build_test()
    ticket = seed_ticket(c, priority=Priority.HIGH, sla_due_at=c.clock.at - timedelta(hours=1))
    c.sla.run(c.clock.at)
    saved = c.repo.get_ticket(ticket.id)
    assert (saved.priority, saved.status) == (Priority.HIGH, TicketStatus.NEW)


def test_not_yet_due_resolved_and_closed_tickets_are_left_alone() -> None:
    c = build_test()
    now = c.clock.at
    due_later = seed_ticket(c, sla_due_at=now + timedelta(hours=1))
    done = seed_ticket(c, status=TicketStatus.SOLVED, sla_due_at=now - timedelta(hours=1))
    closed = seed_ticket(c, status=TicketStatus.CLOSED, sla_due_at=now - timedelta(hours=1))
    assert c.sla.run(now) == []
    for t in (due_later, done, closed):
        assert c.repo.get_ticket(t.id).escalated_at is None


def test_flagging_mirrors_the_ticket_and_notes_the_office() -> None:
    c = build_test()
    ticket = seed_ticket(c, office="it", priority=Priority.LOW, sla_due_at=c.clock.at - timedelta(minutes=1))
    c.sla.run(c.clock.at)
    assert c.sink.calls == [("update_status", ticket.id)]
    [note] = c.notifications()
    assert (note["alias"], note["kind"]) == ("office:it", "ticket_status")
    assert note["payload"]["status"] == "new"
    assert "overdue" in note["payload"]["message"]


def test_a_sink_failure_does_not_stop_the_scan() -> None:
    sink = FakeSink(name="linear", script=[SinkError("Linear down", retryable=True)])
    c = build_test(sinks=[sink])
    now = c.clock.at
    first = seed_ticket(c, sla_due_at=now - timedelta(minutes=2))
    second = seed_ticket(c, sla_due_at=now - timedelta(minutes=1))
    assert c.sla.run(now) == [first.id, second.id]
    assert c.repo.get_ticket(first.id).links[0].error == "Linear down"


class _Admin:
    role = "admin"
    office = None
    alias = None
