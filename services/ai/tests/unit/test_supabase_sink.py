"""P4.6: SupabaseSink over InMemoryRepository always, and over SupabaseRepository with `-m supabase`.

Supabase rows are tagged per run (request alias) and deleted in teardown; tickets cascade.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.backend_fakes import make_ticket
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.integrations.supabase_sink import SupabaseSink
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.domain.entities import Request
from campuspulse_ai.domain.errors import SinkError
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.ports import Repository, TicketSink
from campuspulse_ai.domain.values import RequestStatus, TicketStatus


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Harness:
    def __init__(self, repo: Repository, cleanup: Any = None) -> None:
        self.repo = repo
        self.tag = f"sink-test-{uuid.uuid4().hex[:8]}"
        self._cleanup = cleanup

    def request(self) -> str:
        saved = self.repo.save_request(
            Request(
                id="",
                alias=self.tag,
                raw_text="I cannot register CS 201 and today is the last day",
                normalized=None,
                input_mode="text",
                status=RequestStatus.RECEIVED,
                created_at=datetime.now(UTC),
            )
        )
        return saved.id

    def cleanup(self) -> None:
        if self._cleanup is not None:
            self._cleanup(self.tag)


def inmemory() -> Harness:
    return Harness(InMemoryRepository(UtcClock()))


def supabase() -> Harness:
    from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository

    db = supabase_test_client()

    def cleanup(tag: str) -> None:
        db.table("requests").delete().like("alias", f"{tag}%").execute()  # cascades to tickets

    return Harness(SupabaseRepository(db, UtcClock()), cleanup)


@pytest.fixture(
    params=[pytest.param(inmemory), pytest.param(supabase, marks=pytest.mark.supabase)],
    ids=["inmemory", "supabase"],
)
def h(request: pytest.FixtureRequest) -> Iterator[Harness]:
    harness: Harness = request.param()
    try:
        yield harness
    finally:
        harness.cleanup()


def test_create_is_the_system_of_record(h: Harness) -> None:
    sink = SupabaseSink(h.repo)
    assert isinstance(sink, TicketSink) and sink.name == "supabase"
    ticket = make_ticket(h.request(), id=str(uuid.uuid4()))
    link = sink.create(ticket)
    assert (link.ticket_id, link.sink, link.external_id, link.url) == (ticket.id, "supabase", ticket.id, None)
    stored = h.repo.get_ticket(ticket.id)
    assert (stored.office, stored.priority, stored.status) == ("registrar", Priority.HIGH, TicketStatus.NEW)
    assert stored.title == ticket.title and stored.links == []
    sink.create(ticket)  # idempotent on the ticket id
    assert h.repo.get_ticket(ticket.id).id == ticket.id


def test_update_status_and_close(h: Harness) -> None:
    sink = SupabaseSink(h.repo)
    ticket = make_ticket(h.request(), id=str(uuid.uuid4()))
    sink.create(ticket)
    ticket.status, ticket.priority = TicketStatus.IN_PROGRESS, Priority.HIGH
    sink.update_status(ticket)
    assert h.repo.get_ticket(ticket.id).status == TicketStatus.IN_PROGRESS
    sink.close(ticket)
    assert h.repo.get_ticket(ticket.id).status == TicketStatus.CLOSED
    assert ticket.status == TicketStatus.IN_PROGRESS  # the caller's object is not mutated


def test_inbound_is_not_handled_here(h: Harness) -> None:
    assert SupabaseSink(h.repo).handle_inbound(b"{}", "sig") is None


def test_store_errors_become_sink_errors(h: Harness) -> None:
    orphan = make_ticket(str(uuid.uuid4()), id=str(uuid.uuid4()))  # no such request: FK violation
    with pytest.raises(SinkError) as info:
        SupabaseSink(h.repo).create(orphan)
    assert info.value.retryable is True
