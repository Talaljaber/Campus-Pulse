"""Service-role chat confirmation claims, backed by migration 0017 RPCs."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from campuspulse_ai.adapters.vectors.pgvector import store_call
from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.chat_claims import ConfirmationClaim

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi


class SupabaseChatClaimStore:
    def __init__(self, db: RestApi) -> None:
        self._db = db

    def claim(self, digest: str, alias: str, request_id: str, expires_at: datetime) -> ConfirmationClaim:
        raw: Any = store_call(
            "claim chat confirmation",
            lambda: self._db.rpc("cp_claim_chat_confirmation", {
                "p_token_digest": digest,
                "p_actor_alias": alias,
                "p_request_id": request_id,
                "p_expires_at": expires_at.isoformat(),
            }).execute().data,
        )
        if not isinstance(raw, dict) or raw.get("status") not in (
            "claimed", "in_progress", "completed", "invalid"
        ):
            raise ValueError("unexpected chat confirmation claim")
        result = dto.ChatConfirmResponse.model_validate(raw["result"]) if raw.get("result") else None
        return ConfirmationClaim(raw["status"], str(raw["request_id"]), result)

    def complete(self, digest: str, result: dto.ChatConfirmResponse) -> bool:
        raw: Any = store_call(
            "complete chat confirmation",
            lambda: self._db.rpc("cp_complete_chat_confirmation", {
                "p_token_digest": digest,
                "p_result": result.model_dump(mode="json"),
            }).execute().data,
        )
        return raw is True
