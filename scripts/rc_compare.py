#!/usr/bin/env python3
"""P8.1: official scenario-held-out OOF of rc candidates, per language, paired bootstrap vs a base.

    python scripts/rc_compare.py --base .tmp/rc5/C0 --cand .tmp/rc5/C1 .tmp/rc5/C2 [--out FILE.json]

Reads each model dir's `oof.npz` (written by `train.py` from the frozen folds; nothing else is read), keeps
the official rows (`is_official`), joins candidate to base on `request_id` and prints category and priority
macro-F1 overall and per language (candidate, base, delta with the 90 % paired bootstrap CI over cv_groups,
B = 2000, seed 42) plus the D-016 and data-rule verdicts on the OOF part. Augmented rows in a candidate's
OOF are never scored.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))

from campuspulse_ai.adapters.training.metrics import macro_f1, paired_group_bootstrap  # noqa: E402
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS  # noqa: E402

BOOT: dict[str, Any] = {"resamples": 2000, "seed": 42, "low_pct": 5.0, "high_pct": 95.0}
LANGS = ("en", "ar")


def load(model_dir: Path) -> dict[str, dict[str, Any]]:
    z = np.load(model_dir / "oof.npz", allow_pickle=True)
    out: dict[str, dict[str, Any]] = {}
    for i, rid in enumerate(z["request_id"]):
        if not bool(z["is_official"][i]):
            continue
        out[str(rid)] = {
            "group": str(z["cv_group"][i]),
            "lang": str(z["lang"][i]),
            "category": str(z["category"][i]),
            "priority": str(z["priority"][i]),
            "pred_category": CATEGORY_LABELS[int(np.argmax(z["ensemble__category"][i]))],
            "pred_priority": PRIORITY_LABELS[int(np.argmax(z["final__priority"][i]))],
        }
    return out


def compare(base: dict[str, dict[str, Any]], cand: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = sorted(base)
    if sorted(cand) != ids:
        raise ValueError("candidate and base cover different official rows")
    result: dict[str, Any] = {}
    for name in ("all", *LANGS):
        sel = [i for i in ids if name == "all" or base[i]["lang"] == name]
        if not sel:
            continue
        slot: dict[str, Any] = {"n": len(sel)}
        for target, labels in (("category", CATEGORY_LABELS), ("priority", PRIORITY_LABELS)):
            y = [base[i][target] for i in sel]
            b = [base[i][f"pred_{target}"] for i in sel]
            c = [cand[i][f"pred_{target}"] for i in sel]
            boot = paired_group_bootstrap(y, b, c, [base[i]["group"] for i in sel], labels, **BOOT)
            slot[target] = {"cand": macro_f1(y, c, labels), "base": macro_f1(y, b, labels), **boot}
        result[name] = slot
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--cand", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    base = load(args.base)
    report: dict[str, Any] = {}
    for cdir in args.cand:
        res = compare(base, load(cdir))
        report[str(cdir)] = res
        print(f"\n{cdir} vs {args.base} (official OOF, n={res['all']['n']})")
        for name, slot in res.items():
            for target in ("category", "priority"):
                t = slot[target]
                lo, hi = t["ci_low"], t["ci_high"]
                print(f"  {name:4s} n={slot['n']:3d} {target:8s} cand {t['cand']:.3f} base {t['base']:.3f} "
                      f"delta {t['delta']:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
