"""AnnouncementsUseCase (P9.5): who may post and archive, office forcing, date validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from fixtures.backend_fakes import FrozenClock

from campuspulse_ai.adapters.store.announcements_inmemory import InMemoryAnnouncementStore
from campuspulse_ai.application.use_cases.announcements import AnnouncementsUseCase
from campuspulse_ai.domain.announcements import NewAnnouncement
from campuspulse_ai.domain.errors import InvalidInput, NotFound, Unauthorized

OFFICES = ("registrar", "it", "finance", "transport", "facilities", "academic")


@dataclass(frozen=True)
class Who:
    role: str
    office: str | None = None
    alias: str | None = None


IT = Who("staff", "it")
FINANCE = Who("staff", "finance")
ADMIN = Who("admin")
STUDENT = Who("student", alias="lina")


def setup() -> tuple[AnnouncementsUseCase, InMemoryAnnouncementStore, FrozenClock]:
    store, clock = InMemoryAnnouncementStore(), FrozenClock()
    return AnnouncementsUseCase(store, clock, OFFICES), store, clock


def cmd(**kw: Any) -> NewAnnouncement:
    return NewAnnouncement(**{"title": " Wifi down ", "body": "Library wifi is down.", **kw})


def test_staff_post_is_forced_to_their_office() -> None:
    uc, store, clock = setup()
    a = uc.create(IT, cmd(), created_by="u1")
    assert (a.office, a.title, a.kind, a.starts_at, a.created_by) == (
        "it",
        "Wifi down",
        "info",
        clock.at,
        "u1",
    )
    assert uc.create(IT, cmd(office="it")).office == "it"
    assert store.get_announcement(a.id) == a


def test_staff_cannot_post_for_another_office_or_without_office() -> None:
    uc, *_ = setup()
    with pytest.raises(Unauthorized):
        uc.create(IT, cmd(office="finance"))
    with pytest.raises(Unauthorized):
        uc.create(Who("staff", None), cmd())
    with pytest.raises(Unauthorized):
        uc.create(STUDENT, cmd())


def test_admin_posts_for_any_office_or_campus_wide() -> None:
    uc, *_ = setup()
    assert uc.create(ADMIN, cmd(office="finance")).office == "finance"
    assert uc.create(ADMIN, cmd()).office is None
    with pytest.raises(InvalidInput):
        uc.create(ADMIN, cmd(office="library"))


def test_validation() -> None:
    uc, _, clock = setup()
    with pytest.raises(InvalidInput):
        uc.create(IT, cmd(ends_at=clock.at))  # not after starts_at (default now)
    with pytest.raises(InvalidInput):
        uc.create(IT, cmd(starts_at=clock.at + timedelta(hours=2), ends_at=clock.at + timedelta(hours=1)))
    with pytest.raises(InvalidInput):
        uc.create(IT, cmd(title="   "))
    with pytest.raises(InvalidInput):
        uc.create(IT, cmd(body="x" * 1001))
    with pytest.raises(InvalidInput):
        uc.create(IT, cmd(kind="alert"))
    ok = uc.create(IT, cmd(ends_at=clock.at + timedelta(days=7)))
    assert ok.ends_at == clock.at + timedelta(days=7)


def test_archive_by_office_staff_or_admin_only() -> None:
    uc, store, clock = setup()
    a = uc.create(IT, cmd())
    with pytest.raises(Unauthorized):
        uc.archive(FINANCE, a.id)
    with pytest.raises(Unauthorized):
        uc.archive(STUDENT, a.id)
    done = uc.archive(IT, a.id)
    assert done.archived_at == clock.at and store.live_announcements(clock.at) == []
    assert uc.archive(ADMIN, a.id).archived_at == clock.at  # idempotent
    wide = uc.create(ADMIN, cmd())
    with pytest.raises(Unauthorized):
        uc.archive(IT, wide.id)  # campus-wide: admin only
    assert uc.archive(ADMIN, wide.id).archived_at is not None


def test_archive_unknown_is_not_found() -> None:
    uc, *_ = setup()
    with pytest.raises(NotFound):
        uc.archive(ADMIN, "nope")
