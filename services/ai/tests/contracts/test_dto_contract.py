"""P0.13 contract tests: fixtures <-> DTOs <-> openapi.json <-> mock app.

- every fixture validates against its endpoint's request and response DTOs (or the error body);
- every OpenAPI operation has at least one 2xx fixture, and every SPEC §7 triage status has one;
- the committed `services/ai/openapi.json` equals the mock app's document (re-export if this fails);
- the mock app answers every fixture with exactly the fixture's status and body;
- DTO Literals mirror the domain Literals; fixtures contain no real addresses.
"""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
import typing
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, TypeAdapter

from campuspulse_ai.application import dto
from campuspulse_ai.domain import entities, values
from campuspulse_ai.frameworks.api_contract import ENDPOINTS, EndpointDoc
from campuspulse_ai.frameworks.export_openapi import render
from campuspulse_ai.frameworks.mock_app import MOCK_FIXTURE_HEADER, create_mock_app

SERVICE_AI = Path(__file__).resolve().parents[2]
FIXTURES_DIR = SERVICE_AI / "tests" / "fixtures" / "api"
OPENAPI_PATH = SERVICE_AI / "openapi.json"

REQUEST_MODELS: dict[str, type[BaseModel] | None] = {
    "triage": dto.TriageRequest,
    "clarify": dto.ClarifyRequest,
    "explain_counterfactual": None,
    "cron_sla": None,
    "feedback": dto.FeedbackRequest,
    "ticket_status": dto.TicketStatusRequest,
    "ticket_forward": dto.ForwardRequest,
    "list_reviews": None,
    "review_forward": dto.ForwardRequest,
    "list_incidents": None,
    "resolve_incident": dto.ResolveIncidentRequest,
    "insights_recurring": None,
    "linear_webhook": None,  # Linear's own payload, verified by HMAC
    "batch": None,  # multipart, checked separately
    "redteam_run": dto.RedTeamRunRequest,
    "metrics": None,
    "health": None,
    "health_root": None,
    "admin_simulate": dto.SimulateRequest,
    "admin_reindex": dto.ReindexRequest,
    "ticket_comment": dto.CommentRequest,
    "ticket_priority": dto.PriorityRequest,
    "ticket_student_action": dto.StudentActionRequest,
    "announcement_create": dto.AnnouncementIn,
    "announcement_archive": None,
}
QUERY_MODELS: dict[str, type[BaseModel]] = {
    "triage": dto.TriageQuery,
    "explain_counterfactual": dto.CounterfactualQuery,
    "list_incidents": dto.IncidentListQuery,
    "insights_recurring": dto.RecurringQuery,
    "list_reviews": dto.ReviewListQuery,
}


def _load() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES_DIR.glob("*.json"))]


FIXTURES = _load()


def _endpoint(fixture: dict[str, Any]) -> EndpointDoc:
    hits = [e for e in ENDPOINTS if e.method == fixture["method"] and e.path == fixture["path"]]
    assert len(hits) == 1, f"{fixture['name']}: no endpoint {fixture['method']} {fixture['path']}"
    return hits[0]


def _url(fixture: dict[str, Any], path: str | None = None) -> str:
    url = path or fixture["path"]
    for key, value in fixture["path_params"].items():
        url = url.replace("{" + key + "}", value)
    return url


def test_fixtures_exist_and_are_well_formed() -> None:
    assert FIXTURES, f"no fixtures in {FIXTURES_DIR}"
    names = set()
    for f, path in zip(FIXTURES, sorted(FIXTURES_DIR.glob("*.json")), strict=True):
        assert f["name"] == path.stem, f"{path.name}: name must equal the file stem"
        assert f["name"] not in names
        names.add(f["name"])
        assert {"description", "method", "path", "status_code", "response"} <= set(f)
        assert re.findall(r"\{(\w+)\}", f["path"]) == list(f["path_params"]), f["name"]


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_fixture_validates_against_its_dto(fixture: dict[str, Any]) -> None:
    endpoint = _endpoint(fixture)
    request_model = REQUEST_MODELS[endpoint.op_id]
    if request_model is not None and fixture["status_code"] != 422:
        request_model.model_validate(fixture["request"])
    if endpoint.op_id in QUERY_MODELS:
        QUERY_MODELS[endpoint.op_id].model_validate(fixture["query"])

    status = fixture["status_code"]
    if status >= 400:
        body = dto.ErrorResponse.model_validate(fixture["response"])
        assert dto.ERROR_HTTP_STATUS[body.error.code] == status
        from campuspulse_ai.frameworks.api_contract import endpoint_errors

        assert body.error.code in endpoint_errors(endpoint), f"{body.error.code} not documented"
        return
    assert status == endpoint.status_code
    if endpoint.op_id == "batch":
        rows = list(csv.reader(io.StringIO(fixture["response"])))
        assert tuple(rows[0]) == dto.BATCH_CSV_COLUMNS
        for row in rows[1:]:
            dto.BatchRow.model_validate(dict(zip(dto.BATCH_CSV_COLUMNS, row, strict=True)))
        upload = fixture["request"]["files"]["file"]["content"]
        assert tuple(next(csv.reader(io.StringIO(upload)))) == dto.BATCH_INPUT_COLUMNS
        return
    assert endpoint.response_model is not None
    TypeAdapter(endpoint.response_model).validate_python(fixture["response"])


def test_every_openapi_operation_has_a_success_fixture() -> None:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    covered = set()
    for f in FIXTURES:
        if f["status_code"] < 400:
            for path in (f["path"], *f.get("alias_paths", [])):
                covered.add((f["method"].lower(), path))
    operations = {(m, p) for p, ops in document["paths"].items() for m in ops}
    assert operations, "openapi.json has no paths"
    assert operations <= covered, f"operations without a 2xx fixture: {sorted(operations - covered)}"
    assert all(p.startswith("/v1/") or p == "/health" for _, p in operations)


def test_every_triage_status_has_a_fixture() -> None:
    seen = {
        f["response"]["status"]
        for f in FIXTURES
        if f["path"] in ("/v1/triage", "/v1/triage/{request_id}/clarify") and f["status_code"] == 200
    }
    assert seen == {s.value for s in dto.TRIAGE_STATUSES}


def test_committed_openapi_matches_the_mock_app() -> None:
    expected = render(create_mock_app().openapi())
    actual = OPENAPI_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "services/ai/openapi.json is stale: run "
        "`python -m campuspulse_ai.frameworks.export_openapi --mock --out services/ai/openapi.json`"
    )


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_mock_app(FIXTURES_DIR))


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_mock_app_serves_the_fixture(client: TestClient, fixture: dict[str, Any]) -> None:
    endpoint = _endpoint(fixture)
    headers = {MOCK_FIXTURE_HEADER: fixture["name"], **fixture["headers"]}
    if endpoint.auth == "service_token" and not fixture.get("omit_auth"):
        headers["Authorization"] = "Bearer test-token"
    for path in (fixture["path"], *fixture.get("alias_paths", [])):
        kwargs: dict[str, Any] = {"headers": headers, "params": fixture["query"]}
        if endpoint.op_id == "batch":
            upload = fixture["request"]["files"]["file"]
            kwargs["files"] = {"file": (upload["filename"], upload["content"].encode("utf-8"), "text/csv")}
            kwargs["data"] = fixture["request"]["form"]
        elif fixture["request"] is not None:
            kwargs["json"] = fixture["request"]
        response = client.request(fixture["method"], _url(fixture, path), **kwargs)
        assert response.status_code == fixture["status_code"], response.text
        if endpoint.op_id == "batch" and response.status_code < 400:
            assert response.headers["content-type"].startswith("text/csv")
            assert response.text == fixture["response"]
        else:
            assert response.json() == fixture["response"]


def test_mock_app_selects_triage_fixture_by_text(client: TestClient) -> None:
    by_text = [f for f in FIXTURES if f["path"] == "/v1/triage" and f["status_code"] == 200]
    for f in by_text:
        body = {**f["request"], "text": "  " + f["request"]["text"].upper() + " "}
        r = client.post("/v1/triage", json=body, headers={"Authorization": "Bearer t"})
        assert r.json()["request_id"] == f["response"]["request_id"], f["name"]
    r = client.post("/v1/triage", json={"text": "something new"}, headers={"Authorization": "Bearer t"})
    default = next(f for f in by_text if f.get("default"))
    assert r.json() == default["response"]


def test_mock_app_enforces_roles(client: TestClient) -> None:
    r = client.get("/v1/metrics", headers={"Authorization": "Bearer t", "X-CP-Role": "staff"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    ("dto_literal", "owner", "field"),
    [
        (dto.InputMode, entities.Request, "input_mode"),
        (dto.NeighborSource, values.Neighbor, "source"),
        (dto.UnderstandingSource, values.Understanding, "source"),
        (dto.IncidentStatus, entities.Incident, "status"),
        (dto.ReviewStatus, entities.ReviewItem, "status"),
    ],
)
def test_dto_literals_mirror_the_domain(dto_literal: Any, owner: type, field: str) -> None:
    assert typing.get_args(dto_literal) == typing.get_args(typing.get_type_hints(owner)[field])


def test_triage_statuses_are_request_statuses() -> None:
    assert set(typing.get_args(dto.TriageStatus)) == set(dto.TRIAGE_STATUSES)
    assert set(dto.TRIAGE_STATUSES) <= set(values.RequestStatus)


def test_student_view_strips_staff_only_flags() -> None:
    fixture = next(f for f in FIXTURES if f["name"] == "triage_decided_en_injection")
    staff = dto.TriageResponse.model_validate(
        {**fixture["response"], "flags": ["injection_attempt", "urgency_unsupported"]}
    )
    assert dto.to_student_view(staff).flags == ["injection_attempt"]
    assert dto.STAFF_ONLY_FLAGS <= values.FLAGS and dto.DEBUG_ONLY_FLAGS <= values.FLAGS


def test_error_codes_map_domain_errors() -> None:
    from campuspulse_ai.domain import errors

    assert dto.error_code_for(errors.NotFound("x")) is dto.ErrorCode.NOT_FOUND
    assert dto.error_code_for(errors.StoreError("x")) is dto.ErrorCode.STORE_UNAVAILABLE
    assert dto.error_code_for(errors.ArtifactMissing("x")) is dto.ErrorCode.ARTIFACT_UNAVAILABLE
    assert dto.error_code_for(RuntimeError("x")) is dto.ErrorCode.INTERNAL_ERROR
    assert set(dto.ERROR_HTTP_STATUS) == set(dto.ErrorCode)


def test_fixtures_contain_no_real_addresses_or_secrets() -> None:
    text = "\n".join(p.read_text(encoding="utf-8") for p in FIXTURES_DIR.glob("*.json"))
    for address in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
        assert address.endswith("@example.com"), address
    assert "gju.edu" not in text.lower()
    assert not re.search(r"sk-or-|sk-ant-|service_role|eyJhbGci", text)


def test_generated_endpoint_docs_are_current() -> None:
    repo_root = SERVICE_AI.parents[1]
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "gen_api_docs.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
