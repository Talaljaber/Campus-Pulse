"""The legacy cleaning pipeline runs under pytest (P0.3).

`scripts/test_clean.py` regenerates `data/clean/*` in place. Its outputs are deterministic, so the
committed files do not change (CI asserts that with `git diff --exit-code -- data/clean`).
"""

from __future__ import annotations

import subprocess
import sys

import pandas as pd

from campuspulse_ai.config.paths import DATA_CLEAN, REPO_ROOT

COMBINED_REQUIRED_COLUMNS = {
    "request_id",
    "text",
    "lang",
    "core",
    "text_norm",
    "scenario_id",
    "category",
    "priority",
    "cv_group",
}


def _run_script(name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / name)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_clean_script_passes() -> None:
    result = _run_script("test_clean.py")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "ALL TESTS PASSED"


def test_data_audit_passes() -> None:
    """scripts/test_data_audit.py (P0.3d): the audit's checks 1-11, regenerating in temp copies."""
    result = _run_script("test_data_audit.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == "DATA AUDIT TESTS PASSED"


def test_combined_shape() -> None:
    combined = pd.read_csv(
        DATA_CLEAN / "train_val_combined.csv", encoding="utf-8", dtype=str, keep_default_na=False
    )
    assert len(combined) == 432
    assert combined["cv_group"].nunique() == 30
    assert set(combined.columns) >= COMBINED_REQUIRED_COLUMNS
