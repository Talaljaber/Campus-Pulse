"""P4.12: `/v1/batch` — the predictions CSV format (predict.py contract) and the route."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient
from fixtures.api import api_client, api_settings, auth

from campuspulse_ai.application.use_cases.batch import (
    BatchCsvUseCase,
    read_batch_csv,
    write_predictions_csv,
)
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.domain.errors import ArtifactMissing, InvalidInput

CSV = "request_id,text,extra\nr-001,where is the bus timetable?,x\nr-002,مش قادر أسجل مادة,y\n"


@dataclass
class FakeLabeler:
    """Transportation x low for every row; records the calls."""

    calls: list[tuple[list[tuple[str, str]], bool]] = field(default_factory=list)
    error: Exception | None = None

    def label(self, rows: Sequence[tuple[str, str]], *, use_llm: bool) -> list[tuple[str, str, str]]:
        self.calls.append((list(rows), use_llm))
        if self.error is not None:
            raise self.error
        return [(rid, "Transportation", "low") for rid, _ in rows]


def test_read_accepts_a_bom_ignores_extra_columns_and_keeps_values() -> None:
    rows = read_batch_csv(("﻿" + CSV).encode("utf-8"), max_rows=10)
    assert rows == [("r-001", "where is the bus timetable?"), ("r-002", "مش قادر أسجل مادة")]
    assert read_batch_csv(b"request_id,text\n r-3 ,\n", max_rows=10) == [(" r-3 ", "")]


@pytest.mark.parametrize(
    "data",
    [
        b"id,text\nr-1,hi\n",
        b"",
        "request_id,text\nr-1,\xe9\n".encode("latin-1"),
        b"request_id,text\n1,a\n2,b\n3,c\n",
    ],
    ids=["missing-column", "empty", "not-utf8", "too-many-rows"],
)
def test_read_rejects_bad_files(data: bytes) -> None:
    with pytest.raises(InvalidInput):
        read_batch_csv(data, max_rows=2)


def test_write_is_the_predict_py_format() -> None:
    out = write_predictions_csv([("r-1", "IT Support", "high"), ('id,"2"', "Finance", "low")])
    assert out == b'request_id,category,priority\nr-1,IT Support,high\n"id,""2""",Finance,low\n'
    assert not out.startswith(b"\xef\xbb\xbf") and b"\r" not in out


def test_use_case_keeps_order_and_passes_use_llm() -> None:
    labeler = FakeLabeler()
    out = BatchCsvUseCase(labeler, max_rows=10).run(CSV.encode("utf-8"), use_llm=True)
    assert out.decode("utf-8").splitlines()[1:] == ["r-001,Transportation,low", "r-002,Transportation,low"]
    assert labeler.calls[0][1] is True


def test_a_labeler_that_drops_rows_is_a_server_bug() -> None:
    class Dropping(FakeLabeler):
        def label(self, rows: Sequence[tuple[str, str]], *, use_llm: bool) -> list[tuple[str, str, str]]:
            return super().label(rows, use_llm=use_llm)[:1]

    with pytest.raises(RuntimeError):
        BatchCsvUseCase(Dropping(), max_rows=10).run(CSV.encode("utf-8"))


def client_for(labeler: FakeLabeler, **settings: object) -> TestClient:
    services = ApiServices(batch=BatchCsvUseCase(labeler, max_rows=10))
    return api_client(services=services, settings=api_settings(**settings), raise_server_exceptions=False)


def post(client: TestClient, data: bytes, role: str = "staff", **form: str) -> httpx.Response:
    files = {"file": ("requests.csv", data, "text/csv")}
    return client.post("/v1/batch", files=files, data=form, headers=auth(role, office="it"))


def test_route_returns_csv_bytes() -> None:
    labeler = FakeLabeler()
    r = post(client_for(labeler), CSV.encode("utf-8"), use_llm="true")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content == b"request_id,category,priority\nr-001,Transportation,low\nr-002,Transportation,low\n"
    assert labeler.calls[0][1] is True


def test_route_errors() -> None:
    client = client_for(FakeLabeler(), batch_max_bytes=20)
    assert post(client, CSV.encode("utf-8")).status_code == 422
    small = client_for(FakeLabeler())
    assert post(small, b"id,text\n1,a\n").status_code == 422
    assert post(small, CSV.encode("utf-8"), role="student").status_code == 403
    broken = client_for(FakeLabeler(error=ArtifactMissing("no model")))
    assert post(broken, CSV.encode("utf-8")).status_code == 503
    assert post(api_client(), CSV.encode("utf-8")).status_code == 501
