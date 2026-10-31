"""P4.6: RetryingSink retries only retryable SinkErrors, with exponential backoff."""

from __future__ import annotations

import pytest
from fixtures.backend_fakes import FakeSink, make_ticket

from campuspulse_ai.adapters.integrations.retrying import RetryingSink
from campuspulse_ai.domain.errors import SinkError
from campuspulse_ai.domain.ports import TicketSink
from campuspulse_ai.domain.values import InboundEvent, TicketStatus

# Settings defaults SINK_RETRY_MAX / SINK_RETRY_BASE_S.
MAX_ATTEMPTS, BASE_S = 3, 0.5
TRANSIENT = SinkError("503", retryable=True)
PERMANENT = SinkError("401", retryable=False)


def wrap(inner: FakeSink) -> tuple[RetryingSink, list[float]]:
    sleeps: list[float] = []
    return RetryingSink(inner, MAX_ATTEMPTS, BASE_S, sleep=sleeps.append), sleeps


def test_is_a_ticket_sink_named_like_its_inner() -> None:
    sink, _ = wrap(FakeSink(name="linear"))
    assert isinstance(sink, TicketSink) and sink.name == "linear"


def test_transient_errors_are_retried_until_success() -> None:
    inner = FakeSink(script=[TRANSIENT, TRANSIENT])
    sink, sleeps = wrap(inner)
    link = sink.create(make_ticket("req-1", id="t-1"))
    assert link.external_id == "fake-t-1" and len(inner.calls) == 3 and sleeps == [BASE_S, 2 * BASE_S]


def test_attempts_run_out_and_the_last_error_is_raised() -> None:
    inner = FakeSink(script=[TRANSIENT, TRANSIENT, SinkError("still 503", retryable=True)])
    sink, sleeps = wrap(inner)
    with pytest.raises(SinkError, match="still 503") as info:
        sink.update_status(make_ticket("req-1", id="t-1", status=TicketStatus.IN_PROGRESS))
    assert info.value.retryable and len(inner.calls) == MAX_ATTEMPTS and len(sleeps) == MAX_ATTEMPTS - 1


def test_permanent_errors_are_not_retried() -> None:
    inner = FakeSink(script=[PERMANENT])
    sink, sleeps = wrap(inner)
    with pytest.raises(SinkError) as info:
        sink.close(make_ticket("req-1", id="t-1"))
    assert info.value is PERMANENT and inner.calls == [("close", "t-1")] and sleeps == []


def test_inbound_is_passed_through_without_retries() -> None:
    event = InboundEvent("fake", "ext-1", TicketStatus.RESOLVED, make_ticket("r").sla_due_at)
    inner = FakeSink(inbound=event)
    sink, _ = wrap(inner)
    assert sink.handle_inbound(b"{}", "sig") is event and inner.calls == [("handle_inbound", "sig")]


def test_bad_settings_are_rejected() -> None:
    with pytest.raises(ValueError):
        RetryingSink(FakeSink(), 0, BASE_S)
    with pytest.raises(ValueError):
        RetryingSink(FakeSink(), MAX_ATTEMPTS, -1.0)
