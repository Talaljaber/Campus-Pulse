#!/usr/bin/env python3
"""P8.1: per-request latency (p50, p95, ms) and RSS of a model dir over the dev `tune` inputs.

    python scripts/rc_latency.py --model-dir .tmp/rc5/C1 [--use-llm] [--llm-cache FRESH.sqlite]

One warm-up request, then every dev `tune` row one at a time (batch size 1), as the API serves them. With
`--use-llm` point `--llm-cache` at a fresh file so the network call is part of the time. Prints
`p50 / p95 / rss_mb_after_load / rss_mb_after_run` as one JSON line. Only dev rows are read.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")


def _rss_mb() -> float:
    import psutil

    return round(psutil.Process().memory_info().rss / 2**20, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--use-llm", action="store_true")
    ap.add_argument("--llm-cache", type=Path, default=None)
    args = ap.parse_args()
    if args.llm_cache is not None:
        os.environ["LLM_FRONTEND_CACHE_PATH"] = str(args.llm_cache)
    from campuspulse_ai.composition.offline import build_offline
    from campuspulse_ai.frameworks.cli.predict import read_rows

    rows = []
    for lang in ("en", "ar", "az"):
        rows += read_rows(ROOT / "data" / "dev_fixes" / "inputs" / f"tune_{lang}.csv")
    container = build_offline(args.model_dir, use_llm=args.use_llm)
    after_load = _rss_mb()
    container.batch.run(rows[:1], use_llm=args.use_llm, batch_size=1)
    times = []
    for row in rows:
        t0 = time.perf_counter()
        container.batch.run([row], use_llm=args.use_llm, batch_size=1)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    out = {
        "model_dir": str(args.model_dir), "use_llm": args.use_llm, "n": len(times),
        "p50_ms": round(statistics.median(times), 1), "p95_ms": round(times[int(0.95 * (len(times) - 1))], 1),
        "rss_mb_after_load": after_load, "rss_mb_after_run": _rss_mb(),
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
