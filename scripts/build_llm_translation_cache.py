#!/usr/bin/env python3
"""P8.1: write a training translation table whose English is the LLM front end's (C2 arm).

    python scripts/build_llm_translation_cache.py --out PATH.csv [--folds CSV] [--llm-cache SQLITE]

Builds the same pool `train.py --include-model-reviewed` uses, then for every row whose original request is
Arabic script maps `model_text` to the English of `data/derived/llm_explanations.csv` (official rows, by
request_id) or, for the augmentation rows, to one cached LLM call (`config/llm_frontend.yaml`, needs
OPENROUTER_API_KEY). The CSV has the `CsvCachedTranslator` columns and the opus-mt model id and revision,
so `train.py --translation-cache PATH.csv` uses it unchanged. Rows the LLM cannot translate are listed and
left out (the local opus-mt takes over for them at train time).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))

from campuspulse_ai.adapters.models.translating_encoder import needs_translation  # noqa: E402
from campuspulse_ai.adapters.training.oof import PipelineToggles  # noqa: E402
from campuspulse_ai.adapters.training.pool import FOLDS_CSV  # noqa: E402
from campuspulse_ai.adapters.training.train_config import TrainCfg  # noqa: E402
from campuspulse_ai.adapters.training.translation_cache import HEADER  # noqa: E402
from campuspulse_ai.composition.llm_frontend import FrontendCfg, make_frontend  # noqa: E402
from campuspulse_ai.composition.training import TrainOptions, make_pool  # noqa: E402
from campuspulse_ai.config.settings import Settings  # noqa: E402

DERIVED = ROOT / "data" / "derived" / "llm_explanations.csv"


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--folds", type=Path, default=FOLDS_CSV)
    ap.add_argument("--llm-cache", type=Path, default=Path(".tmp/rc5/llm_cache.sqlite"))
    ap.add_argument("--no-model-reviewed", action="store_true")
    args = ap.parse_args()
    cfg = TrainCfg.load()
    toggles = PipelineToggles(include_model_reviewed=not args.no_model_reviewed)
    pool, _ = make_pool(TrainOptions(folds_csv=args.folds, toggles=toggles), cfg)
    with DERIVED.open(encoding="utf-8", newline="") as fh:
        derived = {r["request_id"]: r["english"] for r in csv.DictReader(fh)}
    tr = cfg.raw["translate"]
    settings = Settings(llm_frontend_cache_path=args.llm_cache)
    frontend = None
    table: dict[str, str] = {}
    from_derived = from_call = 0
    missing: list[str] = []
    for i, (rid, mt) in enumerate(zip(pool.request_id, pool.model_text, strict=True)):
        if not needs_translation(mt, float(tr["min_arabic_ratio"])):
            continue
        english = derived.get(rid) if pool.is_official[i] else None
        if english:
            from_derived += 1
        else:
            if frontend is None:
                frontend = make_frontend(settings, FrontendCfg.load(ROOT / "config" / "llm_frontend.yaml"))
            res = frontend.process(mt)
            english = res.english if res is not None else None
            from_call += 1
        if english:
            table[mt] = english
        else:
            missing.append(rid)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        for src in sorted(table):
            w.writerow([src, table[src], tr["model"], tr["revision"], "llm-frontend", 1])
    print(
        f"wrote {args.out}: {len(table)} texts ({from_derived} derived, {from_call} LLM calls); "
        f"missing {len(missing)}: {missing[:10]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
