"""InAppNotifier: in-app messages as `notifications` rows (P4.4, D-006).

Students and staff receive these through Supabase Realtime on `notifications` (RLS: the recipient
alias and admins). For `kind="in_app"` messages `to_address` is the recipient's alias, never an email
address, so this channel never leaves our database.
"""

from __future__ import annotations

import dataclasses
import uuid

from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError, StoreError
from campuspulse_ai.domain.ports import Repository

DEFAULT_NOTIFICATION_KIND = "message"
PROVIDER_PREFIX = "inapp:"


class InAppNotifier:
    """`Notifier` for `kind="in_app"`: writes one `notifications` row through the repository.

    The row is `(alias=msg.to_address, kind=notification_kind, payload={ref, message, subject,
    priority, flags})`; `message` is the text the student chat prints verbatim (docs/api/README.md ›
    Notifications payload). There is deliberately no `status` key: the chat reads `{status, title}`
    as a ticket-status update. `send` returns `msg` with `status="sent"` and `provider_id="inapp:<ref>"`,
    where `ref` (a UUID) is also in the payload, because `save_notification` returns no id.

    Errors: `NotificationError(retryable=False)` for a non-in-app message or an empty alias;
    `NotificationError(retryable=True)` when the repository write fails (`StoreError`).
    """

    def __init__(self, repo: Repository, *, notification_kind: str = DEFAULT_NOTIFICATION_KIND) -> None:
        self._repo = repo
        self._kind = notification_kind

    def send(self, msg: OutboxMessage) -> OutboxMessage:
        if msg.kind != "in_app":
            raise NotificationError(
                f"InAppNotifier only delivers in_app messages, not {msg.kind!r}", retryable=False
            )
        if not msg.to_address.strip():
            raise NotificationError("in-app message has no recipient alias", retryable=False)
        ref = str(uuid.uuid4())
        payload: dict[str, object] = {
            "ref": ref,
            "message": msg.body,
            "subject": msg.subject,
            "priority": str(msg.priority) if msg.priority else None,
            "flags": sorted(msg.flags),
        }
        try:
            self._repo.save_notification(msg.to_address, self._kind, payload)
        except StoreError as exc:
            raise NotificationError(f"could not write the notification ({exc})", retryable=True) from exc
        return dataclasses.replace(msg, status="sent", provider_id=f"{PROVIDER_PREFIX}{ref}")
