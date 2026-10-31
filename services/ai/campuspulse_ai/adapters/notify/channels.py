"""ChannelNotifier: one `Notifier` that dispatches on `OutboxMessage.kind` (P4.4).

The composition root builds the chain once and hands it to the use cases:

    AllowlistedNotifier(ChannelNotifier({"email": GmailSmtpNotifier(...), "in_app": InAppNotifier(repo)}),
                        RecipientPolicy(settings.demo_email_allowlist), repo)

If SMTP is unavailable (OQ-5), the `email` entry is simply left out: email sends then fail cleanly
with `NotificationError` and are recorded as `failed`, while in-app delivery keeps working.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError
from campuspulse_ai.domain.ports import Notifier


class ChannelNotifier:
    """Routes each message to the notifier registered for its `kind`.

    Errors: `NotificationError(retryable=False)` when no notifier is registered for the kind; any
    error of the chosen notifier propagates unchanged.
    """

    def __init__(self, by_kind: Mapping[str, Notifier]) -> None:
        self._by_kind = MappingProxyType(dict(by_kind))

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._by_kind)

    def send(self, msg: OutboxMessage) -> OutboxMessage:
        notifier = self._by_kind.get(msg.kind)
        if notifier is None:
            raise NotificationError(f"no notifier configured for channel {msg.kind!r}", retryable=False)
        return notifier.send(msg)
