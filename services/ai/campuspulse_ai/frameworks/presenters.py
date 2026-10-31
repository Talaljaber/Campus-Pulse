"""Role-dependent views of use-case results (presentation only; no decisions are made here)."""

from __future__ import annotations

from campuspulse_ai.application.dto import TriageResponse, to_student_view

ADMIN_ONLY_FLAGS: frozenset[str] = frozenset({"priority_gaming_suspected"})
"""docs/api/README.md › Flags: visible to admin (and the service token) only."""


def triage_view(response: TriageResponse, role: str) -> TriageResponse:
    """What `role` may see of a triage/clarify response.

    student: `to_student_view` (no staff-only flags); staff: without the admin-only flags; admin and
    service: everything.
    """
    if role == "student":
        return to_student_view(response)
    if role == "staff":
        return response.model_copy(update={"flags": [f for f in response.flags if f not in ADMIN_ONLY_FLAGS]})
    return response
