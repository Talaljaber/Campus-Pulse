#!/usr/bin/env python3
"""P2.20 arm D1: LLM-translated Arabizi at test time vs the frozen rc3 as it is (`docs/ml/models.md` §29).

    python scripts/arabizi_llm_eval.py [--boot 2000] [--workers 8] [--out reports/arabizi_llm_d1.json]

A = frozen rc3, Arabizi as today (no LLM). D1 = the same frozen model with `LlmArabiziEncoder` in front of the
encoder (no retraining, test time only). Scored on (a) our_test Arabizi through `our_test_rows`, (b) the
Arabizi-from-official rows and (c) arabizi.csv plus the new-scenario Arabizi rows kept by the 0.95 near-dup
cut (ids from the arm C report), with the paired group bootstrap, conformal coverage and set size.
Needs OPENROUTER_API_KEY in the environment (or `--env-file`); responses are cached on disk. Writes nothing
under models/ or data/, and never writes our_test texts anywhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from campuspulse_ai.adapters.llm.arabizi_translator import LlmArabiziTranslator
from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
from campuspulse_ai.adapters.llm.cached_chat import CachedChat
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger
from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.adapters.models.llm_arabizi_encoder import LlmArabiziEncoder, split_arabizi
from campuspulse_ai.composition.evaluation import (
    ENSEMBLE,
    Row,
    core_rows,
    coverage_rows,
    load_eval_cfg,
    our_test_rows,
)
from campuspulse_ai.composition.offline import build_offline
from campuspulse_ai.config.paths import DATA_AUGMENTED, MODELS_FROZEN, REPO_ROOT, REPORTS
from campuspulse_ai.config.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_test import _f1, _paired  # noqa: E402

MODEL = "openai/gpt-4o-mini-2024-07-18"
DEFAULT_ENV = REPO_ROOT.parents[2] / ".env"  # the main checkout's .env (this repo is a worktree)
CACHE = Path(".cache/llm_arabizi_eval.sqlite")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _load_key(env_file: Path) -> None:
    if os.environ.get("OPENROUTER_API_KEY"):
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].split("#")[0].strip()


def _items(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"request_id": r["request_id"], "text": r["text"], "lang": "arabizi", "g": r["cv_group"],
         "subset": "augmented", "category": r["category"], "priority": r["priority"]}
        for r in rows
    ]


def _score(a: list[Row], d: list[Row], boot: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(a), "groups": len({r.group for r in a})}
    for target in ("category", "priority"):
        cov_a = {c["target"]: c for c in coverage_rows([("x", a)]) if c["lang"] == "all"}[target]
        cov_d = {c["target"]: c for c in coverage_rows([("x", d)]) if c["lang"] == "all"}[target]
        out[target] = {
            "A": _f1(a, target), "D1": _f1(d, target), "paired_D1_minus_A": _paired(a, d, target, boot),
            "coverage_A": cov_a["coverage"], "set_size_A": cov_a["mean_set_size"],
            "coverage_D1": cov_d["coverage"], "set_size_D1": cov_d["mean_set_size"],
        }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--boot", type=int, default=2000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    p.add_argument("--from-official", type=Path, default=DATA_AUGMENTED / "arabizi_from_official.csv")
    p.add_argument("--arm-c-report", type=Path, default=REPORTS / "arabizi_translit_arm.json")
    p.add_argument("--out", type=Path, default=REPORTS / "arabizi_llm_d1.json")
    args = p.parse_args()
    _load_key(args.env_file)
    settings = Settings()
    boot = dict(load_eval_cfg()["bootstrap"])
    boot["resamples"] = args.boot

    cost = InMemoryCostLogger()
    key = settings.openrouter_api_key
    assert key is not None, "OPENROUTER_API_KEY is not set"
    client = OpenRouterClient(key.get_secret_value(), timeout_s=settings.llm_arabizi_timeout_s, max_retries=1)
    chat = CachedChat(client, MODEL, SqliteCache(CACHE), cost)
    translator = LlmArabiziTranslator(chat)

    base = build_offline(MODELS_FROZEN / "v1", settings=settings)
    enc_d = LlmArabiziEncoder(base.encoder, translator)
    cont_d = build_offline(MODELS_FROZEN / "v1", settings=settings, encoder_override=enc_d)

    other = [r for r in _read(DATA_AUGMENTED / "arabizi.csv") if r["lang"] == "arabizi"]
    other += [r for r in _read(DATA_AUGMENTED / "new_scenarios.csv") if r["lang"] == "arabizi"]
    report = json.loads(args.arm_c_report.read_text(encoding="utf-8-sig"))
    keep = {row[0] for row in report["rows"]["c"]["arm"]}
    c_rows = [r for r in other if r["request_id"] in keep]
    b_rows = [r for r in _read(args.from_official) if r["lang"] == "arabizi"]
    items = {"b": _items(b_rows), "c": _items(c_rows)}

    # A first (no LLM), which also gives the our_test Arabizi texts for the warm-up below.
    a_test = [r for r in our_test_rows(base) if r.lang == "arabizi"]
    a = {k: core_rows(base, v, "oof", subset_key="subset", group_key="g", cat_key="category",
                      pri_key="priority") for k, v in items.items()}

    def original(text: str) -> str | None:
        return split_arabizi(base.core.normalizer.normalize(text).model_text)

    texts = [r.text for r in a_test] + [it["text"] for v in items.values() for it in v]
    originals = sorted({o for t in texts if (o := original(t)) is not None})
    with ThreadPoolExecutor(args.workers) as ex:  # warm the on-disk cache in parallel; scoring then hits it
        list(ex.map(translator.translate_one, originals))
    print(f"translated {len(originals)} originals: used={translator.used} fell_back={translator.fell_back}")

    d_test = [r for r in our_test_rows(cont_d) if r.lang == "arabizi"]
    d = {k: core_rows(cont_d, v, "oof", subset_key="subset", group_key="g", cat_key="category",
                      pri_key="priority") for k, v in items.items()}
    res: dict[str, Any] = {
        "model": MODEL,
        "a_our_test_arabizi": _score(a_test, d_test, boot),
        "b_from_official": _score(a["b"], d["b"], boot),
        "c_arabizi_plus_new_scenarios": _score(a["c"], d["c"], boot),
    }
    calls = [c for c in cost.calls if not c.cached and c.cost.usd > 0 or (not c.cached and c.tokens_in > 0)]
    lat = sorted(c.latency_ms for c in calls)
    ok_cost = sum(c.cost.usd for c in cost.calls)
    res["translation"] = {
        "originals": len(originals), "used": translator.used, "fell_back": translator.fell_back,
        "cache_hits": chat.cache_hits, "failures": chat.failures, "network_calls": len(calls),
        "latency_ms_p50": statistics.median(lat) if lat else None,
        "latency_ms_p95": lat[int(0.95 * (len(lat) - 1))] if lat else None,
        "spend_usd_this_run": round(ok_cost, 6),
    }
    flips = {
        k: sum(x.pred[ENSEMBLE][0] != y.pred[ENSEMBLE][0] for x, y in zip(a[k], d[k], strict=True))
        for k in a
    }
    res["category_flips_b_c"] = flips
    # translations of the non-our_test rows only (our_test texts are never written out)
    pairs = []
    for k in ("b", "c"):
        for it, x, y in zip(items[k], a[k], d[k], strict=True):
            o = original(it["text"])
            pairs.append({"id": it["request_id"], "set": k, "text": it["text"], "gold": it["category"],
                          "A": x.pred[ENSEMBLE][0], "D1": y.pred[ENSEMBLE][0],
                          "translation": enc_d.last_used.get(o or "")})
    res["pairs"] = pairs
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "pairs"}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
