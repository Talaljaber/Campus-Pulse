"""Every requirement line in the four requirement sets must be an exact == pin."""

import re
from pathlib import Path

PIN = re.compile(r"^[A-Za-z0-9_.\[\]-]+==[0-9][^;\s]*(\s*;.*)?$")
AI_DIR = Path(__file__).resolve().parents[2]


def test_requirements_pinned() -> None:
    files = sorted(AI_DIR.glob("requirements*.txt"))
    assert files, "no requirements files found"
    bad = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith(("#", "-r", "--")):
                continue
            if not PIN.match(s):
                bad.append(f"{f.name}: {s}")
    assert not bad, bad
