"""D-011: the domain additions are additive, and the codec degrades on the live schema until the
DB migration lands (`codec.PENDING_COLUMNS` / `PENDING_VALUES`)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fixtures.backend_fakes import make_ticket

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.values import TicketLink

AT = datetime(2026, 11, 5, 6, 0, tzinfo=UTC)
Status = Literal["queued", "sent", "failed", "rejected", "deferred"]


def _outbox(status: Status, error: str | None) -> OutboxMessage:
    return OutboxMessage("", "email", "demo@example.invalid", "s", "b", None, status, AT, error=error)


def test_new_fields_default_so_existing_callers_still_work() -> None:
    ticket = make_ticket("r1", id="t1")
    assert ticket.tags == () and TicketLink("t1", "linear", "x").error is None
    assert _outbox("sent", None).error is None


def test_rows_carry_tags_last_error_and_outbox_error() -> None:
    ticket = make_ticket("r1", id="t1")
    ticket.tags = ("safety",)
    assert codec.ticket_row(ticket)["tags"] == ["safety"]
    assert codec.to_ticket(codec.ticket_row(ticket), []).tags == ("safety",)
    link = TicketLink("t1", "linear", "error:t1", None, "Linear timed out")
    assert codec.link_row(link)["last_error"] == "Linear timed out"
    assert codec.to_link(codec.link_row(link)) == link
    assert codec.outbox_row(_outbox("failed", "smtp down"))["error"] == "smtp down"


def test_rows_without_the_new_columns_read_as_defaults() -> None:
    row = codec.ticket_row(make_ticket("r1", id="t1"))
    del row["tags"]
    assert codec.to_ticket(row, []).tags == ()
    link_row = codec.link_row(TicketLink("t1", "linear", "x"))
    del link_row["last_error"]
    assert codec.to_link(link_row).error is None


def test_live_schema_guard_drops_pending_columns_and_maps_pending_values() -> None:
    ticket = make_ticket("r1", id="t1")
    ticket.tags = ("safety",)
    live = codec.for_live_schema("tickets", codec.ticket_row(ticket))
    assert ("tags" in live) == ("tags" not in codec.PENDING_COLUMNS.get("tickets", frozenset()))
    held = codec.outbox_row(_outbox("deferred", "daily email cap of 1 reached"))
    out = codec.for_live_schema("outbox", held)
    if "deferred" in codec.PENDING_VALUES.get(("outbox", "status"), {}):
        assert (out["status"], out["error"]) == ("queued", "deferred: daily email cap of 1 reached")
        no_reason = codec.for_live_schema("outbox", codec.outbox_row(_outbox("deferred", None)))
        assert no_reason["error"] == "deferred"
    untouched = codec.outbox_row(_outbox("sent", None))
    assert codec.for_live_schema("outbox", untouched) == untouched
