#!/usr/bin/env python3
"""Standing data-audit tests (P0.3d): the audit's test gaps 1-11, without editing test_clean.py.

    python scripts/test_data_audit.py      -> one "ok <n>" line per check, then DATA AUDIT TESTS PASSED

Each check raises AssertionError naming itself on failure. Regeneration runs in temporary copies
(only data/raw/train.csv and data/raw/validation.csv are copied, by name), so the repo is never
touched. Thresholds come from config/datasets.yaml.

Note on check 1: the four CSVs must match the committed files byte for byte (after CRLF
normalisation). cleaning_report.md must match line for line up to the order of lines; its
`value_counts` tables order tied rows differently across pandas versions (2.2.3 made the committed
file, the pinned 3.0.6 swaps ties). The check prints which case applies.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import ModuleType

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
RAW_FILES = ("train.csv", "validation.csv")  # never glob data/raw: organizer-only files may appear there
CSV_OUTPUTS = ("train_clean.csv", "val_clean.csv", "train_val_combined.csv", "scenarios.csv")
REPORT = "cleaning_report.md"
UNSEEN_WRAPPERS = ("urgent: The bus is late", "URGENT The bus is late")
ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")


def load_clean_data() -> ModuleType:
    """Import scripts/clean_data.py read-only (its top level only defines constants and functions)."""
    spec = importlib.util.spec_from_file_location("clean_data", SCRIPTS / "clean_data.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def md5_lf(path: Path) -> str:
    """md5 of the file with CRLF normalised to LF."""
    return hashlib.md5(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def regenerate(workdir: Path) -> subprocess.CompletedProcess[bytes]:
    """Run a copy of clean_data.py on copies of the two official files, under a cp1252 console."""
    (workdir / "scripts").mkdir(parents=True)
    (workdir / "data" / "raw").mkdir(parents=True)
    shutil.copy2(SCRIPTS / "clean_data.py", workdir / "scripts" / "clean_data.py")
    for name in RAW_FILES:
        shutil.copy2(RAW / name, workdir / "data" / "raw" / name)
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, str(workdir / "scripts" / "clean_data.py")],
        cwd=workdir,
        env=env,
        capture_output=True,
        check=False,
    )


def ok(n: int, message: str) -> None:
    print(f"ok {n:>2}: {message}")


def check_regeneration() -> None:
    """Checks 1, 2 and 11: committed outputs == regenerated, deterministic, exit 0 on cp1252."""
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        runs = [regenerate(Path(tmp_a)), regenerate(Path(tmp_b))]
        for run in runs:
            tail = run.stderr[-300:]
            assert run.returncode == 0, f"check 11: clean_data.py exit {run.returncode}: {tail!r}"
        ok(11, "clean_data.py exits 0 with PYTHONIOENCODING=cp1252")
        out_a, out_b = Path(tmp_a) / "data" / "clean", Path(tmp_b) / "data" / "clean"
        for name in (*CSV_OUTPUTS, REPORT):
            assert md5_lf(out_a / name) == md5_lf(out_b / name), f"check 2: {name} differs between two runs"
        ok(2, "two regenerations hash equal (5 files)")
        for name in CSV_OUTPUTS:
            assert md5_lf(out_a / name) == md5_lf(CLEAN / name), f"check 1: committed {name} != regenerated"
        fresh, committed = out_a / REPORT, CLEAN / REPORT
        if md5_lf(fresh) == md5_lf(committed):
            report_note = "report byte-identical"
        else:
            fresh_lines = Counter(fresh.read_text(encoding="utf-8").splitlines())
            committed_lines = Counter(committed.read_text(encoding="utf-8").splitlines())
            assert fresh_lines == committed_lines, "check 1: cleaning_report.md content differs"
            report_note = f"report equal up to tie order (pandas {pd.__version__})"
        hashes = ", ".join(f"{name} {md5_lf(CLEAN / name)[:8]}" for name in CSV_OUTPUTS)
        ok(1, f"committed data/clean == regenerated: {hashes}; {report_note}")


def check_labels_equal_raw(combined: pd.DataFrame) -> None:
    """Check 3: labels and text in train_val_combined.csv equal raw for all 432 ids."""
    raw = pd.concat([read(RAW / name) for name in RAW_FILES], ignore_index=True)
    assert raw["request_id"].is_unique and combined["request_id"].is_unique, "check 3: duplicate ids"
    merged = raw.merge(combined, on="request_id", how="outer", suffixes=("_raw", "_clean"), indicator=True)
    assert (merged["_merge"] == "both").all() and len(merged) == 432, "check 3: id sets differ"
    for col in ("text", "category", "priority"):
        bad = merged[merged[f"{col}_raw"] != merged[f"{col}_clean"]]
        assert bad.empty, f"check 3: {col} differs from raw for {bad.request_id.tolist()[:5]}"
    ok(3, "labels and text of 432 combined rows equal raw")


def check_near_duplicates(combined: pd.DataFrame, threshold: float) -> None:
    """Check 4: no identical text_norm across groups, no cross-group char 3-5-gram cosine >= threshold.

    Uses the same functions as the leakage gate (scripts/check_leakage.py, P0.3e).
    """
    sys.path.insert(0, str(SCRIPTS))
    import check_leakage

    exact = check_leakage.exact_cross_group(combined)
    near = check_leakage.char_near_pairs(combined, threshold)
    worst = check_leakage.max_cross_group_cosine(combined)
    assert not exact, f"check 4: identical text_norm across groups {exact[:3]}"
    assert not near, f"check 4: cross-group char cosine >= {threshold}: {near[:3]}"
    ok(4, f"no identical text_norm across groups; no cross-group char 3-5-gram cosine >= {threshold} "
          f"(max {worst:.3f})")


def check_groups(combined: pd.DataFrame, scenarios: pd.DataFrame) -> None:
    """Check 5: groups are unions of whole scenarios, pairs never split, one label pair per group."""
    per_scenario = combined.groupby("scenario_id")["cv_group"].nunique()
    split = per_scenario[per_scenario > 1].index.tolist()
    assert not split, f"check 5: scenarios split across groups {split}"
    group_of = combined.drop_duplicates("scenario_id").set_index("scenario_id")["cv_group"]
    pairs = scenarios[scenarios["translation_of"] != ""]
    for row in pairs.itertuples():
        same = group_of[row.scenario_id] == group_of[row.translation_of]
        assert same, f"check 5: translation pair {row.scenario_id} split"
    labels = combined.groupby("cv_group").agg(c=("category", "nunique"), p=("priority", "nunique"))
    assert (labels.c == 1).all() and (labels.p == 1).all(), "check 5: a group mixes labels"
    per_cat = combined.drop_duplicates("cv_group")["category"].value_counts()
    ok(5, f"{len(labels)} groups = whole scenarios; {len(pairs) // 2} translation pairs intact; "
          f"one label pair per group; groups per category {sorted(set(per_cat))}")


def check_folds(combined: pd.DataFrame) -> None:
    """Check 6: cv_folds.csv covers every group once, 6 categories and 3 priorities per fold, reproducible."""
    folds = read(CLEAN / "cv_folds.csv")
    assert list(folds.columns) == ["cv_group", "cv_fold"], "check 6: cv_folds.csv columns"
    assert folds["cv_group"].is_unique, "check 6: a group appears in two folds"
    assert set(folds["cv_group"]) == set(combined["cv_group"]), "check 6: fold groups != data groups"
    k = int(yaml.safe_load((ROOT / "config" / "train.yaml").read_text(encoding="utf-8"))["cv"]["k"])
    assert set(folds["cv_fold"].astype(int)) == set(range(k)), f"check 6: fold ids are not 0..{k - 1}"
    joined = combined.merge(folds.assign(cv_fold=folds["cv_fold"].astype(int)), on="cv_group")
    n_cat, n_pri = combined["category"].nunique(), combined["priority"].nunique()
    for fold, part in joined.groupby("cv_fold"):
        assert part["category"].nunique() == n_cat, f"check 6: fold {fold} lacks a category"
        assert part["priority"].nunique() == n_pri, f"check 6: fold {fold} lacks a priority"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cv_folds.csv"
        run = subprocess.run(
            [sys.executable, str(SCRIPTS / "make_folds.py"), "--out", str(out)],
            capture_output=True,
            check=False,
        )
        assert run.returncode == 0, f"check 6: make_folds.py failed: {run.stderr[-300:]!r}"
        same = out.read_bytes() == (CLEAN / "cv_folds.csv").read_bytes()
        assert same, "check 6: make_folds.py output not reproducible"
    sizes = joined.groupby("cv_fold").size().tolist()
    ok(6, f"{len(folds)} groups in {k} folds, {n_cat} categories and {n_pri} priorities per fold, "
          f"rows/fold {'/'.join(map(str, sizes))}; byte-identical re-run")


def check_label_flags(scenarios: pd.DataFrame) -> None:
    """Check 7: label_flags.csv ids exist, official labels match, soft targets valid with official argmax."""
    flags = read(CLEAN / "label_flags.csv")
    by_id = scenarios.set_index("scenario_id")
    soft = 0
    for row in flags.itertuples():
        assert row.scenario_id in by_id.index, f"check 7: unknown scenario {row.scenario_id}"
        assert row.field in ("category", "priority"), f"check 7: bad field {row.field}"
        actual = by_id.loc[row.scenario_id, row.field]
        assert row.official_label == actual, f"check 7: {row.scenario_id} official_label != {actual}"
        assert row.core == by_id.loc[row.scenario_id, "core"], f"check 7: {row.scenario_id} core differs"
        if row.decision == "keep + soft":
            target = json.loads(row.soft_target)
            assert abs(sum(target.values()) - 1.0) < 1e-9, f"check 7: {row.scenario_id} soft target sum != 1"
            best = max(target.values())
            winners = [label for label, p in target.items() if p == best]
            assert winners == [row.official_label], f"check 7: {row.scenario_id} argmax != official"
            soft += 1
        else:
            hard = row.decision == "keep (hard)" and row.soft_target == ""
            assert hard, f"check 7: {row.scenario_id} bad decision/soft_target"
    ok(7, f"label_flags.csv: {len(flags)} rows ({soft} soft); ids exist, labels match, argmax official")


def check_scripts(combined: pd.DataFrame) -> None:
    """Check 8: no Latin script in ar rows, no Arabic script in en rows."""
    latin_in_ar = combined[(combined["lang"] == "ar") & combined["text"].str.contains(LATIN)]
    arabic_in_en = combined[(combined["lang"] == "en") & combined["text"].str.contains(ARABIC)]
    assert latin_in_ar.empty, f"check 8: Latin in ar rows {latin_in_ar.request_id.tolist()[:5]}"
    assert arabic_in_en.empty, f"check 8: Arabic in en rows {arabic_in_en.request_id.tolist()[:5]}"
    ok(8, "no Latin letters in ar rows, no Arabic letters in en rows")


def check_normalize(combined: pd.DataFrame, cd: ModuleType) -> None:
    """Check 9: normalize is idempotent; text_norm has no diacritics, tatweel or unmapped letters."""
    for text_norm, lang in zip(combined["text_norm"], combined["lang"], strict=True):
        assert cd.normalize(text_norm, lang) == text_norm, f"check 9: not idempotent on {text_norm!r}"
        assert not cd.AR_DIACRITICS.search(text_norm), f"check 9: diacritics/tatweel in {text_norm!r}"
        assert text_norm.translate(cd.AR_CHARMAP) == text_norm, f"check 9: unmapped letter in {text_norm!r}"
    ok(9, "normalize idempotent on 432 rows; no diacritics, tatweel or unmapped alef/ya/ta-marbuta")


def check_unseen_wrappers(cd: ModuleType) -> None:
    """Check 10: document that clean_data.py does NOT strip unseen wrapper forms (P1.1 covers them)."""
    prefixes, suffixes = set(cd.KNOWN_PREFIXES), set(cd.KNOWN_SUFFIXES)
    for text in UNSEEN_WRAPPERS:
        _, _, core = cd.strip_wrappers(text, prefixes, suffixes)
        stripped = core == "The bus is late"
        assert stripped is False, f"check 10: clean_data.py now strips {text!r}; update the audit notes"
    ok(10, f"documented: clean_data.py leaves {list(UNSEEN_WRAPPERS)} unstripped (stripped=False); "
           "the package WrapperStripper (P1.1) covers them")


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "datasets.yaml").read_text(encoding="utf-8"))
    cd = load_clean_data()
    combined = read(CLEAN / "train_val_combined.csv")
    scenarios = read(CLEAN / "scenarios.csv")
    check_regeneration()
    check_labels_equal_raw(combined)
    check_near_duplicates(combined, float(cfg["audit"]["near_dup_cosine"]))
    check_groups(combined, scenarios)
    check_folds(combined)
    check_label_flags(scenarios)
    check_scripts(combined)
    check_normalize(combined, cd)
    check_unseen_wrappers(cd)
    print("DATA AUDIT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
