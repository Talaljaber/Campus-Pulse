#!/usr/bin/env python3
# ruff: noqa: E501
"""P7.4: run the dev set through the LLM front end and write the derived explanation file.

    python scripts/llm_frontend_eval.py run --model-dir D --split tune|check --out DIR [--cache PATH]
                                           [--env-file .env] [--model-id ID]
    python scripts/llm_frontend_eval.py explain --cache PATH [--env-file .env] [--model-id ID]
                                           [--out data/derived/llm_explanations.csv]

`run` builds the container in process with the front end on, labels `data/dev_fixes/inputs/<split>_<lang>.csv`
and writes `DIR/<split>_<lang>.csv` in the `dev_eval.py score` format (plus `DIR/stats.json`: latency p50 and
p95 per language, JSON validity, fallback rate, English-changed rate, spend). `explain` writes the INTERNAL
explanation column keyed by request_id for the 432 official rows and the dev rows. Scratch caches only; the key
is read from the process environment or from `--env-file` and is never printed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))

from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache  # noqa: E402
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger  # noqa: E402
from campuspulse_ai.adapters.models.llm_frontend_encoder import LlmFrontendEncoder  # noqa: E402
from campuspulse_ai.application.use_cases.batch_predict import BatchRow  # noqa: E402
from campuspulse_ai.composition.llm_frontend import FrontendCfg, make_frontend  # noqa: E402
from campuspulse_ai.composition.offline import build_offline  # noqa: E402
from campuspulse_ai.config.settings import Settings  # noqa: E402

DEV_DIR = ROOT / "data" / "dev_fixes"
INPUTS = DEV_DIR / "inputs"
LANGS = ("en", "ar", "az")
FORBIDDEN = (Path(r"C:\Users\hp\Desktop\campuspulse_eval"), ROOT / "data" / "our_test", ROOT / "data" / "robustness")


def load_key(env_file: Path | None) -> None:
    if os.environ.get("OPENROUTER_API_KEY") or env_file is None or not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].split("#")[0].strip()


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def cfg_for(args: argparse.Namespace) -> FrontendCfg:
    cfg = FrontendCfg.load(ROOT / "config" / "llm_frontend.yaml")
    if args.model_id:
        cfg = FrontendCfg(**{**cfg.__dict__, "model": args.model_id})
    return cfg


def run(args: argparse.Namespace) -> int:
    load_key(args.env_file)
    cfg = cfg_for(args)
    os.environ["LLM_FRONTEND_CACHE_PATH"] = str(args.cache)
    if args.model_id:
        os.environ["LLM_FRONTEND_MODEL"] = args.model_id
    container = build_offline(args.model_dir, use_llm=True, settings=Settings())
    enc = container.encoder
    assert isinstance(enc, LlmFrontendEncoder), "no OPENROUTER_API_KEY: the front end is off"
    args.out.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        src = INPUTS / f"{args.split}_{lang}.csv"
        with src.open(encoding="utf-8-sig", newline="") as fh:
            rows = [BatchRow(r["request_id"], r["text"]) for r in csv.DictReader(fh)]
        preds = container.batch.run(rows, use_llm=False, batch_size=64)
        with (args.out / f"{args.split}_{lang}.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["request_id", "category", "priority", "set_cat", "set_pri", "flags"])
            for p in preds:
                d = p.debug
                w.writerow([p.request_id, p.category, p.priority, d.get("set_cat", 1), d.get("set_pri", 1),
                            ";".join(d.get("flags", []))])
    totals = enc.frontend.cost.totals() if enc.frontend.cost is not None else {}
    f = enc.frontend
    non_en = enc.used["ar"] + enc.used["az"] + enc.fell_back["ar"] + enc.fell_back["az"]
    stats = {
        "model": cfg.model,
        "latency_ms": {k: {"n": len(v), "p50": pct(v, 0.5), "p95": pct(v, 0.95), "mean": statistics.fmean(v) if v else None}
                       for k, v in enc.latency_ms.items()},
        "calls": f.calls, "valid": f.valid, "invalid": f.invalid, "failed": f.failed,
        "json_validity": f.valid / max(1, f.valid + f.invalid),
        "fallback_rate_non_english": (enc.fell_back["ar"] + enc.fell_back["az"]) / max(1, non_en),
        "used": enc.used, "fell_back": enc.fell_back,
        "english_rows": enc.english_rows, "english_changed": enc.english_changed,
        "spend_usd": totals.get("usd"), "cost_calls": totals.get("calls"), "cached_calls": totals.get("cached"),
    }
    (args.out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))
    return 0


def explain(args: argparse.Namespace) -> int:
    load_key(args.env_file)
    cfg = cfg_for(args)
    frontend = make_frontend(Settings(), cfg, cache=SqliteCache(args.cache), cost=InMemoryCostLogger())
    items: list[tuple[str, str]] = []
    with (ROOT / "data" / "clean" / "train_val_combined.csv").open(encoding="utf-8-sig", newline="") as fh:
        items += [(r["request_id"], r["text_norm"]) for r in csv.DictReader(fh)]
    with (DEV_DIR / "dev_fixes.csv").open(encoding="utf-8-sig", newline="") as fh:
        items += [(r["dev_id"], r["text"]) for r in csv.DictReader(fh)]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        results = list(pool.map(lambda it: frontend.process(it[1]), items))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ok = 0
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["request_id", "english", "explanation", "cues", "model_id", "prompt_hash"])
        for (rid, _), res in zip(items, results, strict=True):
            if res is None:
                continue
            ok += 1
            w.writerow([rid, res.english, res.explanation, json.dumps(res.cues, sort_keys=True),
                        frontend.model_id, frontend.revision])
    print(f"wrote {ok} of {len(items)} rows to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="llm_frontend_eval.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "explain"):
        p = sub.add_parser(name)
        p.add_argument("--cache", type=Path, required=True)
        p.add_argument("--env-file", type=Path, default=None)
        p.add_argument("--model-id", default=None)
        if name == "run":
            p.add_argument("--model-dir", type=Path, required=True)
            p.add_argument("--split", choices=["tune", "check"], required=True)
            p.add_argument("--out", type=Path, required=True)
        else:
            p.add_argument("--out", type=Path, default=ROOT / "data" / "derived" / "llm_explanations.csv")
    args = ap.parse_args(argv)
    for path in (args.cache, getattr(args, "out", None), getattr(args, "model_dir", None)):
        if path is None:
            continue
        r = Path(path).resolve()
        for banned in FORBIDDEN:
            if r == banned.resolve() or banned.resolve() in r.parents:
                raise SystemExit(f"{path}: refused")
    return run(args) if args.cmd == "run" else explain(args)


if __name__ == "__main__":
    raise SystemExit(main())
