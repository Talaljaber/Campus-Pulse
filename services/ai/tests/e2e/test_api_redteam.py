"""P4.11 over HTTP: `POST /v1/redteam/run` through `ApiServices.redteam`, and the stored runs in
`GET /v1/metrics` `redteam` (newest first)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fixtures.api import api_client, auth
from fixtures.backend_fakes import FrozenClock
from fixtures.redteam import MAX_N, KeywordCore, redteam_use_case

from campuspulse_ai.adapters.memory.null import NullMemoryStore
from campuspulse_ai.adapters.reports.json_reports import JsonReportsSource
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.application.dto import MetricsResponse, ScorecardOut
from campuspulse_ai.application.use_cases.metrics import MetricsUseCase
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.domain.entities import Scorecard


def test_admin_runs_the_red_team_and_metrics_lists_it(tmp_path: Path) -> None:
    clock = FrozenClock()
    repo = InMemoryRepository(clock)
    redteam = redteam_use_case(KeywordCore(), repo=repo, clock=clock, memory=True)
    metrics = MetricsUseCase(JsonReportsSource(tmp_path), repo, NullMemoryStore(), None)
    client = api_client(services=ApiServices(redteam=redteam, metrics=metrics))

    body = {"n": 20, "styles": ["fake_urgency", "injection", "off_topic", "typos"], "seed": 42}
    r = client.post("/v1/redteam/run", json=body, headers=auth("admin"))
    assert r.status_code == 200, r.text
    card = ScorecardOut.model_validate(r.json())
    assert (card.n, card.seed, card.created_at) == (20, 42, clock.at)
    assert list(card.by_style) == ["fake_urgency", "typos", "injection", "off_topic"]
    assert card.by_style["injection"] == 1.0 and card.by_style["off_topic"] == 1.0

    again = client.post("/v1/redteam/run", json=body, headers=auth("admin")).json()
    assert {k: v for k, v in again.items() if k != "run_id"} == {
        k: v for k, v in r.json().items() if k != "run_id"
    }

    m = client.get("/v1/metrics", headers=auth("admin"))
    assert m.status_code == 200
    history = MetricsResponse.model_validate(m.json()).redteam
    assert {h.run_id for h in history} == {card.run_id, again["run_id"]} and len(history) == 2


def test_bad_requests_are_422_and_nothing_is_stored() -> None:
    repo = InMemoryRepository(FrozenClock())
    client = api_client(services=ApiServices(redteam=redteam_use_case(KeywordCore(), repo=repo)))
    too_many = client.post("/v1/redteam/run", json={"n": MAX_N + 1}, headers=auth("admin"))
    assert too_many.status_code == 422 and too_many.json()["error"]["code"] == "invalid_input"
    unknown = client.post("/v1/redteam/run", json={"n": 5, "styles": ["sarcasm"]}, headers=auth("admin"))
    assert unknown.status_code == 422 and "sarcasm" in unknown.json()["error"]["message"]
    assert client.post("/v1/redteam/run", json={"n": 0}, headers=auth("admin")).status_code == 422
    assert repo.redteam_history() == []


def test_staff_cannot_run_it_and_an_unwired_service_is_501() -> None:
    wired = api_client(services=ApiServices(redteam=redteam_use_case(KeywordCore())))
    assert wired.post("/v1/redteam/run", json={"n": 5}, headers=auth("staff", office="it")).status_code == 403
    r = api_client(services=ApiServices()).post("/v1/redteam/run", json={"n": 5}, headers=auth("admin"))
    assert r.status_code == 501 and r.json()["error"]["details"]["component"] == "the red team"


def test_metrics_history_is_newest_first_and_skips_a_run_that_breaks_the_contract(tmp_path: Path) -> None:
    clock = FrozenClock()
    repo = InMemoryRepository(clock)
    old = repo.save_redteam_run(
        Scorecard("", {"typos": 1.0}, {"en": 1.0}, 1.0, created_at=clock.at, n=3, seed=1)
    )
    new = repo.save_redteam_run(
        Scorecard(
            "", {"typos": 0.5}, {"en": 0.5}, 0.5, created_at=clock.at + timedelta(minutes=1), n=4, seed=2
        )
    )
    repo.save_redteam_run(
        Scorecard(
            "",
            {"typos": 0.0},
            {"en": 0.0},
            0.0,
            [{"text": "no other keys"}],
            created_at=clock.at - timedelta(minutes=1),
            n=1,
            seed=3,
        )  # fmt: skip
    )
    out = MetricsUseCase(JsonReportsSource(tmp_path), repo, NullMemoryStore(), None).run()
    assert [(s.run_id, s.n, s.seed) for s in out.redteam] == [(new, 4, 2), (old, 3, 1)]
