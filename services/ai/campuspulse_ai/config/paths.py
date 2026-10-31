"""Project paths: the one place that knows where data, config, models and reports live (P0.3).

`REPO_ROOT` is resolved once at import time, without reading any file:

1. the env var `CAMPUSPULSE_ROOT`, if set (it must point at a directory holding `data/` and `config/`);
2. otherwise the first ancestor of this file that contains both `data/` and `config/`
   (works for the editable install `pip install -e services/ai`);
3. otherwise the first such ancestor of the current working directory
   (works for a non-editable install run from the repo root).

If none is found, importing this module raises `RuntimeError`.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV_VAR = "CAMPUSPULSE_ROOT"
_ROOT_MARKERS: tuple[str, ...] = ("data", "config")

# Folders that hold holdout data. `train.py` refuses any input path containing one of these
# (ARCHITECTURE §3.2); only `evaluate.py` reads them.
HOLDOUT_MARKERS: tuple[str, ...] = ("our_test", "robustness")


def _is_root(candidate: Path) -> bool:
    return all((candidate / marker).is_dir() for marker in _ROOT_MARKERS)


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repo root (see the module docstring for the search order).

    Args:
        start: search upward from here instead of this file's location (used by tests).

    Raises:
        RuntimeError: if `CAMPUSPULSE_ROOT` is set but invalid, or no ancestor holds `data/` and `config/`.
    """
    env = os.environ.get(ROOT_ENV_VAR)
    if env:
        root = Path(env).resolve()
        if not _is_root(root):
            raise RuntimeError(f"{ROOT_ENV_VAR}={env!r} does not contain both data/ and config/")
        return root
    starts = [start] if start is not None else [Path(__file__).resolve().parent, Path.cwd().resolve()]
    for origin in starts:
        for candidate in (origin, *origin.parents):
            if _is_root(candidate):
                return candidate
    raise RuntimeError(
        f"cannot find the CampusPulse repo root (a directory with data/ and config/); set {ROOT_ENV_VAR}"
    )


REPO_ROOT: Path = find_repo_root()

DATA_RAW: Path = REPO_ROOT / "data" / "raw"
DATA_CLEAN: Path = REPO_ROOT / "data" / "clean"
DATA_AUGMENTED: Path = REPO_ROOT / "data" / "augmented"
OUR_TEST: Path = REPO_ROOT / "data" / "our_test"
ROBUSTNESS: Path = REPO_ROOT / "data" / "robustness"
CONFIG_DIR: Path = REPO_ROOT / "config"
LEXICONS: Path = CONFIG_DIR / "lexicons"
MODELS_FROZEN: Path = REPO_ROOT / "models" / "frozen"
REPORTS: Path = REPO_ROOT / "reports"


def is_holdout(path: Path) -> bool:
    """True if the path contains a holdout marker (`our_test`, `robustness`) anywhere.

    Deliberately strict (ARCHITECTURE §3.2: "raises if any input path contains ..."): a case-insensitive
    substring match on the whole path, so `data/our_test/x.csv`, `DATA\\Robustness\\probes.csv` and even
    `data/augmented/copy_of_our_test.csv` all count as holdouts. A false refusal is cheap; training on a
    holdout is not.
    """
    text = Path(path).as_posix().lower()
    return any(marker in text for marker in HOLDOUT_MARKERS)
