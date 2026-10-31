"""Build data/our_test/our_test.csv (the holdout evaluate.py reads) from the set files in data/our_test/.

Usage (from the repo root):
    python scripts/build_our_test.py           # (re)write data/our_test/our_test.csv
    python scripts/build_our_test.py --check   # exit 1 if the file is missing or stale (CI)

Each set is two files in the official hidden-test layout: `<set>_text.csv` (request_id, text) and
`<set>_labels.csv` (request_id, category, priority, scenario_family). The output joins them, adds
`lang` (from scenario_family), `author_method` and `test_set`, and keeps the original request ids.
Stdlib only; deterministic UTF-8 with BOM (like data/raw) and LF line endings.

Never trained on: train.py and load_pool refuse any path containing `our_test`.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "our_test"
OUT = DIR / "our_test.csv"

# set name -> (author_method, what the set measures). Report scores per set, never only pooled.
SETS: dict[str, tuple[str, str]] = {
    "set1": ("hand", "cross-lingual: training scenarios restated in the other language, official wrappers"),
    "set2": ("claude", "unseen scenarios, official style (one core + official wrappers)"),
    "set3": ("claude", "unseen scenarios, free student style (paraphrases, dialect, typos, code-switching)"),
}
LANGS = ("en", "ar", "arabizi")
COLUMNS = [
    "request_id",
    "text",
    "lang",
    "category",
    "priority",
    "author_method",
    "test_set",
    "scenario_family",
    "notes",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def lang_of(family: str) -> str:
    """The language token of a scenario_family such as `en_Facilities_1` or `t2_arabizi_Finance_0`."""
    for token in family.split("_"):
        if token in LANGS:
            return token
    raise ValueError(f"no language in scenario_family {family!r}")


def build() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for name, (author, note) in SETS.items():
        texts = read_csv(DIR / f"{name}_text.csv")
        labels = {r["request_id"]: r for r in read_csv(DIR / f"{name}_labels.csv")}
        if len(labels) != len(texts) or {t["request_id"] for t in texts} != labels.keys():
            raise ValueError(f"{name}: text and label files have different request ids")
        for t in texts:
            lab = labels[t["request_id"]]
            family = lab["scenario_family"]
            writer.writerow(
                [
                    t["request_id"],
                    t["text"],
                    lang_of(family),
                    lab["category"],
                    lab["priority"],
                    author,
                    name,
                    family,
                    note,
                ]
            )
    return "\ufeff" + buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if our_test.csv is missing or stale")
    args = parser.parse_args()
    data = build().encode("utf-8")
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != data:
            print(f"{OUT.relative_to(ROOT)} is stale: run python scripts/build_our_test.py", file=sys.stderr)
            return 1
        print(f"OK {OUT.relative_to(ROOT)} is up to date")
        return 0
    OUT.write_bytes(data)
    rows = data.count(b"\n") - 1
    print(f"wrote {OUT.relative_to(ROOT)}: {rows} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
