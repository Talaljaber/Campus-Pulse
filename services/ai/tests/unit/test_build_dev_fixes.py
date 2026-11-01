"""Merge and agreement logic of scripts/build_dev_fixes.py on a 6-row fixture."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "build_dev_fixes.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_dev_fixes", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_dev_fixes"] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(i: str, persona: str, block: str, cat: str, pri: str, lang: str = "en") -> dict[str, object]:
    return {"id": i, "lang": lang, "persona": persona, "block": block, "family": "", "probe_type": "",
            "text": f"text {i}", "category": cat, "priority": pri}


def test_merge_agreement_and_splits() -> None:
    m = _load()
    authored = [
        _row("EN-A-001", "A", "headline", "Finance", "low"),
        _row("EN-A-002", "A", "headline", "Finance", "high"),
        _row("EN-A-003", "A", "implicit_urgency", "Facilities", "high"),
        _row("EN-B-001", "B", "headline", "IT Support", "medium"),
        _row("EN-B-002", "B", "probe", "none", "none"),
        _row("EN-B-003", "B", "probe", "Registration", "medium"),
    ]
    blind = [
        {"id": "EN-A-001", "category": "Finance", "priority": "low", "kind": "question"},
        {"id": "EN-A-002", "category": "Finance", "priority": "medium"},
        {"id": "EN-A-003", "category": "IT Support", "priority": "high"},
        {"id": "EN-B-001", "category": "IT Support", "priority": "medium"},
        {"id": "EN-B-002", "category": "none", "priority": "none"},
        {"id": "EN-B-003", "category": "Registration", "priority": "low"},
    ]
    rows = m.merge_rows(authored, blind)
    by = {r["dev_id"]: r for r in rows}
    assert by["EN-A-001"]["split"] == "tune" and by["EN-B-001"]["split"] == "check"
    assert by["EN-A-001"]["x_kind"] == "question"
    assert by["EN-A-002"]["priority"] == "" and by["EN-A-002"]["category"] == "Finance"
    assert by["EN-A-003"]["category"] == "" and by["EN-A-003"]["priority"] == "high"
    assert by["EN-B-003"]["priority"] == "medium"  # probe keeps the author label
    assert all(r["scenario_id"] == r["dev_id"] and r["needs_human_check"] for r in rows)
    ag = m.agreement(rows)["en"]
    assert ag["rows"] == 6 and ag["agreed_high"] == 1
    assert ag["agree_cat"] == round(4 / 5, 4)  # the "none" row has no category label to agree on
