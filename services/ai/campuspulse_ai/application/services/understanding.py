"""Flags derived from a `RequestUnderstander` result (UD-10, P3.3a).

Use cases call `understanding_flags(u)` after `RequestUnderstander.understand(...)` and add the result
to the response flags. Pure; domain imports only.
"""

from __future__ import annotations

from campuspulse_ai.domain.values import Understanding

UNDERSTANDING_FALLBACK = "understanding_fallback"


def understanding_flags(understanding: Understanding) -> frozenset[str]:
    """`{"understanding_fallback"}` when the rule-based understander produced it (no key, an LLM error, a
    rejected reply, or an injection-flagged request); otherwise empty."""
    return frozenset({UNDERSTANDING_FALLBACK}) if understanding.source == "rules" else frozenset()
