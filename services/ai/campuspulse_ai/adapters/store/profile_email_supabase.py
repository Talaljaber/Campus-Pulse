"""Service-role persistence for profile notification email."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from campuspulse_ai.adapters.store.codec import parse_dt
from campuspulse_ai.adapters.vectors.pgvector import store_call
from campuspulse_ai.application.use_cases.profile_email import (
    NotificationEmail,
    ProfileEmailRateLimited,
    normalize_email,
)
from campuspulse_ai.domain.errors import NotFound

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi


class SupabaseProfileEmailStore:
    def __init__(self, db: RestApi) -> None:
        self._db = db

    def get(self, profile_id: str) -> NotificationEmail | None:
        rows: Any = store_call(
            "get profile email",
            lambda: (
                self._db.table("profiles")
                .select("notify_email,notify_email_consent_at")
                .eq("id", profile_id)
                .limit(1)
                .execute()
                .data
            ),
        )
        if not rows or not rows[0].get("notify_email") or not rows[0].get("notify_email_consent_at"):
            return None
        stamp = parse_dt(rows[0]["notify_email_consent_at"])
        assert stamp is not None
        return NotificationEmail(str(rows[0]["notify_email"]), stamp)

    def set_with_limit(
        self, profile_id: str, email: str, now: datetime, limit: int = 5, window_s: int = 3600
    ) -> NotificationEmail:
        del now  # SQL owns the timestamp.
        status: Any = store_call(
            "set profile email",
            lambda: (
                self._db.rpc(
                    "cp_set_notification_email",
                    {
                        "p_profile_id": profile_id,
                        "p_email": normalize_email(email),
                        "p_limit": limit,
                        "p_window_seconds": window_s,
                    },
                )
                .execute()
                .data
            ),
        )
        if status == "limited":
            raise ProfileEmailRateLimited()
        if status == "missing":
            raise NotFound("profile not found")
        if status not in ("saved", "unchanged"):
            raise ValueError("unexpected profile email status")
        result = self.get(profile_id)
        assert result is not None
        return result

    def remove(self, profile_id: str) -> None:
        store_call(
            "remove profile email",
            lambda: self._db.rpc("cp_remove_notification_email", {"p_profile_id": profile_id}).execute(),
        )

    def has_active_consent(self, email: str) -> bool:
        rows: Any = store_call(
            "check profile email consent",
            lambda: (
                self._db.table("profiles")
                .select("id")
                .eq("notify_email", normalize_email(email))
                .not_.is_("notify_email_consent_at", "null")
                .limit(1)
                .execute()
                .data
            ),
        )
        return bool(rows)

    def notification_for_alias(self, alias: str) -> str | None:
        rows: Any = store_call(
            "get requester notification email",
            lambda: (
                self._db.table("profiles")
                .select("notify_email,notify_email_consent_at")
                .eq("alias", alias)
                .limit(1)
                .execute()
                .data
            ),
        )
        if not rows or not rows[0].get("notify_email_consent_at"):
            return None
        return str(rows[0]["notify_email"])

    def staff_notifications_for_office(self, office: str) -> list[tuple[str, str]]:
        rows: Any = store_call(
            "get office notification emails",
            lambda: (
                self._db.table("profiles")
                .select("alias,notify_email,notify_email_consent_at")
                .eq("role", "staff")
                .eq("office", office)
                .not_.is_("notify_email_consent_at", "null")
                .execute()
                .data
            ),
        )
        return [
            (str(row.get("alias") or ""), str(row["notify_email"])) for row in rows if row.get("notify_email")
        ]

    def consented_broadcast_recipients(self) -> list[str]:
        rows: Any = store_call(
            "get broadcast notification emails",
            lambda: (
                self._db.table("profiles")
                .select("notify_email")
                .in_("role", ["student", "staff"])
                .not_.is_("notify_email_consent_at", "null")
                .execute()
                .data
            ),
        )
        return [str(row["notify_email"]) for row in rows if row.get("notify_email")]
