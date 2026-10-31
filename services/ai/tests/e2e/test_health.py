"""P0.7 + P3.12: the /health contract (`dto.HealthResponse`) and the no-torch import guarantee."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from fixtures.api import HEALTH, api_client, api_settings
from fixtures.containers import build_test

from campuspulse_ai import __version__
from campuspulse_ai.frameworks.fastapi_app import create_app

AI_DIR = Path(__file__).resolve().parents[2]
HEALTH_KEYS = {
    "status", "version", "artifact", "sha", "rss_mb", "encoder_loaded", "sinks", "llm_tiers", "vector_store",
}  # fmt: skip


def test_health_contract_without_services_is_degraded() -> None:
    client = TestClient(create_app(settings=api_settings()))
    for path in ("/health", "/v1/health"):
        r = client.get(path)
        assert r.status_code == 200
        body = r.json()
        assert set(body) == HEALTH_KEYS
        assert (body["status"], body["version"], body["artifact"]) == ("degraded", __version__, None)
        assert body["rss_mb"] > 0 and body["sinks"] == [] and body["encoder_loaded"] is False


def test_health_reports_the_wiring_and_needs_no_token() -> None:
    body = api_client(build_test()).get("/health").json()
    assert body["status"] == "ok"
    assert (body["artifact"], body["sha"], body["sinks"], body["llm_tiers"]) == (
        HEALTH.artifact,
        HEALTH.sha,
        ["linear"],
        ["tier1"],
    )


def test_app_import_has_no_torch() -> None:
    code = "import sys, api; sys.exit(1 if 'torch' in sys.modules else 0)"
    r = subprocess.run([sys.executable, "-c", code], cwd=AI_DIR, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
