#!/usr/bin/env python3
"""Check that two `evaluate.py --all` runs give the same reports, apart from `generated_at` (P2.8 exit #3).

    python scripts/diff_reports.py [--against HEAD | --against-dir <dir>] [--reports reports]

Compares every report file `evaluate.py` writes (`metrics.json, benchmark.md, coverage.json, fairness.json,
ablations.json, errors.json, eda.json, model_lab.json, confusions/*.json`) with the committed version (git
`HEAD` by default) or with a saved copy of the directory. JSON is compared as data with every `generated_at`
key removed. Prints `identical modulo generated_at` and exits 0, or lists the files that differ and exits 1.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FILES = ("metrics.json", "benchmark.md", "coverage.json", "fairness.json", "ablations.json", "errors.json",
         "eda.json", "model_lab.json")


def strip(value: Any) -> Any:
    """`value` without any `generated_at` key, recursively."""
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k != "generated_at"}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def comparable(name: str, text: str | None) -> Any:
    if text is None:
        return None
    return strip(json.loads(text)) if name.endswith(".json") else text


def at_ref(ref: str, rel: str) -> str | None:
    done = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{rel}"], capture_output=True, check=False)
    return done.stdout.decode("utf-8") if done.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reports", type=Path, default=ROOT / "reports")
    ap.add_argument("--against", default="HEAD", help="git revision holding the previous reports")
    ap.add_argument("--against-dir", type=Path, default=None, help="a saved copy of the reports directory")
    args = ap.parse_args(argv)
    names = list(FILES) + sorted(f"confusions/{p.name}" for p in (args.reports / "confusions").glob("*.json"))
    differ = []
    for name in names:
        current = args.reports / name
        new = current.read_text(encoding="utf-8") if current.is_file() else None
        if args.against_dir is not None:
            old_path = args.against_dir / name
            old = old_path.read_text(encoding="utf-8") if old_path.is_file() else None
        else:
            rel = (args.reports / name).resolve().relative_to(ROOT).as_posix()
            old = at_ref(args.against, rel)
        if comparable(name, new) != comparable(name, old):
            differ.append(name)
    if differ:
        print("differ: " + ", ".join(differ))
        return 1
    print("identical modulo generated_at")
    return 0


if __name__ == "__main__":
    sys.exit(main())
