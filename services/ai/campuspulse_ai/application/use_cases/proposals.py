"""Signed chat proposals (P9.8, docs/plan/p9/PLAN.md section f).

A ticket from the chat is created only through a token this module signed for the caller's alias, so the
language model (or text hidden in a message) can never open one by itself. Format:

    base64url(json{alias, text, category, priority, office, hint_id, exp[, replaces]})
        + "." + hex(hmac_sha256(key, p))

`replaces` (P10.18) is the id of the requester's open ticket a correction proposal would close. It is written
only when set, so a token without it is byte-for-byte the format signed before P10.18, and such older tokens
still verify (their `replaces` is None).

`key = sha256("cp-proposal:" + AI_SERVICE_TOKEN)`. `verify` raises `InvalidInput` (422) for a malformed
token, a bad signature, an expired token or a token that was signed for another alias.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime

from campuspulse_ai.domain.errors import InvalidInput

KEY_PREFIX = "cp-proposal:"
_PARTS = 2
_FIELDS = ("alias", "text", "category", "priority", "office", "hint_id", "exp")


@dataclass(frozen=True, slots=True)
class ProposalClaims:
    """What a proposal token binds: who, which text, and what the server proposed. `exp` is epoch seconds."""

    alias: str
    text: str
    category: str
    priority: str
    office: str
    hint_id: str | None
    exp: int
    replaces: str | None = None


def derive_key(service_token: str) -> bytes:
    """The HMAC key: sha256 of the prefix and the service token."""
    return hashlib.sha256((KEY_PREFIX + service_token).encode("utf-8")).digest()


def _mac(key: bytes, payload: str) -> str:
    return hmac.new(key, payload.encode("ascii"), hashlib.sha256).hexdigest()


def sign(key: bytes, claims: ProposalClaims) -> str:
    fields: dict[str, object] = {name: getattr(claims, name) for name in _FIELDS}
    if claims.replaces is not None:
        fields["replaces"] = claims.replaces
    body = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{payload}.{_mac(key, payload)}"


def verify(key: bytes, token: str, alias: str, now: datetime) -> ProposalClaims:
    """The claims of a valid token for `alias` at `now`. Raises `InvalidInput` otherwise."""
    parts = token.split(".")
    if len(parts) != _PARTS or not parts[0] or not parts[1].isascii():
        raise InvalidInput("invalid proposal token")
    payload, signature = parts
    if not payload.isascii() or not hmac.compare_digest(_mac(key, payload), signature):
        raise InvalidInput("invalid proposal token")
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        claims = ProposalClaims(
            alias=str(data["alias"]),
            text=str(data["text"]),
            category=str(data["category"]),
            priority=str(data["priority"]),
            office=str(data["office"]),
            hint_id=None if data["hint_id"] is None else str(data["hint_id"]),
            exp=int(data["exp"]),
            replaces=None if data.get("replaces") is None else str(data["replaces"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError, binascii.Error) as exc:
        raise InvalidInput("invalid proposal token") from exc
    if claims.alias != alias or not alias:
        raise InvalidInput("this proposal belongs to another user")
    if now.timestamp() >= claims.exp:
        raise InvalidInput("this proposal has expired")
    return claims
