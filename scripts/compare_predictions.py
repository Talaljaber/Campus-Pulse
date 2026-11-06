#!/usr/bin/env python3
"""Score one or more prediction files against a labels file and print them side by side.

    python scripts/compare_predictions.py --labels data/our_test/set4_labels.csv \
        A=out/A.csv B=out/B.csv ...

- `--labels`: `request_id,category,priority` (extra columns such as `scenario_family` are fine).
- Each `NAME=PATH` is a `predict.py` output (`request_id,category,priority`, `--debug` columns allowed).
- Prints, per run: category accuracy and macro-F1, priority accuracy and macro-F1, and joint accuracy (both
  labels right); then the same per language when a language is known (the `lang` column of a `--debug`
  prediction file, else the language part of `scenario_family`, e.g. `t4_arabizi_Finance_2`); then, for every
  run after the first, how many rows it fixed and broke against the first run.
- Exit 1 when a prediction file misses a labelled request_id.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

_LANG = re.compile(r"(?:^|_)(en|ar|arabizi)_")


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def _lang_of_family(family: str) -> str:
    m = _LANG.search(family)
    return m.group(1) if m else ""


def _scores(gold: pd.DataFrame, pred: pd.DataFrame) -> tuple[float, float, float, float, float]:
    cat_g, cat_p = gold["category"], pred["category"]
    pri_g, pri_p = gold["priority"], pred["priority"]
    joint = ((cat_g.values == cat_p.values) & (pri_g.values == pri_p.values)).mean()
    return (
        accuracy_score(cat_g, cat_p),
        f1_score(cat_g, cat_p, average="macro", zero_division=0),
        accuracy_score(pri_g, pri_p),
        f1_score(pri_g, pri_p, average="macro", zero_division=0),
        float(joint),
    )


def _row(name: str, n: int, s: tuple[float, ...]) -> str:
    return f"{name:<10} {n:>5}  " + "  ".join(f"{v:>7.3f}" for v in s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("runs", nargs="+", help="NAME=PATH to a predictions CSV")
    args = ap.parse_args(argv)

    gold = _read(args.labels).set_index("request_id")
    runs: dict[str, pd.DataFrame] = {}
    for spec in args.runs:
        name, _, path = spec.partition("=")
        if not path:
            ap.error(f"expected NAME=PATH, got {spec!r}")
        pred = _read(Path(path)).set_index("request_id")
        missing = gold.index.difference(pred.index)
        if len(missing):
            example = list(missing[:3])
            print(f"error: {path} misses {len(missing)} labelled rows, e.g. {example}", file=sys.stderr)
            return 1
        runs[name] = pred.loc[gold.index]

    cols = ("cat_acc", "cat_F1", "pri_acc", "pri_F1", "joint")
    head = f"{'run':<10} {'rows':>5}  " + "  ".join(f"{c:>7}" for c in cols)
    print(f"labels: {args.labels} ({len(gold)} rows)\n\n{head}")
    for name, pred in runs.items():
        print(_row(name, len(gold), _scores(gold, pred)))

    first = next(iter(runs.values()))
    if "lang" in first.columns:
        lang = first["lang"]
    elif "scenario_family" in gold.columns:
        lang = gold["scenario_family"].map(_lang_of_family)
    else:
        lang = pd.Series("", index=gold.index)
    for value in ("en", "ar", "arabizi"):
        mask = (lang == value).values
        if not mask.any():
            continue
        print(f"\n[{value}]\n{head}")
        for name, pred in runs.items():
            print(_row(name, int(mask.sum()), _scores(gold[mask], pred[mask])))

    base_name, base = next(iter(runs.items()))
    if len(runs) > 1:
        print(f"\nrows fixed / broken against {base_name} (category, priority):")
        for name, pred in list(runs.items())[1:]:
            parts = []
            for col in ("category", "priority"):
                was = base[col].values == gold[col].values
                now = pred[col].values == gold[col].values
                parts.append(f"{col} +{int((~was & now).sum())} / -{int((was & ~now).sum())}")
            print(f"  {name:<10} " + ", ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
