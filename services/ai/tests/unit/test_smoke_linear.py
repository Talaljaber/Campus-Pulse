"""P4.0: scripts/smoke_linear.py refuses without a key or --yes, and against a mocked Linear it runs every
check and archives what it created. respx blocks the network, so no test here reaches Linear."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "smoke_linear.py"
API = "https://api.linear.app/graphql"
KEY = "lin_api_test_key_never_printed"


@pytest.fixture
def smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_linear_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    return module


def env_file(tmp_path: Path) -> Path:
    path = tmp_path / "test.env"
    path.write_text(f"LINEAR_API_KEY={KEY}\n", encoding="utf-8")
    return path


def test_refuses_without_a_key(smoke: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main(["--env-file", str(tmp_path / "missing.env"), "--yes"]) == smoke.EXIT_REFUSED
    assert "LINEAR_API_KEY is not set" in capsys.readouterr().out


def test_refuses_without_yes(smoke: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post(API)
        assert smoke.main(["--env-file", str(env_file(tmp_path))]) == smoke.EXIT_REFUSED
        assert not route.called
    assert KEY not in capsys.readouterr().out


class FakeLinear:
    """Answers each operation by name, keeping one issue's state like Linear would."""

    def __init__(self) -> None:
        self.issue: dict[str, Any] | None = None
        self.ops: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == KEY
        body = json.loads(request.content)
        op = body["query"].split()[1].split("(")[0]
        self.ops.append(op)
        v = body["variables"]
        if op == "CampusPulseViewer":
            data: dict[str, Any] = {"viewer": {"id": "u1", "admin": True}}
        elif op == "CampusPulseTeams":
            states = [
                {"id": f"st-{t}", "name": t, "type": t, "position": i}
                for i, t in enumerate(
                    ["backlog", "unstarted", "started", "completed", "canceled", "duplicate"]
                )
            ]
            data = {
                "teams": {
                    "nodes": [{"id": "team-cdp", "key": "CDP", "name": "CDP", "states": {"nodes": states}}]
                }
            }
        elif op == "CampusPulseLabels":
            names = [
                "registration",
                "it-support",
                "finance",
                "transportation",
                "facilities",
                "academic-support",
            ]
            data = {"issueLabels": {"nodes": [{"id": f"lb-{n}", "name": n} for n in names]}}
        elif op == "CampusPulseIssueCreate":
            i = v["input"]
            self.issue = {"id": i["id"], "identifier": "CDP-9", "url": "https://linear.app/x/CDP-9",
                          "priority": i["priority"], "state": {"type": "backlog"}}  # fmt: skip
            data = {"issueCreate": {"success": True, "issue": self.issue}}
        elif op in {"CampusPulseIssue", "CampusPulseIssueState"}:
            data = {"issue": self.issue}
        elif op == "CampusPulseIssueUpdate":
            assert self.issue is not None
            self.issue["priority"] = v["input"]["priority"]
            self.issue["state"] = {"type": v["input"]["stateId"].removeprefix("st-")}
            data = {"issueUpdate": {"success": True, "issue": self.issue}}
        elif op == "CampusPulseIssueArchive":
            data = {"issueArchive": {"success": True}}
        else:
            raise AssertionError(op)
        return httpx.Response(200, json={"data": data})


def test_full_run_verifies_every_operation_and_archives(
    smoke: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeLinear()
    with respx.mock() as router:
        router.post(API).mock(side_effect=fake)
        code = smoke.main(["--env-file", str(env_file(tmp_path)), "--yes"])
    out = capsys.readouterr().out
    assert code == smoke.EXIT_OK, out
    assert "Linear OK team=CDP" in out and "archived=1" in out and KEY not in out
    assert fake.ops[-1] == "CampusPulseIssueArchive" and "CampusPulseIssueUpdate" in fake.ops
