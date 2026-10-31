"""P4.4: scripts/smoke_email.py refuses unless the recipient is allow-listed AND --yes is passed.

smtplib is monkeypatched in every case, so no test here can open a socket or send mail.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from campuspulse_ai.adapters.notify import gmail_smtp

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "smoke_email.py"
INBOX = "campuspulse.support+student17@gmail.com"


@pytest.fixture
def smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[ModuleType, list[str]]:
    """The script module with an isolated env and a recording fake SMTP."""
    spec = importlib.util.spec_from_file_location("smoke_email_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)  # no repo .env: only the vars set below
    for name in ("DEMO_EMAIL_ALLOWLIST", "GMAIL_SMTP_USER", "GMAIL_APP_PASSWORD", "SMTP_PORT", "SMTP_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    opened: list[str] = []

    class Fake:
        def __init__(self, host: str, port: int, timeout: float, **_: Any) -> None:
            opened.append(f"{host}:{port}")

        def ehlo(self, name: str = "") -> tuple[int, bytes]:
            return 250, b"ok"

        def starttls(self, **_: Any) -> tuple[int, bytes]:
            return 220, b"ok"

        def login(self, user: str, password: str) -> tuple[int, bytes]:
            return 235, b"ok"

        def send_message(self, msg: Any) -> dict[str, Any]:
            return {}

        def quit(self) -> tuple[int, bytes]:
            return 221, b"bye"

        def close(self) -> None: ...

    monkeypatch.setattr(gmail_smtp.smtplib, "SMTP", Fake)
    monkeypatch.setattr(gmail_smtp.smtplib, "SMTP_SSL", Fake)
    return module, opened


def test_refuses_a_recipient_that_is_not_allow_listed(
    smoke: tuple[ModuleType, list[str]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module, opened = smoke
    monkeypatch.setenv("DEMO_EMAIL_ALLOWLIST", INBOX)
    assert module.main(["--to", "real.person@gju.edu.jo", "--yes"]) == module.EXIT_REFUSED
    assert opened == [] and "not on DEMO_EMAIL_ALLOWLIST" in capsys.readouterr().err


def test_refuses_without_yes(smoke: tuple[ModuleType, list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    module, opened = smoke
    monkeypatch.setenv("DEMO_EMAIL_ALLOWLIST", INBOX)
    monkeypatch.setenv("GMAIL_SMTP_USER", "campuspulse.support@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake-password")
    assert module.main(["--to", INBOX]) == module.EXIT_REFUSED and opened == []


def test_refuses_without_credentials(
    smoke: tuple[ModuleType, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, opened = smoke
    monkeypatch.setenv("DEMO_EMAIL_ALLOWLIST", INBOX)
    assert module.main(["--to", INBOX, "--yes"]) == module.EXIT_REFUSED and opened == []


def test_sends_through_the_chain_when_allowed(
    smoke: tuple[ModuleType, list[str]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module, opened = smoke
    monkeypatch.setenv("DEMO_EMAIL_ALLOWLIST", INBOX)
    monkeypatch.setenv("GMAIL_SMTP_USER", "campuspulse.support@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake-password")
    assert module.main(["--to", INBOX, "--yes"]) == module.EXIT_SENT
    out = capsys.readouterr().out
    assert opened == ["smtp.gmail.com:587"] and out.startswith("SMTP OK port=587 message_id=<")
    assert "fake-password" not in out
