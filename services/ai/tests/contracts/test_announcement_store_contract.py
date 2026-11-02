"""AnnouncementStore contract (P9.5): the same cases run against every store.

SupabaseAnnouncementStore runs under `-m supabase` (SUPABASE_TEST_* env); InMemoryAnnouncementStore always.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fixtures.backend_fakes import AMMAN
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.store.announcements_inmemory import InMemoryAnnouncementStore
from campuspulse_ai.application.use_cases.announcement_ports import AnnouncementStore
from campuspulse_ai.domain.announcements import Announcement
from campuspulse_ai.domain.errors import NotFound

NOW = datetime(2026, 11, 5, 9, 5, tzinfo=AMMAN)


class Harness:
    def __init__(self) -> None:
        self.store: AnnouncementStore = InMemoryAnnouncementStore()
        self.ids: list[str] = []

    def close(self) -> None:
        pass


class PgHarness(Harness):
    def __init__(self) -> None:
        from campuspulse_ai.adapters.store.announcements_supabase import SupabaseAnnouncementStore

        super().__init__()
        self.client: Any = supabase_test_client()
        self.store = SupabaseAnnouncementStore(self.client)

    def close(self) -> None:
        for id in self.ids:
            self.client.table("announcements").delete().eq("id", id).execute()


@pytest.fixture(params=[pytest.param(PgHarness, marks=pytest.mark.supabase), pytest.param(Harness)])
def h(request: pytest.FixtureRequest) -> Iterator[Harness]:
    harness: Harness = request.param()
    yield harness
    harness.close()


def make(h: Harness, **kw: Any) -> Announcement:
    base = Announcement(
        id=str(uuid.uuid4()),
        office="it",
        kind="info",
        title="t",
        body="b",
        starts_at=NOW - timedelta(hours=1),
    )
    saved = h.store.save_announcement(dataclasses.replace(base, **kw))
    h.ids.append(saved.id)
    return saved


def test_save_mints_an_id_and_get_round_trips(h: Harness) -> None:
    saved = make(h, id="", office=None, ends_at=NOW + timedelta(days=1))
    assert saved.id
    got = h.store.get_announcement(saved.id)
    assert (got.office, got.kind, got.title, got.ends_at) == (None, "info", "t", NOW + timedelta(days=1))
    assert got.archived_at is None


def test_get_unknown_is_not_found(h: Harness) -> None:
    with pytest.raises(NotFound):
        h.store.get_announcement(str(uuid.uuid4()))


def test_save_is_an_upsert_by_id(h: Harness) -> None:
    saved = make(h)
    h.store.save_announcement(dataclasses.replace(saved, title="changed", archived_at=NOW))
    got = h.store.get_announcement(saved.id)
    assert (got.title, got.archived_at) == ("changed", NOW)


def test_live_filters_and_orders_newest_first(h: Harness) -> None:
    older = make(h, title="older", starts_at=NOW - timedelta(hours=5))
    newer = make(h, title="newer", starts_at=NOW - timedelta(hours=1), ends_at=NOW + timedelta(hours=1))
    ended = make(h, title="ended", ends_at=NOW - timedelta(minutes=1))
    future = make(h, title="future", starts_at=NOW + timedelta(hours=1))
    archived = make(h, title="archived", archived_at=NOW - timedelta(minutes=5))
    mine = {older.id, newer.id, ended.id, future.id, archived.id}
    live = [a.id for a in h.store.live_announcements(NOW, limit=200) if a.id in mine]
    assert live == [newer.id, older.id]


def test_live_respects_the_limit(h: Harness) -> None:
    for i in range(3):
        make(h, starts_at=NOW - timedelta(minutes=i + 1))
    assert len(h.store.live_announcements(NOW, limit=2)) == 2
