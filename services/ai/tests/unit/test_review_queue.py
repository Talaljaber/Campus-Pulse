"""P8.1 review queue: build order, scenario inheritance, apply safety, guard, audit log (fixture only)."""
# ruff: noqa: E501

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

from campuspulse_ai.config.paths import REPO_ROOT

AUG_COLS = ["request_id", "text", "lang", "source", "source_scenario_id", "cv_group", "needs_human_check",
            "author_method", "category", "priority"]
SHEET_COLS = ["file", "request_id", "text", "lang", "source", "draft_category", "draft_priority", "check_category",
              "check_priority", "check_natural", "agree", "read_in_full", "human_verdict", "human_category",
              "human_priority", "human_text", "notes"]


@pytest.fixture(scope="module")
def rq() -> ModuleType:
    path = REPO_ROOT / "scripts" / "review_queue.py"
    spec = importlib.util.spec_from_file_location("review_queue", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _aug(rid: str, lang: str, group: str, cat: str = "Finance", pri: str = "low",
         src: str = "new_scenario") -> dict[str, str]:
    return {"request_id": rid, "text": f"text {rid}", "lang": lang, "source": src, "source_scenario_id": group,
            "cv_group": group, "needs_human_check": "True", "author_method": "llm", "category": cat,
            "priority": pri}


def _put(path: Path, cols: Sequence[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _get(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["request_id"]: r for r in csv.DictReader(fh)}


@pytest.fixture
def env(tmp_path: Path) -> tuple[Path, Path]:
    aug, review = tmp_path / "aug", tmp_path / "aug" / "review"
    review.mkdir(parents=True)
    # NEW-C01: its first EN form is a checker disagreement (T1); NEW-C02: all agree (T2 anchor); Arabizi forms in T4
    new = [_aug("N1", "en", "NEW-C01"), _aug("N2", "ar", "NEW-C01"), _aug("N3", "arabizi", "NEW-C01"),
           _aug("N4", "en", "NEW-C01"),
           _aug("M1", "en", "NEW-C02", "IT Support", "high"), _aug("M2", "ar", "NEW-C02", "IT Support", "high"),
           _aug("M3", "arabizi", "NEW-C02", "IT Support", "high"), _aug("M4", "ar", "NEW-C02", "IT Support", "high")]
    para = [_aug("P1", "en", "TR-S01", "IT Support", "high", "llm_paraphrase"),
            _aug("P2", "en", "TR-S02", "Finance", "low", "llm_paraphrase")]
    foff = [_aug("O1", "arabizi", "TR-S03", "Finance", "low", "llm_arabizi")]
    _put(aug / "new_scenarios.csv", AUG_COLS, new)
    _put(aug / "paraphrases.csv", AUG_COLS, para)
    _put(aug / "arabizi_from_official.csv", AUG_COLS, foff)

    def sheet_row(r: dict[str, str], name: str, agree: bool, pri: str = "") -> dict[str, str]:
        return {"file": name, "request_id": r["request_id"], "text": r["text"], "lang": r["lang"],
                "source": r["source"], "draft_category": r["category"], "draft_priority": r["priority"],
                "check_category": r["category"], "check_priority": pri or r["priority"],
                "check_natural": "True", "agree": str(agree), "read_in_full": str(not agree), "human_verdict": "",
                "human_category": "", "human_priority": "", "human_text": "", "notes": ""}

    rows = [sheet_row(new[0], "new_scenarios.csv", False, pri="high")]
    rows += [sheet_row(r, "new_scenarios.csv", r["request_id"] != "N4") for r in new[1:]]
    rows += [sheet_row(para[0], "paraphrases.csv", False, pri="medium"), sheet_row(para[1], "paraphrases.csv", True)]
    _put(review / "review_sheet.csv", SHEET_COLS, rows)
    return aug, review


def _decide(path: Path, decisions: dict[str, str]) -> None:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames or []
        rows = list(rd)
    for r in rows:
        r["decision"] = decisions.get(r["draft_id"], r["decision"])
    _put(path, cols, rows)


def test_build_orders_blocks_and_inherits(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rows = rq.build_rows(aug, review)
    assert [r["block"] for r in rows] == ["T1", "T1", "T2", "T3", "T3", "T4", "T4", "T4"]
    t1, t2 = rows[0], rows[2]
    assert (t1["draft_id"], t1["scope"], t1["inherits"]) == ("N1", "scenario", "N2")
    assert (t2["draft_id"], t2["inherits"]) == ("M1", "M2 M4")
    assert all(r["decision"] == "" for r in rows)
    assert rows[-1]["draft_id"] == "O1" and "no checker pass" in rows[-1]["why_first"]  # official-derived last


def test_nothing_changes_without_decisions(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    before = (aug / "new_scenarios.csv").read_bytes()
    assert rq.apply(None, aug, review) == 0
    assert (aug / "new_scenarios.csv").read_bytes() == before
    assert not list(review.glob("applied_*.jsonl"))


def test_keep_inherit_fix_drop_and_audit(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    q = review / "review_queue.csv"
    _decide(q, {"N1": "fix:Finance/high", "N4": "keep", "M1": "keep", "P1": "drop", "P2": "keep", "N3": "keep"})
    assert rq.apply(q, aug, review, today="2026-11-01") == 0
    new = _get(aug / "new_scenarios.csv")
    assert {i: (r["priority"], r["needs_human_check"]) for i, r in new.items() if i.startswith("N")} == {
        "N1": ("high", "False"), "N2": ("high", "False"), "N3": ("high", "False"), "N4": ("high", "False")}
    assert all(new[i]["needs_human_check"] == "False" for i in ("M1", "M2", "M4"))
    assert new["M3"]["needs_human_check"] == "True"  # Arabizi sibling: only on its own decision
    para = _get(aug / "paraphrases.csv")
    assert "P1" not in para and para["P2"]["needs_human_check"] == "False"
    assert _get(aug / "arabizi_from_official.csv")["O1"]["needs_human_check"] == "True"
    log = [json.loads(x) for x in (review / "applied_2026-11-01.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {e["id"] for e in log} >= {"N1", "N2", "P1", "M2"}
    assert next(e for e in log if e["id"] == "N2")["after"]["priority"] == "high"


def test_scenario_drop_removes_all_forms_and_row_drop_only_one(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    q = review / "review_queue.csv"
    _decide(q, {"N1": "drop", "M1": "keep", "M3": "drop"})
    rq.apply(q, aug, review)
    assert set(_get(aug / "new_scenarios.csv")) == {"M1", "M2", "M4"}


def test_refusals_change_nothing(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    q = review / "review_queue.csv"
    before = (aug / "paraphrases.csv").read_bytes()
    _decide(q, {"P1": "fix:Finance/low"})
    assert rq.apply(q, aug, review) == 1
    _decide(q, {"P1": "ok"})
    assert rq.apply(q, aug, review) == 1
    _decide(q, {"P1": "", "N1": "fix:Finance/high", "N4": "fix:Finance/medium"})
    assert rq.apply(q, aug, review) == 1  # one scenario, two labels
    assert (aug / "paraphrases.csv").read_bytes() == before


def test_accept_agreed_guard(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    q = review / "review_queue.csv"
    assert rq.apply(q, aug, review, accept_agreed=True) == 1  # nothing decided: guard refuses
    _decide(q, {"N1": "keep", "N4": "keep", "M1": "keep", "P1": "keep", "P2": "keep"})
    assert rq.apply(q, aug, review, accept_agreed=True) == 0
    new = _get(aug / "new_scenarios.csv")
    assert new["N3"]["needs_human_check"] == "True" and new["M3"]["needs_human_check"] == "True"  # no Arabizi
    assert _get(aug / "arabizi_from_official.csv")["O1"]["needs_human_check"] == "True"  # no checker pass


def test_guard_refuses_when_agreements_are_changed(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    q = review / "review_queue.csv"
    _decide(q, {"N1": "keep", "N4": "keep", "M1": "fix:IT Support/medium", "P1": "keep", "P2": "keep"})
    assert rq.apply(q, aug, review, accept_agreed=True) == 1
    assert rq.apply(q, aug, review, accept_agreed=True, skip_guard=True) == 0


def test_model_panel_mode_never_sets_needs_human_check_false(rq: ModuleType, env: tuple[Path, Path]) -> None:
    aug, review = env
    rq.build(aug, review)
    queue = review / "review_queue.csv"
    _decide(queue, {"N1": "fix:Finance/high", "P1": "drop", "P2": "keep", "M1": "keep"})
    assert rq.apply(queue, aug, review, model_panel=True, today="2026-11-01") == 0
    new, para = _get(aug / "new_scenarios.csv"), _get(aug / "paraphrases.csv")
    assert "P1" not in para and para["P2"]["needs_human_check"] == "True"  # drop applied, keep is not human review
    assert new["N1"]["priority"] == "high" and new["N1"]["needs_human_check"] == "True"  # fix applied, still unreviewed
    assert {r["needs_human_check"] for rows in (new, para) for r in rows.values()} == {"True"}