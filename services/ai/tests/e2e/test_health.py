"""P0.7: the /health contract and the no-torch import guarantee."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from campuspulse_ai.frameworks.fastapi_app import create_app

AI_DIR = Path(__file__).resolve().parents[2]


def test_health_contract() -> None:
    client = TestClient(create_app())
    for path in ("/health", "/v1/health"):
        r = client.get(path)
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"status", "artifact", "rss_mb"}
        assert body["status"] == "ok" and body["artifact"] is None
        assert body["rss_mb"] > 0


def test_app_import_has_no_torch() -> None:
    code = "import sys, api; sys.exit(1 if 'torch' in sys.modules else 0)"
    r = subprocess.run([sys.executable, "-c", code], cwd=AI_DIR, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
