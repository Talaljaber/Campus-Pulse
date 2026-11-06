#!/usr/bin/env python3
"""Validate a hand-written or drafted dataset CSV against its schema (P1.0; ARCHITECTURE §4.2).

    python scripts/validate_dataset.py --kind {our_test|augmented|probes} <csv>

Prints one `OK <kind>: ...` line and exits 0, or prints one line per violation and exits 1.
Every floor and pattern comes from `config/datasets.yaml` (block named like the kind); labels come from
`campuspulse_ai.domain.labels`. The script only reads: it never edits a dataset.

Checks per kind:
- all kinds: columns exactly as configured, UTF-8 (a BOM is accepted, read with `utf-8-sig`), unique
  `request_id` matching the configured pattern, non-empty text, `lang` in the configured set, labels spelled
  exactly as the official labels.
- our_test (D-010: built from the set files by `scripts/build_our_test.py`): `author_method` and
  `test_set` in the lists of `config/datasets.yaml`, non-empty `scenario_family` and `notes`; on the POOLED
  file: at least `min_rows` rows,
  `min_per_cell` rows in each of the 18 category x priority cells, `min_per_lang` rows per language,
  `min_wrapped_rows` rows carrying an official-style wrapper, no duplicate normalized text, and no row whose
  normalized core equals an official `text_norm` (`clean_data.normalize(core, lang)` via a read-only
  importlib load of `scripts/clean_data.py`, plus the package `WrapperStripper` for wrapper variants).
- augmented: `source`, `author_method` and `needs_human_check` (True/False) valid, `source_scenario_id`
  present; a row deriving from an official scenario must carry that scenario's `cv_group` and labels; any
  other scenario/group must match `new_group_pattern`, and all rows of one new scenario share its labels.
- probes: `style` from the configured list (at least `min_per_style` each), `author_method` valid,
  `expected_flags` drawn from the domain flag set, `base_request_id` (when set) present in
  `data/our_test/our_test.csv`, no overlap with official `text_norm`.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

import pandas as pd
import yaml

from campuspulse_ai.adapters.preprocess.wrappers import WrapperStripper
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.values import FLAGS

ROOT = Path(__file__).resolve().parent.parent
DATASETS_YAML = ROOT / "config" / "datasets.yaml"
WRAPPERS_YAML = ROOT / "config" / "lexicons" / "wrappers.yaml"
CLEAN_DATA = ROOT / "scripts" / "clean_data.py"
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
OUR_TEST_CSV = ROOT / "data" / "our_test" / "our_test.csv"

Kind = Literal["our_test", "augmented", "probes"]
KINDS: tuple[str, ...] = ("our_test", "augmented", "probes")
BOOL_VALUES: Mapping[str, bool] = {"true": True, "false": False}


@dataclass(frozen=True)
class DatasetSpec:
    """The `config/datasets.yaml` block for one kind (plain mapping, validated where used)."""

    kind: str
    rules: Mapping[str, Any]

    @classmethod
    def load(cls, kind: str, path: Path = DATASETS_YAML) -> DatasetSpec:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        if kind not in cfg:
            raise KeyError(f"{path} has no `{kind}` block")
        return cls(kind=kind, rules=cfg[kind])


@dataclass
class ValidationReport:
    """Outcome of `validate`: `errors` is empty when the file is valid; `summary` is the OK line body."""

    kind: str
    rows: int
    errors: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class Official:
    """What the validator needs from the official data."""

    text_norms: frozenset[str]
    scenarios: Mapping[str, tuple[str, str, str]]  # scenario_id -> (cv_group, category, priority)
    groups: frozenset[str]


def load_clean_data() -> ModuleType:
    """Import `scripts/clean_data.py` read-only (its `run()` only executes under `__main__`)."""
    spec = importlib.util.spec_from_file_location("clean_data", CLEAN_DATA)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {CLEAN_DATA}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_official() -> Official:
    df = pd.read_csv(COMBINED, encoding="utf-8", dtype=str, keep_default_na=False)
    scenarios = {
        sid: (grp.cv_group.iloc[0], grp.category.iloc[0], grp.priority.iloc[0])
        for sid, grp in df.groupby("scenario_id", sort=True)
    }
    return Official(frozenset(df.text_norm), scenarios, frozenset(df.cv_group))


def _read(path: Path, columns: Sequence[str], errors: list[str]) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        errors.append(f"{path}: unreadable as UTF-8 CSV: {exc}")
        return None
    if list(df.columns) != list(columns):
        errors.append(f"{path}: columns must be exactly {','.join(columns)}; got {','.join(df.columns)}")
        return None
    return df


def _common_checks(df: pd.DataFrame, rules: Mapping[str, Any], label_cols: tuple[str, str],
                   errors: list[str]) -> None:
    """Ids, text, lang and label spellings: one error line per violating row."""
    id_re = re.compile(rules["id_pattern"])
    for rid, n in Counter(df.request_id).items():
        if n > 1:
            errors.append(f"request_id {rid!r}: duplicated {n} times")
    cat_col, pri_col = label_cols
    for i, row in enumerate(df.itertuples(index=False), start=2):  # line 1 is the header
        where = f"line {i} ({row.request_id})"
        if not id_re.match(row.request_id):
            errors.append(f"{where}: request_id must match {rules['id_pattern']}")
        if not row.text.strip():
            errors.append(f"{where}: empty text")
        if row.lang not in rules["langs"]:
            errors.append(f"{where}: lang {row.lang!r} not in {rules['langs']}")
        if getattr(row, cat_col) not in CATEGORY_LABELS:
            errors.append(f"{where}: {cat_col} {getattr(row, cat_col)!r} is not an official category")
        if getattr(row, pri_col) not in PRIORITY_LABELS:
            errors.append(f"{where}: {pri_col} {getattr(row, pri_col)!r} is not an official priority")


class _Normalizer:
    """`clean_data.normalize(core, lang)` with the clean_data stripper and the package stripper."""

    def __init__(self) -> None:
        self._cd = load_clean_data()
        self._wrappers = WrapperStripper.from_yaml(WRAPPERS_YAML)

    def forms(self, text: str) -> tuple[set[str], bool]:
        """(normalized cores, carries a wrapper) for one raw text."""
        cd = self._cd
        prefix, suffix, core = cd.strip_wrappers(text, cd.KNOWN_PREFIXES, cd.KNOWN_SUFFIXES)
        stripped = self._wrappers.strip(text)
        forms = {
            cd.normalize(core, cd.detect_lang(text)),
            cd.normalize(stripped.core, cd.detect_lang(stripped.core)),
        }
        wrapped = bool(prefix or suffix or stripped.prefix or stripped.suffix or stripped.stated_urgency)
        return {f for f in forms if f}, wrapped


def _overlaps(df: pd.DataFrame, official: Official, norm: _Normalizer, errors: list[str], *,
              forbid_official: bool, label_cols: tuple[str, str]) -> tuple[int, int, int]:
    """Errors for official-text overlaps (if `forbid_official`) and for in-file label conflicts.

    Several rows may share a normalized core (wrapper variants of one scenario, like the official data and
    the D-010 holdout sets); they must then carry the same labels.

    Returns:
        (rows overlapping an official text_norm, rows carrying a wrapper, distinct normalized cores).
    """
    overlaps = wrapped_rows = 0
    seen: dict[str, tuple[str, tuple[str, str]]] = {}
    for row in df.itertuples(index=False):
        forms, wrapped = norm.forms(row.text)
        wrapped_rows += wrapped
        hit = sorted(forms & official.text_norms)
        if hit:
            overlaps += 1
        if hit and forbid_official:
            errors.append(f"{row.request_id}: normalized text equals an official text_norm: {hit[0]!r}")
        labels = (getattr(row, label_cols[0]), getattr(row, label_cols[1]))
        for form in sorted(forms):
            first_id, first_labels = seen.setdefault(form, (row.request_id, labels))
            if first_labels != labels:
                errors.append(f"{row.request_id}: same normalized text as {first_id} but labels "
                              f"{'/'.join(labels)} != {'/'.join(first_labels)}: {form!r}")
    return overlaps, wrapped_rows, len(seen)


def _validate_our_test(df: pd.DataFrame, rules: Mapping[str, Any], official: Official,
                       errors: list[str]) -> str:
    _common_checks(df, rules, ("category", "priority"), errors)
    methods, sets = rules["author_methods"], rules["test_sets"]
    for row in df.itertuples(index=False):
        if row.author_method not in methods:
            errors.append(f"{row.request_id}: author_method {row.author_method!r} not in {methods}")
        if row.test_set not in sets:
            errors.append(f"{row.request_id}: test_set {row.test_set!r} not in {sets}")
        if not row.scenario_family.strip():
            errors.append(f"{row.request_id}: scenario_family is required")
        if not row.notes.strip():
            errors.append(f"{row.request_id}: notes must say how the row was written")
    # floors are checked on the pooled file (D-010)
    if len(df) < rules["min_rows"]:
        errors.append(f"{len(df)} rows; need >= {rules['min_rows']}")
    cells = Counter(zip(df.category, df.priority, strict=True))
    floor = rules["min_per_cell"]
    full = [(c, p) for c in CATEGORY_LABELS for p in PRIORITY_LABELS if cells[(c, p)] >= floor]
    for c in CATEGORY_LABELS:
        for p in PRIORITY_LABELS:
            if cells[(c, p)] < floor:
                errors.append(f"cell {c} x {p}: {cells[(c, p)]} rows; need >= {floor}")
    langs = Counter(df.lang)
    for lang, floor in rules["min_per_lang"].items():
        if langs[lang] < floor:
            errors.append(f"lang {lang}: {langs[lang]} rows; need >= {floor}")
    overlaps, wrapped, cores = _overlaps(df, official, _Normalizer(), errors,
                                         forbid_official=rules["forbid_official_overlap"],
                                         label_cols=("category", "priority")) if len(df) else (0, 0, 0)
    if wrapped < rules["min_wrapped_rows"]:
        errors.append(f"{wrapped} rows carry an official-style wrapper; need >= {rules['min_wrapped_rows']}")
    n_cells = len(CATEGORY_LABELS) * len(PRIORITY_LABELS)
    lang_text = " ".join(f"{lang}={langs[lang]}" for lang in rules["langs"])
    per_set = Counter(df.test_set)
    set_text = " ".join(f"{s}={per_set[s]}" for s in sets)
    return (f"{len(df)} rows; cells {len(full)}/{n_cells} (min ≥{rules['min_per_cell']}); langs {lang_text}; "
            f"{overlaps} overlaps with official text_norm; sets {set_text}; {cores} distinct cores")


def _parse_bool(value: str) -> bool | None:
    return BOOL_VALUES.get(value.strip().lower())


def _validate_augmented(df: pd.DataFrame, rules: Mapping[str, Any], official: Official,
                        errors: list[str]) -> str:
    _common_checks(df, rules, ("category", "priority"), errors)
    method_pattern, new_pattern = rules["author_method_pattern"], rules["new_group_pattern"]
    method_re, new_re = re.compile(method_pattern), re.compile(new_pattern)
    new_labels: dict[str, set[tuple[str, str]]] = {}
    reviewed = 0
    for row in df.itertuples(index=False):
        rid = row.request_id
        flag = _parse_bool(row.needs_human_check)
        if flag is None:
            errors.append(f"{rid}: needs_human_check must be True or False, got {row.needs_human_check!r}")
        elif not flag:
            reviewed += 1
        if row.source not in rules["sources"]:
            errors.append(f"{rid}: source {row.source!r} not in {rules['sources']}")
        if not method_re.match(row.author_method):
            errors.append(f"{rid}: author_method {row.author_method!r} must match {method_pattern}")
        sid = row.source_scenario_id.strip()
        if not sid:
            errors.append(f"{rid}: source_scenario_id is required")
            continue
        if sid in official.scenarios:
            group, cat, pri = official.scenarios[sid]
            if row.cv_group != group:
                errors.append(f"{rid}: cv_group {row.cv_group!r} != {group!r} of source scenario {sid}")
            if (row.category, row.priority) != (cat, pri):
                got = f"{row.category}/{row.priority}"
                errors.append(f"{rid}: labels {got} != source scenario {sid} {cat}/{pri}")
        elif new_re.match(sid):
            new_labels.setdefault(sid, set()).add((row.category, row.priority))
            if row.cv_group not in official.groups and not new_re.match(row.cv_group):
                errors.append(f"{rid}: unknown cv_group {row.cv_group!r} (official group or {new_pattern})")
        else:
            errors.append(f"{rid}: source_scenario_id {sid!r} is neither official nor {new_pattern}")
    for sid, labels in sorted(new_labels.items()):
        if len(labels) > 1:
            errors.append(f"new scenario {sid}: rows disagree on labels {sorted(labels)}")
    cells = {(c, p) for c, p in zip(df.category, df.priority, strict=True)}
    n_cells = len(CATEGORY_LABELS) * len(PRIORITY_LABELS)
    return (f"{len(df)} rows; {reviewed} reviewed; cv_groups all known; labels match source scenarios; "
            f"cells covered {len(cells)}/{n_cells}")


def _validate_probes(df: pd.DataFrame, rules: Mapping[str, Any], official: Official,
                     errors: list[str]) -> str:
    _common_checks(df, rules, ("intended_category", "intended_priority"), errors)
    base_ids: set[str] | None = None
    if OUR_TEST_CSV.is_file():
        base_df = pd.read_csv(OUR_TEST_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        base_ids = set(base_df.request_id)
    methods = rules["author_methods"]
    for row in df.itertuples(index=False):
        rid = row.request_id
        if row.style not in rules["styles"]:
            errors.append(f"{rid}: style {row.style!r} not in {rules['styles']}")
        if row.author_method not in methods:
            errors.append(f"{rid}: author_method {row.author_method!r} not in {methods}")
        flags = [f.strip() for f in row.expected_flags.split(rules["flag_separator"]) if f.strip()]
        unknown = sorted(set(flags) - FLAGS)
        if unknown:
            errors.append(f"{rid}: unknown expected_flags {unknown}")
        base = row.base_request_id.strip()
        if base and base_ids is not None and base not in base_ids:
            errors.append(f"{rid}: base_request_id {base!r} not in {OUR_TEST_CSV.name}")
        if not row.notes.strip():
            errors.append(f"{rid}: notes must say what the probe tests")
    if len(df) < rules["min_rows"]:
        errors.append(f"{len(df)} rows; need >= {rules['min_rows']}")
    styles = Counter(df["style"])
    for style in rules["styles"]:
        if styles[style] < rules["min_per_style"]:
            errors.append(f"style {style}: {styles[style]} rows; need >= {rules['min_per_style']}")
    if len(df):
        _overlaps(df, official, _Normalizer(), errors, forbid_official=rules["forbid_official_overlap"],
                  label_cols=("intended_category", "intended_priority"))
    full = sum(styles[s] >= rules["min_per_style"] for s in rules["styles"])
    langs = Counter(df.lang)
    lang_text = " ".join(f"{lang}={langs[lang]}" for lang in rules["langs"])
    return (f"{len(df)} rows; styles {full}/{len(rules['styles'])} (min ≥{rules['min_per_style']}); "
            f"langs {lang_text}")


def validate(path: Path, kind: Kind, spec: DatasetSpec) -> ValidationReport:
    """Validate one CSV. Never raises for data problems: they are returned as `errors`."""
    errors: list[str] = []
    df = _read(Path(path), spec.rules["columns"], errors)
    if df is None:
        return ValidationReport(kind, 0, errors)
    official = load_official()
    checkers = {"our_test": _validate_our_test, "augmented": _validate_augmented, "probes": _validate_probes}
    summary = checkers[kind](df, spec.rules, official, errors)
    return ValidationReport(kind, len(df), errors, summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic text in error lines on a cp1252 console
    report = validate(args.csv, args.kind, DatasetSpec.load(args.kind))
    if report.ok:
        print(f"OK {report.kind}: {report.summary}")
        return 0
    for line in report.errors:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
