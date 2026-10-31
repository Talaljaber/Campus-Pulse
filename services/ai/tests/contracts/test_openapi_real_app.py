"""P3.12: the real app implements the frozen contract. Its OpenAPI export is byte-identical to the mock
app's and to `services/ai/openapi.json`, which the web app generates its TypeScript types from."""

from __future__ import annotations

from pathlib import Path

from campuspulse_ai.frameworks.api_contract import ENDPOINTS
from campuspulse_ai.frameworks.export_openapi import openapi_document, render

OPENAPI_FILE = Path(__file__).resolve().parents[2] / "openapi.json"


def test_real_and_mock_exports_are_identical() -> None:
    assert render(openapi_document(mock=False)) == render(openapi_document(mock=True))


def test_committed_openapi_matches_the_real_app() -> None:
    assert OPENAPI_FILE.read_text(encoding="utf-8") == render(openapi_document(mock=False))


def test_every_contract_operation_is_served() -> None:
    paths = openapi_document(mock=False)["paths"]
    served = {(m.upper(), p) for p, ops in paths.items() for m in ops}
    assert served == {(e.method, e.path) for e in ENDPOINTS}
