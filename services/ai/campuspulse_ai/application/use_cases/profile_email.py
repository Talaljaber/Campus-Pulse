"""P10 profile email contract and validation; caller identity is supplied by the API boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from campuspulse_ai.domain.errors import InvalidInput

_ADDRESS = re.compile(r"^[^\s@<>,;:\\]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}$")


def normalize_email(value: str) -> str:
    """A conservative single-mailbox address; preserve the local part's case."""
    address = value.strip()
    if len(address) > 254 or not _ADDRESS.fullmatch(address):
        raise InvalidInput("Enter one valid notification email address.")
    local, domain = address.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        raise InvalidInput("Enter one valid notification email address.")
    return f"{local}@{domain.lower()}"


@dataclass(frozen=True)
class NotificationEmail:
    email: str
    consented_at: datetime


class ProfileEmailStore(Protocol):
    def get(self, profile_id: str) -> NotificationEmail | None: ...
    def set_with_limit(
        self, profile_id: str, email: str, now: datetime, limit: int = 5, window_s: int = 3600
    ) -> NotificationEmail: ...
    def remove(self, profile_id: str) -> None: ...
    def has_active_consent(self, email: str) -> bool: ...
    def notification_for_alias(self, alias: str) -> str | None: ...
    def staff_notifications_for_office(self, office: str) -> list[tuple[str, str]]: ...


class ProfileEmailService:
    def __init__(self, store: ProfileEmailStore, *, opt_in_enabled: bool) -> None:
        self.store = store
        self.opt_in_enabled = opt_in_enabled

    def get(self, profile_id: str) -> NotificationEmail | None:
        return self.store.get(profile_id)

    def set(self, profile_id: str, email: str, consent: bool, now: datetime) -> NotificationEmail:
        if not self.opt_in_enabled:
            raise ProfileEmailDisabled()
        if consent is not True:
            raise InvalidInput("Consent is required to save a notification email.")
        return self.store.set_with_limit(profile_id, normalize_email(email), now)

    def remove(self, profile_id: str) -> None:
        self.store.remove(profile_id)


class ProfileEmailDisabled(Exception):
    pass


class ProfileEmailRateLimited(Exception):
    pass
