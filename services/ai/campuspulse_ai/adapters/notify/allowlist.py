"""AllowlistedNotifier: the demo allow-list in front of every notifier (P4.4, ARCHITECTURE §3.13).

CLAUDE.md non-negotiable: never send email to real people. Every external channel (email, and
WhatsApp if it is ever wired) is checked against `RecipientPolicy(DEMO_EMAIL_ALLOWLIST)` before the
inner notifier is called; an empty allow-list rejects everything. In-app messages go to an alias's
`notifications` row inside our own database, so they are not checked, but they are recorded the
same way ("symmetry of logging").
"""

from __future__ import annotations

from campuspulse_ai.adapters.notify.outbox import OutboxRecorder
from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import Notifier, Repository

# Channels that never leave our own database. Anything else is an external address.
INTERNAL_KINDS: frozenset[str] = frozenset({"in_app"})


class AllowlistedNotifier:
    """`Notifier` decorator: allow-list check, then the inner send, then exactly one outbox row.

    `send(msg)`:
    - external kind and `msg.to_address` not allow-listed -> outbox row `rejected` + audit event,
      the inner notifier is **never called**, and `RecipientNotAllowed` is raised;
    - the inner notifier raises `NotificationError` -> outbox row `failed` + audit event, re-raised
      (`ActUseCase` catches it; triage never fails because of a notification, LD-15);
    - the inner notifier raises `RecipientNotAllowed` (its own defence-in-depth check) -> recorded
      as `rejected`, re-raised;
    - otherwise the delivered message (status `sent`, `provider_id`) is saved and returned with its
      outbox id.

    Must be the outermost decorator: inner notifiers do not write the outbox (see `outbox.py`).
    Errors: `RecipientNotAllowed`, `NotificationError`, `StoreError` (repository).
    """

    def __init__(self, inner: Notifier, policy: RecipientPolicy, repo: Repository) -> None:
        self._inner = inner
        self._policy = policy
        self._recorder = OutboxRecorder(repo)

    def send(self, msg: OutboxMessage) -> OutboxMessage:
        if msg.kind not in INTERNAL_KINDS:
            try:
                self._policy.check(msg.to_address)
            except RecipientNotAllowed as exc:
                self._recorder.rejected(msg, exc)
                raise
        try:
            delivered = self._inner.send(msg)
        except RecipientNotAllowed as exc:
            self._recorder.rejected(msg, exc)
            raise
        except NotificationError as exc:
            self._recorder.failed(msg, exc)
            raise
        return self._recorder.sent(delivered)
