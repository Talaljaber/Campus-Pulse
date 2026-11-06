"""`predict.py`: the judges' command (P1.17, ARCHITECTURE §2.5, SPEC §5.5; LLM default D-057).

    python services/ai/predict.py --input <csv> --output <csv> [--offline | --use-llm]
                                  [--model-dir models/frozen] [--debug] [--batch-size 64]

- LLM mode (D-057, user decision 2026-11-06): by default the LLM front end (P7.4, D-050) runs whenever
  `OPENROUTER_API_KEY` is set (environment or `.env`): Arabic and Arabizi requests are translated to English
  by the pinned LLM in front of our trained model (temperature 0, cached), which still makes every decision.
  Without a key it runs fully offline on CPU, with a one-line notice. `--offline` never calls a network;
  `--use-llm` requires the LLM and exits 3 without a key.

- Input: UTF-8 CSV (a BOM is accepted, as in the official files) with at least `request_id` and `text`
  (the hidden-test layout); other columns are ignored.
- Output: exactly `request_id,category,priority`, one row per input row in input order, UTF-8 without BOM,
  `\\n` line endings (the challenge's `predictions.csv`). `--debug` appends probability, set-size, tier,
  flag, OOD and artifact columns.
- Exit codes: 0 ok · 2 artifact problem (missing encoder → the fetch command) · 3 `--use-llm` without a key ·
  4 invalid input (missing file or column).
- Last line: `wrote N rows → <path> (artifact v1 sha=<12 hex>, llm_frontend=on|off, tier0=N, llm=N,
  llm_failed=N, <s> s)`; `llm_failed` counts rows whose LLM call failed twice and kept the model's labels.
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

from campuspulse_ai.application.dto import BATCH_CSV_COLUMNS  # noqa: E402
from campuspulse_ai.composition.arabizi_llm import has_key  # noqa: E402
from campuspulse_ai.composition.offline import (  # noqa: E402
    BatchRow,
    build_offline,
    read_batch_csv,
    write_predictions_csv,
)
from campuspulse_ai.config.paths import MODELS_FROZEN  # noqa: E402
from campuspulse_ai.config.settings import Settings  # noqa: E402
from campuspulse_ai.domain.errors import ArtifactError, InvalidInput, LLMUnavailable  # noqa: E402

EXIT_OK, EXIT_ARTIFACT, EXIT_LLM, EXIT_INPUT = 0, 2, 3, 4
FETCH_COMMAND = "python scripts/fetch_models.py"
NO_KEY_NOTICE = (
    "note: OPENROUTER_API_KEY is not set, so the LLM front end is off and every row is predicted fully "
    "offline. Set the key to translate Arabic and Arabizi with the LLM (README, Disclosures)."
)
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
    "route",
    "llm_cues",
)
MB = 2**20


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="predict.py", description="CampusPulse batch prediction.")
    p.add_argument("--input", type=Path, required=True, help="CSV with request_id,text")
    p.add_argument("--output", type=Path, required=True, help="predictions CSV to write")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--use-llm", action="store_true", help="require the LLM front end (exit 3 without OPENROUTER_API_KEY)"
    )
    mode.add_argument("--offline", action="store_true", help="never call an LLM (fully offline, CPU only)")
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
    """Read `request_id,text` rows with the shared `/v1/batch` reader (UTF-8, BOM accepted, values kept
    exactly as written). Raises InvalidInput (unreadable file, not UTF-8, missing column)."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise InvalidInput(f"{path}: cannot read: {exc}") from exc
    try:
        return [BatchRow(rid, text) for rid, text in read_batch_csv(data, max_rows=sys.maxsize)]
    except InvalidInput as exc:
        raise InvalidInput(f"{path}: {exc}") from exc


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
        d.get("route", ""),
        json.dumps(d["llm_cues"], sort_keys=True) if d.get("llm_cues") else "",
    ]


def llm_mode(args: argparse.Namespace, settings: Settings) -> bool:
    """D-057: `--offline` → off; `--use-llm` → on (build_offline exits 3 without a key); default → on exactly
    when a key is configured."""
    if args.offline:
        return False
    return bool(args.use_llm) or has_key(settings)


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
    settings = Settings()
    use_llm = llm_mode(args, settings)
    if not use_llm and not args.offline:
        print(NO_KEY_NOTICE, file=sys.stderr)
    if args.offline:  # an explicit offline run ignores LLM_FRONTEND / LLM_ARABIZI_TRANSLATE in .env too
        settings = settings.model_copy(update={"llm_frontend": False, "llm_arabizi_translate": False})
    try:
        container = build_offline(args.model_dir, use_llm=use_llm, settings=settings)
    except LLMUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LLM
    except ArtifactError as exc:
        print(f"error: {exc}\nrun: {FETCH_COMMAND}", file=sys.stderr)
        return EXIT_ARTIFACT
    try:
        predictions = container.batch.run(rows, use_llm=use_llm, batch_size=args.batch_size)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.debug:  # our extension: the contract columns first, then the debug columns
        with args.output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow([*BATCH_CSV_COLUMNS, *DEBUG_COLUMNS])
            for p in predictions:
                writer.writerow([p.request_id, p.category, p.priority, *_debug_cells(p.debug)])
    else:  # the challenge's predictions.csv: the same bytes as /v1/batch
        labelled = [(p.request_id, p.category, p.priority) for p in predictions]
        args.output.write_bytes(write_predictions_csv(labelled))
    llm = sum(1 for p in predictions if p.debug.get("tier") not in (None, "tier0"))
    elapsed = time.perf_counter() - started
    sha = container.manifest.sha[:12]
    summary = (
        f"wrote {len(predictions)} rows → {args.output} (artifact {container.config.artifact_version} "
        f"sha={sha}, llm_frontend={'on' if use_llm else 'off'}, tier0={len(predictions) - llm}, llm={llm}, "
        f"llm_failed={container.batch.llm_failures}, "
        f"{elapsed:.1f} s)"
    )
    peak = _peak_rss_mb() if args.debug else None
    print(summary + (f" peak_rss_mb={peak}" if peak is not None else ""))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
