"""P4.4: InAppNotifier and ChannelNotifier, alone and inside the allow-listed chain."""

from __future__ import annotations

import pytest
from fixtures.backend_fakes import FakeNotifier, FrozenClock, make_outbox

from campuspulse_ai.adapters.notify.allowlist import AllowlistedNotifier
from campuspulse_ai.adapters.notify.channels import ChannelNotifier
from campuspulse_ai.adapters.notify.inapp import InAppNotifier
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import Notifier

DEMO_INBOX = "campuspulse.support+student17@gmail.com"


def test_inapp_writes_one_notification_row() -> None:
    repo = InMemoryRepository(FrozenClock())
    notifier = InAppNotifier(repo, notification_kind="ticket_status")
    assert isinstance(notifier, Notifier)
    msg = make_outbox("student-17", kind="in_app", subject="Ticket resolved", body="It was resolved.")
    msg.priority, msg.flags = Priority.HIGH, frozenset({"safety"})
    sent = notifier.send(msg)
    [row] = repo.tables["notifications"].values()
    assert (row["alias"], row["kind"]) == ("student-17", "ticket_status")
    payload = row["payload"]
    assert payload["subject"] == "Ticket resolved" and payload["priority"] == "high"
    assert payload["flags"] == ["safety"]
    assert sent.status == "sent" and sent.provider_id == f"inapp:{payload['ref']}"
    assert repo.tables["outbox"] == {}  # only AllowlistedNotifier writes the outbox


def test_inapp_rejects_email_and_empty_alias() -> None:
    notifier = InAppNotifier(InMemoryRepository())
    for msg in (make_outbox(DEMO_INBOX), make_outbox(" ", kind="in_app")):
        with pytest.raises(NotificationError) as info:
            notifier.send(msg)
        assert info.value.retryable is False


def test_channel_notifier_routes_by_kind() -> None:
    email, in_app = FakeNotifier(), FakeNotifier()
    router = ChannelNotifier({"email": email, "in_app": in_app})
    router.send(make_outbox(DEMO_INBOX))
    router.send(make_outbox("student-17", kind="in_app"))
    assert (email.calls, in_app.calls) == (1, 1) and router.kinds == {"email", "in_app"}
    with pytest.raises(NotificationError):
        router.send(make_outbox("+962790000000", kind="whatsapp"))


def test_full_chain_records_every_outcome_once() -> None:
    repo = InMemoryRepository(FrozenClock())
    router = ChannelNotifier({"in_app": InAppNotifier(repo)})  # no SMTP configured (OQ-5)
    chain = AllowlistedNotifier(router, RecipientPolicy(frozenset({DEMO_INBOX})), repo)
    chain.send(make_outbox("student-17", kind="in_app"))
    with pytest.raises(NotificationError):
        chain.send(make_outbox(DEMO_INBOX))  # allow-listed, but no email channel
    with pytest.raises(RecipientNotAllowed):
        chain.send(make_outbox("real.person@gju.edu.jo"))
    statuses = sorted(r["status"] for r in repo.tables["outbox"].values())
    assert statuses == ["failed", "rejected", "sent"]
    assert len(repo.tables["notifications"]) == 1
