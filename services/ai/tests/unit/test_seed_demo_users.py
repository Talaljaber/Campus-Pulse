"""P9.1: the demo account list (scripts/seed_demo_users.py) is fictional, unique and demo.local only."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def load() -> object:
    spec = importlib.util.spec_from_file_location("seed_demo_users", ROOT / "scripts" / "seed_demo_users.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def test_demo_accounts_are_the_p9_roster() -> None:
    users = load().DEMO_USERS  # type: ignore[attr-defined]
    assert [u.username for u in users] == [
        "talal", "lina", "omar", "registrar", "it", "finance", "transport", "facilities", "academic", "admin",
    ]  # fmt: skip
    assert len({u.alias for u in users}) == len({u.email for u in users}) == len(users)
    assert all(u.email.endswith("@demo.local") for u in users)
    students = [u for u in users if u.role == "student"]
    assert [u.student_number for u in students] == ["20230017", "20230042", "20220311"]
    assert all(u.university_email == f"{u.username}@student.demo.local" for u in students)
    staff = [u for u in users if u.role == "staff"]
    assert [(u.alias, u.office) for u in staff][:2] == [("staff-registrar", "registrar"), ("staff-it", "it")]
    assert staff[1].display_name == "IT Desk (demo)"
    assert all(u.university_email is None for u in users if u.role != "student")
    assert "advisor@demo.local" not in {u.email for u in users}
