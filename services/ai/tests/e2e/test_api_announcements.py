"""P9.5 over HTTP: `POST /v1/announcements` and `/archive` (roles, office forcing, validation)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from fixtures.api import api_client, auth
from fixtures.backend_fakes import FrozenClock

from campuspulse_ai.adapters.store.announcements_inmemory import InMemoryAnnouncementStore
from campuspulse_ai.application.use_cases.announcements import AnnouncementsUseCase
from campuspulse_ai.composition.api import ApiServices

URL = "/v1/announcements"
BODY = {"title": "Library wifi is down", "body": "Use the lab network.", "kind": "outage"}
OFFICES = ("registrar", "it", "finance", "transport", "facilities", "academic")


def client() -> tuple[TestClient, InMemoryAnnouncementStore, FrozenClock]:
    store, clock = InMemoryAnnouncementStore(), FrozenClock()
    services = ApiServices(announcements=AnnouncementsUseCase(store, clock, OFFICES))
    return api_client(services=services), store, clock


def test_staff_post_is_forced_to_own_office() -> None:
    c, store, clock = client()
    r = c.post(URL, json=BODY, headers=auth("staff", office="it"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["office"], out["kind"], out["archived_at"]) == ("it", "outage", None)
    assert [a.id for a in store.live_announcements(clock.at)] == [out["id"]]
    other = c.post(URL, json={**BODY, "office": "finance"}, headers=auth("staff", office="it"))
    assert other.status_code == 403 and other.json()["error"]["code"] == "forbidden"


def test_admin_posts_campus_wide_or_for_an_office() -> None:
    c, *_ = client()
    assert c.post(URL, json=BODY, headers=auth("admin")).json()["office"] is None
    wide = c.post(URL, json={**BODY, "office": "finance"}, headers=auth("admin"))
    assert wide.json()["office"] == "finance"
    assert c.post(URL, json={**BODY, "office": "library"}, headers=auth("admin")).status_code == 422


def test_students_and_missing_token_are_refused() -> None:
    c, store, clock = client()
    assert c.post(URL, json=BODY, headers=auth("student", "lina")).status_code == 403
    assert c.post(URL, json=BODY).status_code == 401
    assert store.live_announcements(clock.at) == []


def test_validation_is_422() -> None:
    c, *_ = client()
    h = auth("admin")
    assert c.post(URL, json={**BODY, "title": ""}, headers=h).status_code == 422
    assert c.post(URL, json={**BODY, "kind": "alert"}, headers=h).status_code == 422
    assert c.post(URL, json={**BODY, "extra": 1}, headers=h).status_code == 422
    backwards = {"starts_at": "2026-11-06T10:00:00+03:00", "ends_at": "2026-11-06T09:00:00+03:00"}
    bad = c.post(URL, json={**BODY, **backwards}, headers=h)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_input"


def test_archive_roles_and_not_found() -> None:
    c, store, clock = client()
    made = c.post(URL, json=BODY, headers=auth("staff", office="it")).json()
    url = f"{URL}/{made['id']}/archive"
    assert c.post(url, headers=auth("staff", office="finance")).status_code == 403
    assert c.post(url, headers=auth("student", "lina")).status_code == 403
    r = c.post(url, headers=auth("staff", office="it"))
    assert r.status_code == 200 and r.json()["archived_at"] is not None
    assert store.live_announcements(clock.at) == []
    assert c.post(url, headers=auth("admin")).status_code == 200
    assert c.post(f"{URL}/nope/archive", headers=auth("admin")).status_code == 404


def test_unwired_is_501() -> None:
    r = api_client(services=ApiServices()).post(URL, json=BODY, headers=auth("admin"))
    assert r.status_code == 501
