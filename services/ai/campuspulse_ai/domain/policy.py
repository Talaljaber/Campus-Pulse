"""Pure domain policies.

- `RecipientPolicy`: the demo allow-list. Used by AllowlistedNotifier and booking attendees.
- `DefaultDecisionPolicy` (P3.1): ACCEPT / ASK / ESCALATE / HUMAN_REVIEW / OUT_OF_SCOPE / DISTRESS.
"""

from __future__ import annotations

from campuspulse_ai.domain.errors import RecipientNotAllowed


class RecipientPolicy:
    """Allow-list check for every outgoing address. An empty allow-list rejects everything."""

    def __init__(self, allowlist: frozenset[str]) -> None:
        self._allowed = frozenset(self._canonical(a) for a in allowlist if a.strip())

    @staticmethod
    def _canonical(address: str) -> str:
        return address.strip().lower()

    def check(self, address: str) -> None:
        """Raise RecipientNotAllowed unless `address` is on the allow-list."""
        if self._canonical(address) not in self._allowed:
            raise RecipientNotAllowed(f"recipient not in DEMO allow-list: {address!r}")
