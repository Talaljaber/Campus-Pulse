"""LLM drafting (scripts/draft_augmentation.py, P2.2 + D-014): pinned, cached, schema-checked, never trusted.

No network: OpenRouter is mocked with respx.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx

from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.config.paths import REPO_ROOT

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "test/model"


def _load() -> ModuleType:
    path = REPO_ROOT / "scripts" / "draft_augmentation.py"
    spec = importlib.util.spec_from_file_location("draft_augmentation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def da() -> ModuleType:
    return _load()


def _reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001}})


def _drafter(da: ModuleType, tmp_path: Path, budget: float = 1.0) -> Any:
    def factory() -> OpenRouterClient:
        return OpenRouterClient("test-key", timeout_s=5, max_retries=0, sleep=lambda s: None)

    return da.Drafter(model=MODEL, params={"temperature": 0, "top_p": 1, "seed": 42}, cache=da.DraftCache(
        tmp_path / "cache.sqlite", "draft_responses"), budget_usd=budget, spent_today=0.0,
        log_path=tmp_path / "log.jsonl", retries=1, client_factory=factory)


@respx.mock
def test_schema_invalid_output_rejected(da: ModuleType, tmp_path: Path) -> None:
    route = respx.post(URL).mock(return_value=_reply('{"same_lang": "only one key"}'))
    drafter = _drafter(da, tmp_path)
    out = drafter.call("v1", "sys", "user", da.PARAPHRASE_SCHEMA, schema_name="p", item="TR-S01",
                       cmd="paraphrase")
    assert out is None and route.call_count == 2  # one retry, then skipped
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in log] == ["invalid", "invalid"] and all(r["cost_usd"] == 0.001 for r in log)
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == MODEL and sent["temperature"] == 0 and sent["seed"] == 42
    assert sent["response_format"]["type"] == "json_schema"


@respx.mock
def test_cache_hit_makes_no_http_call(da: ModuleType, tmp_path: Path) -> None:
    good = json.dumps({"same_lang": "a", "other_lang": "b", "arabizi": "c", "label_facts": "d"})
    route = respx.post(URL).mock(return_value=_reply(good))
    first = _drafter(da, tmp_path)
    a = first.call("v1", "sys", "user", da.PARAPHRASE_SCHEMA, schema_name="p", item="x", cmd="paraphrase")
    assert a is not None and not a.cached and route.call_count == 1
    second = _drafter(da, tmp_path)  # a new process would open the same cache file
    b = second.call("v1", "sys", "user", da.PARAPHRASE_SCHEMA, schema_name="p", item="x", cmd="paraphrase")
    assert b is not None and b.cached and b.cost_usd == 0.0 and route.call_count == 1
    assert b.data == a.data and second.calls == 0


@respx.mock
def test_rows_marked_needs_human_check(da: ModuleType, tmp_path: Path) -> None:
    good = json.dumps({"same_lang": "my uni account got locked and the online exam is tonight",
                       "other_lang": "حسابي مسكر وعندي امتحان الليلة",
                       "arabizi": "7esabi msakkar w 3indi emti7an", "label_facts": "exam tonight"})
    respx.post(URL).mock(return_value=_reply(good))
    scenarios = [s for s in da.official_scenarios() if s.scenario_id in ("TR-S32", "TR-S02")]
    prompt = da.Prompt.load(REPO_ROOT / "scripts" / "prompts" / "paraphrase.md")
    rows, skipped = da.paraphrase_rows(_drafter(da, tmp_path), prompt, scenarios,
                                       ["same_lang", "other_lang", "arabizi"], "AUG-PA-")
    assert skipped == [] and len(rows) == 6
    assert all(r["needs_human_check"] == "True" and r["author_method"] == f"llm:{MODEL}" for r in rows)
    by_sid = {s.scenario_id: s for s in scenarios}
    for r in rows:  # labels and cv_group are the source scenario's, so a paraphrase never crosses folds
        sc = by_sid[r["source_scenario_id"]]
        assert (r["cv_group"], r["category"], r["priority"]) == (sc.cv_group, sc.category, sc.priority)
    assert {r["source"] for r in rows if r["lang"] == "arabizi"} == {"llm_arabizi"}


def test_budget_stops_before_calling(da: ModuleType, tmp_path: Path) -> None:
    drafter = _drafter(da, tmp_path, budget=0.0)
    with pytest.raises(da.BudgetExceeded):
        drafter.call("v1", "sys", "user", da.PARAPHRASE_SCHEMA, schema_name="p", item="x", cmd="paraphrase")


def _write(path: Path, header: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def test_apply_review_needs_a_human_verdict(da: ModuleType, tmp_path: Path) -> None:
    base = {"lang": "en", "source": "llm_paraphrase", "source_scenario_id": "TR-S02", "cv_group": "TR-S02",
            "needs_human_check": "True", "author_method": f"llm:{MODEL}", "category": "Finance",
            "priority": "low"}
    aug = tmp_path / "paraphrases.csv"
    rows = [{"request_id": f"AUG-PA-000{i}", "text": f"text {i}", **base} for i in (1, 2, 3)]
    _write(aug, da.COLUMNS, rows)
    sheet_rows = []
    for i, (agree, full, verdict) in enumerate([("False", "True", ""), ("True", "True", "ok"),
                                                ("True", "False", "")], start=1):
        row = dict.fromkeys(da.SHEET_COLUMNS, "")
        row.update({"request_id": f"AUG-PA-000{i}", "agree": agree, "read_in_full": full,
                    "human_verdict": verdict})
        sheet_rows.append(row)
    sheet = tmp_path / "sheet.csv"
    _write(sheet, da.SHEET_COLUMNS, sheet_rows)
    # a disagreement without a verdict blocks accepting the unsampled agreements
    assert da.apply_review(sheet, [aug], accept_unsampled=True) == 1
    assert da.apply_review(sheet, [aug], accept_unsampled=False) == 0
    flags = {r["request_id"]: r["needs_human_check"] for r in da._read_csv(aug)}
    assert flags == {"AUG-PA-0001": "True", "AUG-PA-0002": "False", "AUG-PA-0003": "True"}


def test_sample_is_seeded_and_order_free(da: ModuleType) -> None:
    ids = [f"AUG-PA-{i:04d}" for i in range(100)]
    a = da._sample(ids, 0.2, 42)
    assert len(a) == 20 and a == da._sample(list(reversed(ids)), 0.2, 42) and a != da._sample(ids, 0.2, 7)
