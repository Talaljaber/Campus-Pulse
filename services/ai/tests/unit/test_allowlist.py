"""X4.7 / P4.4: the demo allow-list cannot be bypassed (ARCHITECTURE §3.13).

`real.person@gju.edu.jo` is rejected, recorded as an outbox `rejected` row with its reason, and the
provider is called 0 times. Booking attendees are covered in `test_calendar.py`.
"""

from __future__ import annotations

from typing import NoReturn

import pytest
from fixtures.backend_fakes import FakeNotifier, FrozenClock, make_outbox
from pydantic import SecretStr

from campuspulse_ai.adapters.notify.allowlist import AllowlistedNotifier
from campuspulse_ai.adapters.notify.gmail_smtp import GmailSmtpNotifier
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import Notifier

DEMO_INBOX = "campuspulse.support+student17@gmail.com"
REAL_PERSON = "real.person@gju.edu.jo"


def chain(allowlist: frozenset[str], inner: Notifier) -> tuple[AllowlistedNotifier, InMemoryRepository]:
    repo = InMemoryRepository(FrozenClock())
    return AllowlistedNotifier(inner, RecipientPolicy(allowlist), repo), repo


def outbox_rows(repo: InMemoryRepository) -> list[dict[str, object]]:
    return list(repo.tables["outbox"].values())


def events(repo: InMemoryRepository) -> list[dict[str, object]]:
    return list(repo.tables["events"].values())


def test_real_person_is_rejected_and_provider_never_called() -> None:
    inner = FakeNotifier()
    notifier, repo = chain(frozenset({DEMO_INBOX}), inner)
    with pytest.raises(RecipientNotAllowed):
        notifier.send(make_outbox(REAL_PERSON))
    assert inner.calls == 0
    [row] = outbox_rows(repo)
    assert (row["status"], row["to_address"], row["provider_id"]) == ("rejected", REAL_PERSON, None)
    assert "allow-list" in row["error"]  # D-011: the reason is on the row itself
    [event] = events(repo)
    assert event["action"] == "outbox.rejected" and event["entity"] == f"outbox:{row['id']}"
    assert REAL_PERSON in str(event["payload"]) and "allow-list" in str(event["payload"])


def test_empty_allowlist_rejects_everything() -> None:
    inner = FakeNotifier()
    notifier, repo = chain(frozenset(), inner)
    for address in (DEMO_INBOX, REAL_PERSON, ""):
        with pytest.raises(RecipientNotAllowed):
            notifier.send(make_outbox(address))
    assert inner.calls == 0 and [r["status"] for r in outbox_rows(repo)] == ["rejected"] * 3


@pytest.mark.parametrize(
    ("address", "allowed"),
    [
        (DEMO_INBOX, True),
        ("  CampusPulse.Support+Student17@GMAIL.com ", True),  # case and whitespace only
        ("campuspulse.support@gmail.com", False),  # no plus-address wildcard
        ("campuspulse.support+student18@gmail.com", False),
        ("campuspulse.support+student17@mail.gmail.com", False),  # no subdomain wildcard
        ("campuspulse.support+student17@gmail.com.evil.io", False),
        ("x" + DEMO_INBOX, False),
    ],
)
def test_case_insensitive_exact_match(address: str, allowed: bool) -> None:
    inner = FakeNotifier()
    notifier, _ = chain(frozenset({DEMO_INBOX}), inner)
    if allowed:
        assert notifier.send(make_outbox(address)).status == "sent"
    else:
        with pytest.raises(RecipientNotAllowed):
            notifier.send(make_outbox(address))
    assert inner.calls == int(allowed)


def test_sent_message_is_recorded_once_with_provider_id() -> None:
    notifier, repo = chain(frozenset({DEMO_INBOX}), FakeNotifier())
    sent = notifier.send(make_outbox(DEMO_INBOX))
    [row] = outbox_rows(repo)
    assert sent.id == row["id"] and sent.status == "sent" and row["provider_id"] == "fake:1"
    assert events(repo) == []


@pytest.mark.parametrize("retryable", [True, False])
def test_provider_failure_is_recorded_failed_and_reraised(retryable: bool) -> None:
    inner = FakeNotifier(fail_with=NotificationError("smtp down", retryable=retryable))
    notifier, repo = chain(frozenset({DEMO_INBOX}), inner)
    with pytest.raises(NotificationError) as info:
        notifier.send(make_outbox(DEMO_INBOX))
    assert info.value.retryable is retryable
    [row] = outbox_rows(repo)
    assert (row["status"], row["error"]) == ("failed", "smtp down")
    [event] = events(repo)
    assert event["action"] == "outbox.failed" and event["payload"]["retryable"] is retryable  # type: ignore[index]


def test_in_app_messages_skip_the_email_check_but_are_recorded() -> None:
    inner = FakeNotifier()
    notifier, repo = chain(frozenset(), inner)
    notifier.send(make_outbox("student-17", kind="in_app"))
    assert inner.calls == 1 and [r["status"] for r in outbox_rows(repo)] == ["sent"]


def test_other_external_channels_are_checked_too() -> None:
    inner = FakeNotifier()
    notifier, _ = chain(frozenset({DEMO_INBOX}), inner)
    with pytest.raises(RecipientNotAllowed):
        notifier.send(make_outbox("+962790000000", kind="whatsapp"))
    assert inner.calls == 0


def test_smtp_notifier_refuses_before_connecting_even_unwrapped() -> None:
    connections: list[object] = []

    def factory(*args: object) -> object:
        connections.append(args)
        raise AssertionError("must not connect")

    smtp = GmailSmtpNotifier(
        "smtp.test",
        587,
        "campuspulse.support@gmail.com",
        SecretStr("app-password"),
        policy=RecipientPolicy(frozenset({DEMO_INBOX})),
        clock=FrozenClock(),
        timeout_s=1.0,
        max_retries=0,
        backoff_s=0.0,
        daily_cap=10,
        smtp_factory=factory,  # type: ignore[arg-type]
    )
    with pytest.raises(RecipientNotAllowed):
        smtp.send(make_outbox(REAL_PERSON))
    assert connections == []
    # Wrapped, the inner refusal is recorded as rejected too.
    notifier, repo = chain(frozenset({DEMO_INBOX, REAL_PERSON}), smtp)
    with pytest.raises(RecipientNotAllowed):
        notifier.send(make_outbox(REAL_PERSON))
    assert [r["status"] for r in outbox_rows(repo)] == ["rejected"] and connections == []


def test_deferred_send_is_recorded_with_its_reason() -> None:
    """D-011: an inner notifier that holds a message back (e.g. the daily cap) is recorded `deferred`."""
    clock = FrozenClock()
    policy = RecipientPolicy(frozenset({DEMO_INBOX}))
    repo = InMemoryRepository()
    smtp = GmailSmtpNotifier(
        "smtp.example.invalid", 587, "support@example.invalid", SecretStr("pw"), policy=policy,
        clock=clock, timeout_s=1.0, max_retries=0, backoff_s=0.0, daily_cap=0,
        smtp_factory=_never_connect,
    )  # fmt: skip
    notifier = AllowlistedNotifier(smtp, policy, repo)
    held = notifier.send(make_outbox(DEMO_INBOX))
    [row] = outbox_rows(repo)
    assert held.status == row["status"] == "deferred" and row["error"] == "daily email cap of 0 reached"
    assert row["provider_id"] is None and events(repo) == []


def _never_connect(*_: object) -> NoReturn:
    raise AssertionError("a deferred send must not open a connection")
