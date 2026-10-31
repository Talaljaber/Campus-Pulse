"""`predict.py`: the judges' command. Offline, CPU only, no API key (P1.17, ARCHITECTURE §2.5, SPEC §5.5).

    python services/ai/predict.py --input <csv> --output <csv> [--use-llm] [--model-dir models/frozen]
                                  [--debug] [--batch-size 64]

- Input: UTF-8 CSV (a BOM is accepted, as in the official files) with at least `request_id` and `text`
  (the hidden-test layout); other columns are ignored.
- Output: exactly `request_id,category,priority`, one row per input row in input order, UTF-8 without BOM,
  `\\n` line endings (the challenge's `predictions.csv`). `--debug` appends probability, set-size, tier,
  flag, OOD and artifact columns.
- Exit codes: 0 ok · 2 artifact problem (missing encoder → the fetch command) · 3 `--use-llm` unavailable ·
  4 invalid input (missing file or column).
- Last line: `wrote N rows → <path> (artifact v1 sha=<12 hex>, tier0=N, llm=N, <s> s)`.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

for _var, _value in (
    ("HF_HUB_OFFLINE", "1"),
    ("TRANSFORMERS_OFFLINE", "1"),
    ("TOKENIZERS_PARALLELISM", "false"),
):
    os.environ.setdefault(_var, _value)

from campuspulse_ai.application.dto import BATCH_CSV_COLUMNS, BATCH_INPUT_COLUMNS  # noqa: E402
from campuspulse_ai.composition.offline import BatchRow, build_offline  # noqa: E402
from campuspulse_ai.config.paths import MODELS_FROZEN  # noqa: E402
from campuspulse_ai.domain.errors import ArtifactError, InvalidInput, LLMUnavailable  # noqa: E402

EXIT_OK, EXIT_ARTIFACT, EXIT_LLM, EXIT_INPUT = 0, 2, 3, 4
FETCH_COMMAND = "python scripts/fetch_models.py --tag models-v1-rc1"
DEBUG_COLUMNS = (
    "p_category",
    "p_priority",
    "set_cat",
    "set_pri",
    "tier",
    "flags",
    "ood_score",
    "lang",
    "artifact_version",
)
MB = 2**20


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="predict.py", description="Offline CampusPulse batch prediction.")
    p.add_argument("--input", type=Path, required=True, help="CSV with request_id,text")
    p.add_argument("--output", type=Path, required=True, help="predictions CSV to write")
    p.add_argument("--use-llm", action="store_true", help="LLM tie-breaks (needs the P3 tier and a key)")
    p.add_argument(
        "--model-dir",
        type=Path,
        default=MODELS_FROZEN,
        help="a frozen model dir, or models/frozen to use CURRENT (default %(default)s)",
    )
    p.add_argument("--debug", action="store_true", help="append probabilities, sets, flags, OOD columns")
    p.add_argument("--batch-size", type=int, default=64, help="rows per chunk (default %(default)s)")
    return p


def read_rows(path: Path) -> list[BatchRow]:
    """Read `request_id,text` rows (UTF-8, BOM accepted, every value a string). Raises InvalidInput."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            columns = list(reader.fieldnames or [])
            missing = [c for c in BATCH_INPUT_COLUMNS if c not in columns]
            if missing:
                raise InvalidInput(f"{path}: missing column(s) {missing}; found {columns}")
            return [BatchRow(str(r["request_id"] or ""), str(r["text"] or "")) for r in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise InvalidInput(f"{path}: unreadable CSV: {exc}") from exc


def _peak_rss_mb() -> float | None:
    try:
        import psutil
    except ImportError:  # psutil is optional for predict.py (requirements.txt does not pin it)
        return None
    info = psutil.Process().memory_info()
    return round(float(getattr(info, "peak_wset", info.rss)) / MB, 1)


def _debug_cells(d: Mapping[str, object]) -> list[object]:
    flags = d.get("flags")
    joined = ";".join(str(f) for f in flags) if isinstance(flags, list) else ""
    return [
        json.dumps(d.get("p_cat"), sort_keys=True),
        json.dumps(d.get("p_pri"), sort_keys=True),
        d.get("set_cat"),
        d.get("set_pri"),
        d.get("tier"),
        joined,
        d.get("ood_score"),
        d.get("lang", ""),
        d.get("artifact_version"),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # "→" on a Windows cp1252 console
    args = _parser().parse_args(argv)
    started = time.perf_counter()
    try:
        rows = read_rows(args.input)
    except InvalidInput as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    try:
        container = build_offline(args.model_dir, use_llm=args.use_llm)
    except LLMUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LLM
    except ArtifactError as exc:
        print(f"error: {exc}\nrun: {FETCH_COMMAND}", file=sys.stderr)
        return EXIT_ARTIFACT
    try:
        predictions = container.batch.run(rows, use_llm=args.use_llm, batch_size=args.batch_size)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow([*BATCH_CSV_COLUMNS, *(DEBUG_COLUMNS if args.debug else ())])
        for p in predictions:
            row: list[object] = [p.request_id, p.category, p.priority]
            writer.writerow(row + (_debug_cells(p.debug) if args.debug else []))
    llm = sum(1 for p in predictions if p.debug.get("tier") not in (None, "tier0"))
    elapsed = time.perf_counter() - started
    sha = container.manifest.sha[:12]
    summary = (
        f"wrote {len(predictions)} rows → {args.output} (artifact {container.config.artifact_version} "
        f"sha={sha}, tier0={len(predictions) - llm}, llm={llm}, {elapsed:.1f} s)"
    )
    peak = _peak_rss_mb() if args.debug else None
    print(summary + (f" peak_rss_mb={peak}" if peak is not None else ""))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
