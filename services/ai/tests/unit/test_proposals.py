"""P9.8: the signed proposal token (tamper, expiry, alias binding)."""

from __future__ import annotations

import base64
import json
from datetime import timedelta

import pytest
from fixtures.backend_fakes import FrozenClock

from campuspulse_ai.application.use_cases.proposals import ProposalClaims, derive_key, sign, verify
from campuspulse_ai.domain.errors import InvalidInput

KEY = derive_key("service-token")
NOW = FrozenClock().at


def claims(**changes: object) -> ProposalClaims:
    base = {
        "alias": "demo-17", "text": "my wifi is down", "category": "IT Support", "priority": "medium",
        "office": "it", "hint_id": None, "exp": int((NOW + timedelta(minutes=30)).timestamp()),
    }  # fmt: skip
    return ProposalClaims(**{**base, **changes})  # type: ignore[arg-type]


def test_round_trip_keeps_every_claim() -> None:
    original = claims(hint_id="h-1", text="الواي فاي مقطوع")
    assert verify(KEY, sign(KEY, original), "demo-17", NOW) == original


def test_key_is_sha256_of_the_prefixed_service_token() -> None:
    import hashlib

    assert derive_key("abc") == hashlib.sha256(b"cp-proposal:abc").digest()


def test_tampered_payload_or_signature_is_refused() -> None:
    token = sign(KEY, claims())
    payload, signature = token.split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["office"] = "finance"
    forged_payload = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    for bad in (
        f"{forged_payload}.{signature}",
        f"{payload}.{'0' * 64}",
        payload,
        "x.y",
        "",
        f"{payload}.{signature}.x",
    ):
        with pytest.raises(InvalidInput):
            verify(KEY, bad, "demo-17", NOW)


def test_a_token_signed_with_another_key_is_refused() -> None:
    token = sign(derive_key("another-token"), claims())
    with pytest.raises(InvalidInput):
        verify(KEY, token, "demo-17", NOW)


def test_expired_token_is_refused() -> None:
    token = sign(KEY, claims())
    verify(KEY, token, "demo-17", NOW + timedelta(minutes=29))
    with pytest.raises(InvalidInput, match="expired"):
        verify(KEY, token, "demo-17", NOW + timedelta(minutes=31))


def test_token_of_another_alias_is_refused() -> None:
    token = sign(KEY, claims())
    with pytest.raises(InvalidInput, match="another user"):
        verify(KEY, token, "demo-18", NOW)
    with pytest.raises(InvalidInput):
        verify(KEY, token, "", NOW)
