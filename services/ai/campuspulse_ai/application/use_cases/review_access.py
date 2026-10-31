"""Who may see and resolve a review item (UD-13). The same rule as the `review_queue_read` policy
of DB migration 0012, so the API never shows or accepts more than Supabase RLS would:

- admins: every item;
- staff: the non-distress items of their own office that are unassigned or assigned to them (an
  advisor sees the academic queue plus their own students' items, never another advisor's);
- an item with no office (legacy rows written before 0012) is open to any staff member, as before.

Distress items stay admin-only (0011); `FeedbackUseCase` enforces that separately with its own
message.
"""

from __future__ import annotations

import logging

from campuspulse_ai.application.use_cases.ports import (
    ROLE_ADMIN,
    ROLE_STAFF,
    Actor,
    AdvisorDirectory,
    Identified,
)
from campuspulse_ai.domain.entities import ReviewItem
from campuspulse_ai.domain.errors import StoreError, Unauthorized

log = logging.getLogger(__name__)

REASON_DISTRESS = "distress"


def user_id_of(actor: Actor) -> str | None:
    """The actor's auth user id (None for the service token and trusted headers)."""
    return actor.user_id if isinstance(actor, Identified) else None


def caller_profile_id(actor: Actor, directory: AdvisorDirectory | None) -> str | None:
    """The caller's `profiles.id`: the verified user id, else (trusted headers) the profile with the
    caller's alias. None when neither is known; a store failure is logged and gives None."""
    user_id = user_id_of(actor)
    if user_id:
        return user_id
    if directory is None or not actor.alias:
        return None
    try:
        return directory.profile_id_of(actor.alias)
    except StoreError as exc:
        log.warning("profile of alias %s not resolved: %s", actor.alias, exc)
        return None


def may_review(actor: Actor, item: ReviewItem, profile_id: str | None) -> bool:
    """The module rule for one item (`profile_id` is the caller's, from `caller_profile_id`)."""
    if actor.role == ROLE_ADMIN:
        return True
    if actor.role != ROLE_STAFF or item.reason == REASON_DISTRESS:
        return False
    if item.office is not None and item.office != actor.office:
        return False
    return item.assignee is None or (profile_id is not None and item.assignee == profile_id)


def check_reviewer(actor: Actor, item: ReviewItem, profile_id: str | None) -> None:
    """Raise `Unauthorized` (403) unless `may_review`."""
    if not may_review(actor, item, profile_id):
        whose = "another advisor's queue" if item.assignee else f"the {item.office} office queue"
        raise Unauthorized(f"this review item is in {whose}, not yours")
