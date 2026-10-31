"""P3.12: service-token auth, the error mapping (`frameworks/errors.py`), the counterfactual and feedback
routes, all over HTTP with `build_test()`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from fixtures.api import api_client, api_settings, auth
from fixtures.backend_fakes import FakeCore, make_core, prob_vector
from fixtures.containers import build_test

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.explain import CounterfactualUseCase
from campuspulse_ai.application.use_cases.ports import Actor
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import ArtifactMissing, StoreError
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.values import (
    ClarificationConstraint,
    Location,
    NormalizedRequest,
    ProbVector,
)

TEXT = "wifi is down in the library"
STUDENT = auth("student", "demo-17")


@dataclass
class FailingCore(FakeCore):
    error: Exception = field(default_factory=lambda: StoreError("relation requests: connection refused"))

    def classify(
        self,
        raw: str,
        picked_location: Location | None = None,
        constraints: Sequence[ClarificationConstraint] = (),
        memory: bool = True,
    ) -> tuple[NormalizedRequest, CoreResult]:
        raise self.error


class FlipExplainer:
    """Dropping "wifi" flips IT Support to Facilities."""

    def explain(self, req: NormalizedRequest, core: CoreResult, decided: tuple[Category, Priority]) -> Any:
        raise NotImplementedError

    def counterfactual(
        self, req: NormalizedRequest, drop_token: str
    ) -> tuple[Category, Priority, ProbVector, ProbVector]:
        return (
            Category.FACILITIES,
            Priority.MEDIUM,
            prob_vector(CATEGORY_LABELS, {"Facilities": 0.7}),
            prob_vector(PRIORITY_LABELS, {"medium": 0.8}),
        )


@dataclass
class RecordingFeedback:
    reviewers: list[Actor] = field(default_factory=list)

    def run(self, cmd: dto.FeedbackRequest, reviewer: Actor) -> dto.FeedbackResponse:
        self.reviewers.append(reviewer)
        raise StoreError("not needed for this test")


def error_of(r: Any) -> dict[str, Any]:
    body: dict[str, Any] = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}
    error: dict[str, Any] = body["error"]
    return error


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic dGVzdA=="}],
    ids=["missing", "wrong", "not-bearer"],
)
def test_service_token_is_required(headers: dict[str, str]) -> None:
    r = api_client(build_test()).post("/v1/triage", json={"text": TEXT}, headers=headers)
    assert r.status_code == 401 and error_of(r)["code"] == "unauthenticated"


def test_no_token_configured_on_the_server_fails_closed() -> None:
    client = api_client(build_test(), settings=api_settings(ai_service_token=None))
    r = client.post("/v1/triage", json={"text": TEXT}, headers=STUDENT)
    assert r.status_code == 401


def test_validation_and_domain_invalid_input_are_422() -> None:
    client = api_client(build_test())
    empty = client.post("/v1/triage", json={"text": ""}, headers=STUDENT)
    assert empty.status_code == 422 and error_of(empty)["details"]["errors"][0]["loc"] == ["body", "text"]
    blank = client.post("/v1/triage", json={"text": "   "}, headers=STUDENT)
    assert blank.status_code == 422 and error_of(blank)["message"] == "empty request text"
    extra = client.post("/v1/triage", json={"text": TEXT, "role": "admin"}, headers=STUDENT)
    assert extra.status_code == 422


def test_store_and_artifact_errors_are_503_without_internals() -> None:
    store = api_client(build_test(core=FailingCore()))
    r = store.post("/v1/triage", json={"text": TEXT}, headers=STUDENT)
    err = error_of(r)
    assert r.status_code == 503 and err["code"] == "store_unavailable"
    assert "connection refused" not in r.text and err["details"]["request_id"]
    artifact = api_client(build_test(core=FailingCore(error=ArtifactMissing("models/frozen/v1 missing"))))
    r = artifact.post("/v1/triage", json={"text": TEXT}, headers=STUDENT)
    assert r.status_code == 503 and error_of(r)["code"] == "artifact_unavailable" and "models/" not in r.text


def test_unexpected_errors_are_500_with_a_reference_and_no_trace() -> None:
    client = api_client(build_test(core=FailingCore(error=KeyError("secret"))), raise_server_exceptions=False)
    r = client.post("/v1/triage", json={"text": TEXT}, headers=STUDENT)
    err = error_of(r)
    assert r.status_code == 500 and err["code"] == "internal_error" and err["details"]["request_id"]
    assert "Traceback" not in r.text and "secret" not in r.text


def test_unknown_route_is_404_in_the_error_shape() -> None:
    r = api_client(build_test()).get("/v1/nope", headers=STUDENT)
    assert r.status_code == 404 and error_of(r)["code"] == "not_found"


def test_unwired_use_case_is_501() -> None:
    r = api_client().post("/v1/triage", json={"text": TEXT}, headers=STUDENT)
    assert r.status_code == 501 and error_of(r)["code"] == "not_implemented"


def test_debug_members_is_admin_only() -> None:
    client = api_client(build_test())
    student = client.post("/v1/triage?debug=members", json={"text": TEXT}, headers=STUDENT)
    assert student.status_code == 403
    admin = client.post("/v1/triage?debug=members", json={"text": TEXT}, headers=auth("admin"))
    assert admin.status_code == 200 and admin.json()["explanation"]["trace"]["per_model"] is not None


def test_a_student_caller_alias_wins_over_the_body() -> None:
    c = build_test()
    client = api_client(c)
    r = client.post("/v1/triage", json={"text": TEXT, "student_alias": "demo-99"}, headers=STUDENT)
    assert c.repo.get_request(r.json()["request_id"]).alias == "demo-17"
    service = client.post("/v1/triage", json={"text": TEXT, "student_alias": "demo-55"}, headers=auth())
    assert c.repo.get_request(service.json()["request_id"]).alias == "demo-55"


def test_counterfactual_route() -> None:
    c = build_test(core=FakeCore().add(TEXT, make_core({"IT Support": 0.9}, {"medium": 0.9})))
    client = api_client(c, counterfactual=CounterfactualUseCase(FlipExplainer(), c.repo))
    rid = client.post("/v1/triage", json={"text": TEXT}, headers=STUDENT).json()["request_id"]
    url = f"/v1/explain/{rid}/counterfactual"
    r = client.get(url, params={"drop": "WiFi"}, headers=STUDENT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["original_category"], body["category"], body["flipped"]) == (
        "IT Support",
        "Facilities",
        True,
    )
    assert body["category_prob"] == pytest.approx(0.7)
    assert client.get(url, params={"drop": "printer"}, headers=STUDENT).status_code == 422
    assert client.get(url, params={"drop": "wifi"}, headers=auth("student", "demo-99")).status_code == 403
    assert client.get(url, params={"drop": "wifi"}, headers=auth("staff", office="it")).status_code == 200
    assert client.get(url, headers=STUDENT).status_code == 422


def test_feedback_route_passes_the_caller_as_reviewer() -> None:
    handler = RecordingFeedback()
    client = api_client(build_test(), feedback=handler)
    r = client.post("/v1/feedback", json={"prediction_id": "p-1"}, headers=auth("staff", "staff-it", "it"))
    assert r.status_code == 503
    [reviewer] = handler.reviewers
    assert (reviewer.role, reviewer.office) == ("staff", "it")
    assert (
        api_client(build_test())
        .post("/v1/feedback", json={"prediction_id": "p-1"}, headers=auth("staff", office="it"))
        .status_code
        == 501
    )
