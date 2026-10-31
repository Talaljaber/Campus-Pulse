"""P4.12: MetricsUseCase (`/v1/metrics`) over JsonReportsSource, InMemoryRepository and live memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fixtures.api import api_client, auth
from fixtures.containers import build_test

from campuspulse_ai.adapters.memory.null import NullMemoryStore
from campuspulse_ai.adapters.reports.json_reports import JsonReportsSource
from campuspulse_ai.application.dto import MetricsResponse
from campuspulse_ai.application.use_cases.metrics import MetricsUseCase
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.values import ArtifactVersion

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "api" / "metrics.json"
ARTIFACT = ArtifactVersion(name="v1", sha256="ab" * 32)
OFFLINE_KEYS = ("benchmark", "coverage", "calibration", "fairness", "ablations", "confusions")


def report() -> dict[str, Any]:
    """The offline sections of the contract fixture: the shape evaluate.py must write."""
    response: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]
    keep = (*OFFLINE_KEYS, "generated_at", "ask_rate", "ask_rate_is_proxy")
    return {k: response[k] for k in keep}


def metrics(tmp_path: Path, content: str | None) -> MetricsResponse:
    if content is not None:
        (tmp_path / "model_lab.json").write_text(content, encoding="utf-8")
    c = build_test()
    use_case = MetricsUseCase(JsonReportsSource(tmp_path), c.repo, NullMemoryStore(), ARTIFACT)
    return use_case.run()


def test_report_sections_and_live_stats(tmp_path: Path) -> None:
    out = metrics(tmp_path, json.dumps(report()))
    expected = report()
    for key in OFFLINE_KEYS:
        assert len(getattr(out, key)) == len(expected[key]), key
    assert out.ask_rate == expected["ask_rate"] and out.generated_at is not None
    assert (out.artifact.version, out.artifact.sha) == ("v1", ARTIFACT.sha256)
    assert out.router.total == 0 and out.router.cost_per_1k_usd == 0.0
    assert out.memory.active == 0 and out.redteam == []


def test_no_report_yet_gives_empty_sections(tmp_path: Path) -> None:
    out = metrics(tmp_path, None)
    assert all(getattr(out, k) == [] for k in OFFLINE_KEYS)
    assert (out.generated_at, out.ask_rate, out.ask_rate_is_proxy) == (None, None, True)


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_an_unreadable_report_never_fails_the_page(tmp_path: Path, content: str) -> None:
    with pytest.raises(InvalidInput):
        (tmp_path / "model_lab.json").write_text(content, encoding="utf-8")
        JsonReportsSource(tmp_path).load()
    out = metrics(tmp_path, content)
    assert out.benchmark == []


def test_one_bad_section_is_dropped_and_the_rest_kept(tmp_path: Path) -> None:
    data = report()
    data["coverage"] = [{"target": "category", "coverage": 7}]
    data["ask_rate"] = 3.5
    out = metrics(tmp_path, json.dumps(data))
    assert out.coverage == [] and out.benchmark and out.ask_rate is None


def test_route_is_admin_only(tmp_path: Path) -> None:
    c = build_test()
    use_case = MetricsUseCase(JsonReportsSource(tmp_path), c.repo, NullMemoryStore(), None)
    client = api_client(services=ApiServices(metrics=use_case))
    assert client.get("/v1/metrics", headers=auth("staff", office="it")).status_code == 403
    r = client.get("/v1/metrics", headers=auth("admin"))
    assert r.status_code == 200 and r.json()["artifact"] == {"version": "none", "sha": ""}
