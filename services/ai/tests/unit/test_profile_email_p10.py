"""Package A: validation and consent contract; no external services."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from campuspulse_ai.application.use_cases.profile_email import (
    NotificationEmail,
    ProfileEmailDisabled,
    ProfileEmailService,
    normalize_email,
)
from campuspulse_ai.domain.errors import InvalidInput


@pytest.mark.parametrize(
    "address", ["a@b.com\nBcc:x@y.com", "A <a@b.com>", "a@b.com,b@c.com", "a@b", "a..b@c.com"]
)
def test_rejects_unsafe_or_malformed_email(address: str) -> None:
    with pytest.raises(InvalidInput):
        normalize_email(address)


def test_normalization_preserves_local_case() -> None:
    assert normalize_email("  Talal@Example.COM  ") == "Talal@example.com"


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, NotificationEmail] = {}

    def get(self, profile_id: str) -> NotificationEmail | None:
        return self.values.get(profile_id)

    def set_with_limit(
        self, profile_id: str, email: str, now: datetime, limit: int = 5, window_s: int = 3600
    ) -> NotificationEmail:
        del limit, window_s
        result = NotificationEmail(email, now)
        self.values[profile_id] = result
        return result

    def remove(self, profile_id: str) -> None:
        self.values.pop(profile_id, None)

    def has_active_consent(self, email: str) -> bool:
        return any(item.email == email for item in self.values.values())


def test_service_requires_consent_and_allows_removal_with_opt_in_disabled() -> None:
    store = FakeStore()
    service = ProfileEmailService(store, opt_in_enabled=True)
    now = datetime.now(UTC)
    with pytest.raises(InvalidInput):
        service.set("user", "a@example.com", False, now)
    assert service.set("user", "a@example.com", True, now).email == "a@example.com"
    disabled = ProfileEmailService(store, opt_in_enabled=False)
    with pytest.raises(ProfileEmailDisabled):
        disabled.set("user", "b@example.com", True, now)
    disabled.remove("user")
    assert disabled.get("user") is None
