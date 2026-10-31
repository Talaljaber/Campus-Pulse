"""Outbox recording: every outgoing message becomes one `outbox` row (P4.4, SPEC §5.1 [12]).

`AllowlistedNotifier` is the outermost decorator of every notifier chain and is the only writer of
notifier outbox rows: it records `rejected`, `failed` or the sent message through `OutboxRecorder`.
Inner notifiers never write the outbox, so each send is recorded exactly once, and use cases must not
save it again.

The `OutboxMessage` entity has no `error` field (frozen contract), so the reason for a rejected or
failed send goes to the audit log (`events`: actor `notifier`, action `outbox.rejected` /
`outbox.failed`, entity `outbox:<id>`, payload `{to_address, kind, reason, retryable}`).
"""

from __future__ import annotations

import dataclasses

from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed
from campuspulse_ai.domain.ports import Repository

ACTOR = "notifier"
ACTION_REJECTED = "outbox.rejected"
ACTION_FAILED = "outbox.failed"


class OutboxRecorder:
    """Saves outbox rows and, for rejected or failed sends, an audit event with the reason.

    Errors: `StoreError` from the repository propagates (the caller decides how to degrade).
    """

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def sent(self, msg: OutboxMessage) -> OutboxMessage:
        """Record a message the inner notifier delivered (its status and provider id as returned)."""
        return self._repo.save_outbox(msg)

    def rejected(self, msg: OutboxMessage, error: RecipientNotAllowed) -> OutboxMessage:
        """Record a send the allow-list blocked: status `rejected`, nothing was sent."""
        saved = self._repo.save_outbox(dataclasses.replace(msg, status="rejected", provider_id=None))
        self._event(ACTION_REJECTED, saved, str(error), retryable=False)
        return saved

    def failed(self, msg: OutboxMessage, error: NotificationError) -> OutboxMessage:
        """Record a send the provider refused or could not complete: status `failed`."""
        saved = self._repo.save_outbox(dataclasses.replace(msg, status="failed", provider_id=None))
        self._event(ACTION_FAILED, saved, str(error), retryable=error.retryable)
        return saved

    def _event(self, action: str, msg: OutboxMessage, reason: str, *, retryable: bool) -> None:
        self._repo.append_event(
            ACTOR,
            action,
            f"outbox:{msg.id}",
            {"to_address": msg.to_address, "kind": msg.kind, "reason": reason, "retryable": retryable},
        )
