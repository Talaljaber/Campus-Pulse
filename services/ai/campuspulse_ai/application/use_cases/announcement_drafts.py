"""P10 staff review of incident-derived announcement drafts.

Only the persistence adapter may publish: its operation inserts the announcement and
broadcast job in one transaction. An application failure never publishes a partial draft.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from campuspulse_ai.application.use_cases.ports import Actor
from campuspulse_ai.domain.errors import InvalidInput, Unauthorized


@dataclass(frozen=True)
class AnnouncementDraft:
    id: str
    incident_id: str
    office: str
    title: str
    body: str
    status: Literal["pending", "published", "dismissed"]
    version: int
    published_announcement_id: str | None = None


class DraftStore(Protocol):
    def list_for_office(self, office: str | None) -> Sequence[AnnouncementDraft]: ...
    def get(self, draft_id: str) -> AnnouncementDraft: ...
    def suggest(self, incident_id: str, office: str, title: str, body: str) -> AnnouncementDraft: ...
    def change(
        self, draft_id: str, version: int, title: str, body: str, dismiss: bool
    ) -> AnnouncementDraft | None: ...
    def publish(self, draft_id: str, version: int, author_id: str) -> AnnouncementDraft | None: ...


class DraftConflict(Exception):
    """The draft was changed, dismissed or published by someone else."""


class AnnouncementDraftsUseCase:
    def __init__(self, store: DraftStore) -> None:
        self._store = store

    @staticmethod
    def _check(actor: Actor, draft: AnnouncementDraft) -> None:
        if actor.role == "admin" or (actor.role == "staff" and actor.office == draft.office):
            return
        raise Unauthorized("only staff of this office or an admin may manage its announcement draft")

    @staticmethod
    def _text(title: str, body: str) -> tuple[str, str]:
        title, body = title.strip(), body.strip()
        if not 1 <= len(title) <= 120 or not 1 <= len(body) <= 1000:
            raise InvalidInput("draft title must be 1..120 and body 1..1000 characters")
        return title, body

    def list(self, actor: Actor) -> Sequence[AnnouncementDraft]:
        if actor.role == "admin":
            return self._store.list_for_office(None)
        if actor.role == "staff" and actor.office:
            return self._store.list_for_office(actor.office)
        raise Unauthorized("only staff or admins may list announcement drafts")

    def edit(self, actor: Actor, draft_id: str, version: int, title: str, body: str) -> AnnouncementDraft:
        draft = self._store.get(draft_id)
        self._check(actor, draft)
        title, body = self._text(title, body)
        changed = self._store.change(draft_id, version, title, body, False)
        if changed is None:
            raise DraftConflict("draft changed; reload before editing")
        return changed

    def dismiss(self, actor: Actor, draft_id: str, version: int) -> AnnouncementDraft:
        draft = self._store.get(draft_id)
        self._check(actor, draft)
        changed = self._store.change(draft_id, version, draft.title, draft.body, True)
        if changed is None:
            raise DraftConflict("draft changed; reload before dismissing")
        return changed

    def publish(self, actor: Actor, draft_id: str, version: int, author_id: str) -> AnnouncementDraft:
        draft = self._store.get(draft_id)
        self._check(actor, draft)
        if draft.status == "published":
            return draft
        published = self._store.publish(draft_id, version, author_id)
        if published is None:
            raise DraftConflict("draft changed; reload before publishing")
        return published

    def suggest(self, incident_id: str, office: str, title: str, body: str) -> AnnouncementDraft:
        title, body = self._text(title, body)
        return self._store.suggest(incident_id, office, title, body)
