#!/usr/bin/env python3
"""P8.1: score one candidate model dir on the locked holdout (the lead runs it once per candidate and mode).

    python scripts/score_holdout.py --model-dir .tmp/rc5/C1 --mode offline|llm
                                  --holdout PATH [--out FILE.json]

Pre-registered rule (docs/plan/p7/SELECTION.md): score = 0.7 x category macro-F1 + 0.3 x priority macro-F1,
pooled over the holdout. The file's sha256 must equal the value recorded in SELECTION.md (EXPECTED_SHA256,
copied from there) or the script exits 2 before reading any row. Predictions come from `predict.py` (the
judges' command); `--mode llm` adds `--use-llm` (needs OPENROUTER_API_KEY; the cache is a scratch sqlite
file next to the model dir, never the shared one). Prints category and priority macro-F1 and accuracy per
language and pooled, the score, and the share of auto / ask / review rows. No holdout row is printed or
written; only aggregates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))

from campuspulse_ai.adapters.training.metrics import accuracy, macro_f1  # noqa: E402
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS  # noqa: E402

EXPECTED_SHA256 = "bdfee810ef38d5c06018254e37b630e07c34d0b801c15455126be6399b2a4614"  # SELECTION.md
W_CATEGORY, W_PRIORITY = 0.7, 0.3


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bucket(set_cat: str, set_pri: str) -> str:
    a, b = int(float(set_cat)), int(float(set_pri))
    if a == 0 or b == 0:
        return "review"
    return {1: "auto", 2: "ask"}.get(max(a, b), "review")


def score_rows(rows: list[dict[str, str]]) -> dict[str, float | int]:
    yc, pc = [r["category"] for r in rows], [r["pred_category"] for r in rows]
    yp, pp = [r["priority"] for r in rows], [r["pred_priority"] for r in rows]
    cat, pri = macro_f1(yc, pc, CATEGORY_LABELS), macro_f1(yp, pp, PRIORITY_LABELS)
    return {
        "n": len(rows),
        "category_macro_f1": cat,
        "priority_macro_f1": pri,
        "category_accuracy": accuracy(yc, pc),
        "priority_accuracy": accuracy(yp, pp),
        "score": W_CATEGORY * cat + W_PRIORITY * pri,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--mode", choices=("offline", "llm"), required=True)
    ap.add_argument("--holdout", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None, help="optional JSON with the aggregates")
    args = ap.parse_args()
    if sha256_of(args.holdout) != EXPECTED_SHA256:
        print(f"error: {args.holdout} does not match the sha256 in SELECTION.md; refusing to score",
              file=sys.stderr)
        return 2
    with args.holdout.open(encoding="utf-8-sig", newline="") as fh:
        gold = {r["id"]: r for r in csv.DictReader(fh)}
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "services" / "ai") + os.pathsep + env.get("PYTHONPATH", "")
    if args.mode == "llm":
        env["LLM_FRONTEND_CACHE_PATH"] = str(args.model_dir.resolve().parent / "holdout_llm_cache.sqlite")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.csv", Path(tmp) / "out.csv"
        with src.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["request_id", "text"])
            for rid, r in gold.items():
                w.writerow([rid, r["text"]])
        cmd = [sys.executable, str(ROOT / "services" / "ai" / "predict.py"), "--input", str(src),
               "--output", str(dst), "--model-dir", str(args.model_dir), "--debug"]
        if args.mode == "llm":
            cmd.append("--use-llm")
        subprocess.run(cmd, check=True, env=env, stdout=subprocess.DEVNULL)
        with dst.open(encoding="utf-8-sig", newline="") as fh:
            preds = {r["request_id"]: r for r in csv.DictReader(fh)}
    rows = [
        {**g, "pred_category": preds[i]["category"], "pred_priority": preds[i]["priority"],
         "bucket": bucket(preds[i].get("set_cat", "1"), preds[i].get("set_pri", "1"))}
        for i, g in gold.items()
    ]
    result: dict[str, object] = {
        "model_dir": str(args.model_dir), "mode": args.mode, "pooled": score_rows(rows)
    }
    for lang in sorted({r["lang"] for r in rows}):
        result[lang] = score_rows([r for r in rows if r["lang"] == lang])
    result["routing_share"] = {b: sum(r["bucket"] == b for r in rows) / len(rows)
                               for b in ("auto", "ask", "review")}
    langs = sorted(k for k in result if k not in ("pooled", "model_dir", "mode", "routing_share"))
    for key in ("pooled", *langs):
        s = result[key]
        assert isinstance(s, dict)  # noqa: S101
        print(f"{key:7s} n={s['n']:3d} category F1 {s['category_macro_f1']:.3f} "
              f"(acc {s['category_accuracy']:.3f})  "
              f"priority F1 {s['priority_macro_f1']:.3f} (acc {s['priority_accuracy']:.3f})  "
              f"score {s['score']:.3f}")
    print(f"score = 0.7 x category + 0.3 x priority (pooled): {result['pooled']['score']:.4f}"  # type: ignore[index]
          f"  routing {result['routing_share']}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
