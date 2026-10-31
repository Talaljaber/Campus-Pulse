"""Validate a predictions CSV against its input (P1.17): the challenge's `predictions.csv` contract.

    python scripts/validate_predictions.py --input data/raw/validation.csv --pred .tmp/pred_val.csv [--score]

Checks: UTF-8 without BOM; LF line endings only; header exactly `request_id,category,priority`; one row per
input row with the same `request_id`s in the same order; every label an official category / priority.
Prints `OK: <n> rows; header request_id,category,priority; labels valid; order preserved; utf-8 no BOM; LF`
and exits 0, or prints one line per problem and exits 1.

`--score` (wiring check only) also prints accuracy and macro-F1 when the input has `category`/`priority`.
On the official validation file those are **training rows**, so the numbers are never a metric.
Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import io
from collections.abc import Sequence
from pathlib import Path

HEADER = ("request_id", "category", "priority")
CATEGORIES = ("Registration", "IT Support", "Finance", "Transportation", "Facilities", "Academic Support")
PRIORITIES = ("low", "medium", "high")
BOM = b"\xef\xbb\xbf"


def _read_input(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _macro_f1(y: Sequence[str], yhat: Sequence[str]) -> float:
    labels = sorted(set(y) | set(yhat))
    scores = []
    for lab in labels:
        tp = sum(a == lab and b == lab for a, b in zip(y, yhat, strict=True))
        fp = sum(a != lab and b == lab for a, b in zip(y, yhat, strict=True))
        fn = sum(a == lab and b != lab for a, b in zip(y, yhat, strict=True))
        scores.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def validate(input_path: Path, pred_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """(errors, prediction rows)."""
    errors: list[str] = []
    raw = pred_path.read_bytes()
    if raw.startswith(BOM):
        errors.append("predictions start with a UTF-8 BOM")
    if b"\r" in raw:
        errors.append("predictions contain CR characters (line endings must be LF)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [f"predictions are not UTF-8: {exc}"], []
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    if not rows or tuple(rows[0]) != HEADER:
        errors.append(f"header is {rows[0] if rows else None}, expected {','.join(HEADER)}")
        return errors, []
    preds = [dict(zip(HEADER, r, strict=False)) for r in rows[1:]]
    for n, r in enumerate(rows[1:], start=2):
        if len(r) != len(HEADER):
            errors.append(f"line {n}: {len(r)} fields, expected {len(HEADER)}")
    inputs = _read_input(input_path)
    if len(preds) != len(inputs):
        errors.append(f"{len(preds)} prediction rows for {len(inputs)} input rows")
    for n, (a, b) in enumerate(zip(inputs, preds, strict=False), start=2):
        if a.get("request_id") != b.get("request_id"):
            errors.append(f"line {n}: request_id {b.get('request_id')!r} != input {a.get('request_id')!r}")
            break
    for n, p in enumerate(preds, start=2):
        if p.get("category") not in CATEGORIES:
            errors.append(f"line {n}: category {p.get('category')!r} is not an official category")
        if p.get("priority") not in PRIORITIES:
            errors.append(f"line {n}: priority {p.get('priority')!r} is not an official priority")
    return errors, preds


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--score", action="store_true", help="wiring check against input labels (never a metric)")
    args = ap.parse_args(argv)
    errors, preds = validate(args.input, args.pred)
    if errors:
        for e in errors:
            print(e)
        return 1
    print(
        f"OK: {len(preds)} rows; header {','.join(HEADER)}; labels valid; order preserved; utf-8 no BOM; LF"
    )
    if args.score:
        gold = _read_input(args.input)
        for target in ("category", "priority"):
            if target not in gold[0]:
                print(f"{target}: no gold column in the input")
                continue
            y, yhat = [g[target] for g in gold], [p[target] for p in preds]
            acc = sum(a == b for a, b in zip(y, yhat, strict=True)) / len(y)
            print(f"{target} acc={acc:.3f} macroF1={_macro_f1(y, yhat):.3f} (wiring check, not a metric)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
