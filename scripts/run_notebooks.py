#!/usr/bin/env python3
"""Execute notebooks 01-05 in place (P2.12, LD-23); P6 re-runs it after the final freeze.

    python scripts/run_notebooks.py                     # -> 5/5 executed
    python scripts/run_notebooks.py --check-reads-only  # -> OK: notebooks read only reports/

The notebooks are thin loaders of `reports/*` written by `evaluate.py --all`: they never train, predict or
open a dataset. `--check-reads-only` scans every code cell for file reads (`open(`, `read_*(`, `np.load(`,
`Path(`)
and fails if a path literal leaves `reports/` or names a data or model path. Needs nbclient + ipykernel
(requirements-dev / the train venv).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB_DIR = ROOT / "notebooks"
NOTEBOOKS = ("01_eda", "02_benchmark", "03_uncertainty_conformal", "04_robustness_error_analysis",
             "05_fairness")
READ_CALL = re.compile(r"""(?:open|read_\w+|load|Path)\(\s*["']([^"']+)["']""")
ALLOWED = ("../reports", "reports")
FORBIDDEN = re.compile(r"""["'](?:\.\./)?(?:data|models)/""")
TIMEOUT_S = 300


def check_reads_only() -> list[str]:
    import nbformat

    bad = []
    for name in NOTEBOOKS:
        nb = nbformat.read(NB_DIR / f"{name}.ipynb", as_version=4)
        for cell in nb.cells:
            if cell.cell_type != "code":
                continue
            # a path literal handed to a read call is either the reports dir or a name relative to it (the
            # notebooks' `load(name)` joins it onto R = Path("../reports")); nothing may climb elsewhere
            bad += [f"{name}: {p}" for p in READ_CALL.findall(cell.source)
                    if p.startswith(("..", "/")) and not p.startswith(ALLOWED)]
            if FORBIDDEN.search(cell.source):
                bad.append(f"{name}: mentions a data or model path")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-reads-only", action="store_true")
    args = ap.parse_args(argv)
    if args.check_reads_only:
        bad = check_reads_only()
        if bad:
            print("\n".join(bad))
            return 1
        print("OK: notebooks read only reports/")
        return 0
    import nbformat
    from nbclient import NotebookClient

    done = 0
    for name in NOTEBOOKS:
        path = NB_DIR / f"{name}.ipynb"
        nb = nbformat.read(path, as_version=4)
        NotebookClient(nb, timeout=TIMEOUT_S, kernel_name="python3",
                       resources={"metadata": {"path": str(NB_DIR)}}).execute()
        for cell in nb.cells:  # deterministic diffs: drop execution timing metadata
            cell.metadata.pop("execution", None)
        nbformat.write(nb, path)
        done += 1
    print(f"{done}/{len(NOTEBOOKS)} executed")
    return 0 if done == len(NOTEBOOKS) else 1


if __name__ == "__main__":
    sys.exit(main())
