#!/usr/bin/env python3
"""Write data/clean/train_val_features.csv: the derived columns the plan needs (P0.3b, LD-33).

    python scripts/add_derived_columns.py

Columns: request_id, lang_script, is_arabizi, stated_urgency (one row per official row, input order).
- lang_script    = lang from train_val_combined.csv. It is script-only (ar/en): clean_data.detect_lang
                   counts Arabic vs Latin letters and has no Arabizi class.
- is_arabizi     = False for every official row. Asserted: no row has a Latin letter next to one of the
                   Arabizi digits 2/3/5/6/7/8/9 (the official data has no digits at all). The package
                   LangIdentifier (P1.2) is the only source of the Arabizi label for new text.
- stated_urgency = has_urgent_marker ("URGENT" in text, case-sensitive; 27 rows).

The existing CSVs are not rewritten, so their parity hashes stay valid.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
OUT = ROOT / "data" / "clean" / "train_val_features.csv"

# A Latin letter adjacent to an Arabizi digit (3arif, te2akhar, 7abibi).
ARABIZI_DIGIT_IN_WORD = re.compile(r"[A-Za-z][2356789]|[2356789][A-Za-z]")


def derive(combined: pd.DataFrame) -> pd.DataFrame:
    """Build the derived-feature frame from train_val_combined.csv rows (read as strings).

    Raises:
        AssertionError: a row looks like Arabizi, or a column is malformed.
    """
    arabizi_like = combined["text"].str.contains(ARABIZI_DIGIT_IN_WORD)
    offenders = combined.loc[arabizi_like, "request_id"].tolist()
    assert not offenders, f"Arabizi-like official rows: {offenders}"
    assert set(combined["lang"]) <= {"ar", "en"}, f"unexpected lang values {set(combined['lang'])}"
    assert set(combined["has_urgent_marker"]) <= {"True", "False"}
    return pd.DataFrame(
        {
            "request_id": combined["request_id"],
            "lang_script": combined["lang"],
            "is_arabizi": False,
            "stated_urgency": combined["has_urgent_marker"] == "True",
        }
    )


def main() -> int:
    """CLI entry point; returns the process exit code."""
    combined = pd.read_csv(COMBINED, encoding="utf-8", dtype=str, keep_default_na=False)
    features = derive(combined)
    features.to_csv(OUT, index=False, encoding="utf-8", lineterminator="\n")
    print(
        f"wrote {OUT.relative_to(ROOT).as_posix()}: {len(features)} rows, "
        f"is_arabizi={int(features.is_arabizi.sum())}, stated_urgency={int(features.stated_urgency.sum())}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
