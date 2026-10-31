"""Seed rows for the red team (P4.11): official training texts or a supplied CSV, never a holdout.

`load_seed_rows(path)` reads a UTF-8 CSV (a BOM is fine) with `request_id`, `category`, `priority`
and the text in `core` (the wrapper-stripped text of `data/clean/*.csv`) or else `text`. `lang` is
read when present (`en`, `ar`, `arabizi`), else guessed from the script (`config.text_lang`).

The default source is `data/clean/train_clean.csv` (the official training rows). A path inside
`data/our_test` or `data/robustness` is refused before the file is opened (`config.paths.is_holdout`,
D-013): perturbing holdout rows would leak them into anything trained on the failures.

Errors: `InvalidInput` for a holdout path, a missing file or column, an unknown label or language,
or a file with no rows. No side effects.
"""

from __future__ import annotations

import csv
from pathlib import Path

from campuspulse_ai.adapters.redteam.config import text_lang
from campuspulse_ai.adapters.redteam.perturbation import SeedRow
from campuspulse_ai.config.paths import is_holdout
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang

REQUIRED_COLUMNS = ("request_id", "category", "priority")
TEXT_COLUMNS = ("core", "text")
"""The first one present holds the text."""


def load_seed_rows(path: Path) -> list[SeedRow]:
    """The seed rows of `path`, in file order (module docstring). Raises `InvalidInput`."""
    if is_holdout(path):
        raise InvalidInput(f"refusing a holdout file as red-team seeds: {path} (D-013)")
    if not path.is_file():
        raise InvalidInput(f"red-team seed file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        text_col = next((c for c in TEXT_COLUMNS if c in header), None)
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if text_col is None or missing:
            raise InvalidInput(
                f"{path}: needs columns {[*REQUIRED_COLUMNS, 'core or text']}, missing {missing}"
            )
        rows = [_row(path, line, text_col) for line in reader if line[text_col].strip()]
    if not rows:
        raise InvalidInput(f"{path}: no rows with text")
    return rows


def _row(path: Path, line: dict[str, str], text_col: str) -> SeedRow:
    text = line[text_col].strip()
    try:
        return SeedRow(
            request_id=line["request_id"],
            text=text,
            lang=Lang(line["lang"]) if line.get("lang") else text_lang(text),
            category=Category(line["category"]),
            priority=Priority(line["priority"]),
        )
    except ValueError as exc:
        raise InvalidInput(f"{path}: row {line.get('request_id')!r}: {exc}") from exc
