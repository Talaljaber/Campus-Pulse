"""P8.1b model panel: the conservative decision rule and the vote parser (no network)."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest

from campuspulse_ai.config.paths import REPO_ROOT


@pytest.fixture(scope="module")
def mp() -> ModuleType:
    spec = importlib.util.spec_from_file_location("model_panel", REPO_ROOT / "scripts" / "model_panel.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rec(draft: str, check: str, new: tuple[str, str, str], file: str = "new_scenarios.csv", *,
         nat: tuple[str, str, str] = ("True", "True", "True"), check_nat: str = "True") -> dict[str, str]:
    dc, dp = draft.split("/")
    cc, cp = check.split("/") if check else ("", "")
    rec = {"file": file, "draft_category": dc, "draft_priority": dp, "check_category": cc,
           "check_priority": cp, "check_natural": check_nat if check else ""}
    for k, lab, n in zip(("gpt", "qwen", "glm"), new, nat, strict=True):
        rec[f"{k}_category"], rec[f"{k}_priority"] = lab.split("/")
        rec[f"{k}_natural"] = n
    return rec


def test_keep_needs_four_of_five_equal_to_the_draft(mp: ModuleType) -> None:
    same = "Finance/low"
    assert mp.decide_row(_rec(same, same, (same, same, same)))[0] == "keep"
    assert mp.decide_row(_rec(same, same, ("Finance/high", same, same)))[0] == "keep"  # 4 of 5
    assert mp.decide_row(_rec(same, "Finance/high", ("Finance/high", same, same)))[0] == ""  # 3 of 5
    assert mp.decide_row(_rec(same, "", (same, same, same)))[0] == "keep"  # no checker: all 4 agree
    assert mp.decide_row(_rec(same, "", ("Finance/high", same, same)))[0] == ""


def test_fix_only_for_new_scenarios_with_unanimous_new_votes_and_checker(mp: ModuleType) -> None:
    alt = "Finance/high"
    assert mp.decide_row(_rec("Finance/low", alt, (alt, alt, alt)))[0] == "fix:Finance/high"
    assert mp.decide_row(_rec("Finance/low", alt, (alt, alt, alt), file="paraphrases.csv"))[0] == ""
    assert mp.decide_row(_rec("Finance/low", alt, (alt, alt, "Finance/medium")))[0] == ""


def test_drop_on_unnatural_majority_never_kept(mp: ModuleType) -> None:
    same = "Finance/low"
    assert mp.decide_row(_rec(same, same, (same, same, same), nat=("False", "False", "True")))[0] == "drop"
    assert mp.decide_row(_rec(same, same, (same, same, same), check_nat="False"))[0] == ""


def test_parse_vote(mp: ModuleType) -> None:
    ok = '{"category": "IT Support", "priority": "high", "natural": true}'
    assert mp.parse_vote(ok) == ("IT Support", "high", "True")
    assert mp.parse_vote('{"category": "Parking", "priority": "high", "natural": true}') is None
    assert mp.parse_vote("not json") is None and mp.parse_vote(None) is None
