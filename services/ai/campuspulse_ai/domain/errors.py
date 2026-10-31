"""Domain errors. Adapters raise only these, never SDK exceptions (ARCHITECTURE §1.3).

Use cases catch only what they can degrade (e.g. SinkError -> log and continue,
LLMUnavailable -> fall back to tier 0); routes map them to HTTP codes in one place.
"""

from __future__ import annotations


class CampusPulseError(Exception):
    """Base for every domain error."""


class InvalidInput(CampusPulseError):
    """Empty text, bad CSV columns."""


class ArtifactError(CampusPulseError):
    """Base for frozen-artifact problems."""


class ArtifactMissing(ArtifactError):
    """An expected artifact path is absent."""


class ArtifactChecksumMismatch(ArtifactError):
    """A file's sha256 differs from MANIFEST.json."""


class ArtifactVersionMismatch(ArtifactError):
    """config.json schema/version or vector dimension does not match the code."""


class LLMError(CampusPulseError):
    """Base for LLM tier problems."""


class LLMUnavailable(LLMError):
    """No key, no network, or 5xx after retries."""


class LLMOutputOutOfSet(LLMError):
    """The LLM returned a label outside the allowed conformal set, or violated the output schema."""


class RecipientNotAllowed(CampusPulseError):
    """Address is not in the demo allow-list."""


class SinkError(CampusPulseError):
    """A ticket sink failed."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class NotificationError(CampusPulseError):
    """SMTP/provider failure. 5xx/timeout are retryable; auth/4xx are not."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class CalendarUnavailable(CampusPulseError):
    """Calendar provider unreachable or not configured."""


class StoreError(CampusPulseError):
    """Persistence failure."""


class NotFound(StoreError):
    """The requested entity does not exist."""


class Unauthorized(CampusPulseError):
    """Role check failed."""


class ClarificationBudgetExceeded(CampusPulseError):
    """No clarification questions left for this request."""
