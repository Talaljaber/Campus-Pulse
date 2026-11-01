"""The training pool: official rows + reviewed augmentation, normalized like inference (P1.8, §3.2).

`load_pool` is the only way training data enters `train.py` (LD-21). It refuses holdout paths
(`data/our_test`, `data/robustness`), drops augmentation rows still marked `needs_human_check`, runs every
row through the same `Normalizer` the core uses (so `model_text` is exactly what models see at inference),
and joins the frozen `cv_fold` on `cv_group` (LD-31). Labels are the official hard labels; soft targets
are applied later by `SoftTargetExpander` (§3.3).
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

from campuspulse_ai.adapters.preprocess.wrappers import collapse_ws, normalize_text, script_lang
from campuspulse_ai.config.paths import DATA_AUGMENTED, DATA_CLEAN, is_holdout
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import Normalizer
from campuspulse_ai.domain.values import Lang

OFFICIAL_CSV = DATA_CLEAN / "train_val_combined.csv"
FOLDS_CSV = DATA_CLEAN / "cv_folds.csv"
FEATURES_CSV = DATA_CLEAN / "train_val_features.csv"
OFFICIAL_COLUMNS = ("request_id", "text", "scenario_id", "cv_group", "category", "priority")
AUGMENTED_COLUMNS = ("request_id", "text", "lang", "source", "source_scenario_id", "cv_group",
                     "needs_human_check", "author_method", "category", "priority")
MODEL_PANEL_CSV = DATA_AUGMENTED / "review" / "model_panel_v1.csv"  # P8.1b audit log: votes + review_status
MODEL_PANEL_STATUS = "model_panel_v1"
OFFICIAL_SOURCE = "official"
NO_FOLD = -1  # cv_fold of a group missing from cv_folds.csv; `group_folds` refuses it
_BOOLS: Mapping[str, bool] = {"true": True, "false": False}


@dataclass(frozen=True)
class Pool:
    """Aligned tuples, one entry per training text (index i is the same row in every field).

    `lang` is the package `LangIdentifier` label (en/ar/arabizi); `lang_script` is the CSV-style script label
    (`train_val_features.csv` for official rows, the script ratio for augmented ones). `scenario_id` is the
    official scenario id, or an augmented row's `source_scenario_id`. `cv_fold` is `NO_FOLD` (-1) for a group
    that `scripts/make_folds.py --include-augmented` has not placed yet.
    """

    request_id: tuple[str, ...]
    raw: tuple[str, ...]
    model_text: tuple[str, ...]
    text_norm: tuple[str, ...]
    lang: tuple[Lang, ...]
    lang_script: tuple[str, ...]
    category: tuple[str, ...]
    priority: tuple[str, ...]
    cv_group: tuple[str, ...]
    cv_fold: tuple[int, ...]
    source: tuple[str, ...]
    scenario_id: tuple[str, ...]
    is_official: tuple[bool, ...]
    category_only: tuple[bool, ...] = ()  # P8.1c: rows that may teach the category side only (empty = none)

    def __post_init__(self) -> None:
        if not self.category_only:
            object.__setattr__(self, "category_only", (False,) * len(self.request_id))
        sizes = {len(getattr(self, f.name)) for f in fields(self)}
        if len(sizes) > 1:
            raise ValueError(f"Pool fields must have equal lengths, got {sorted(sizes)}")

    def __len__(self) -> int:
        return len(self.request_id)

    def select(self, indices: Iterable[int]) -> Pool:
        """A sub-pool with the given rows, in the given order."""
        idx = list(indices)
        return Pool(**{f.name: tuple(getattr(self, f.name)[i] for i in idx) for f in fields(self)})


def default_pool_paths(*, include_augmented: bool = True) -> list[Path]:
    """`train_val_combined.csv`, then every `data/augmented/*.csv` in name order."""
    paths = [OFFICIAL_CSV]
    if include_augmented and DATA_AUGMENTED.is_dir():
        paths.extend(sorted(DATA_AUGMENTED.glob("*.csv")))
    return paths


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """(header, rows) of a UTF-8 CSV (a BOM is accepted); every value is a string."""
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [dict(r) for r in reader]
            return list(reader.fieldnames or []), rows
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise InvalidInput(f"{path}: unreadable CSV: {exc}") from exc


def _check_labels(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    bad_cat = sorted({r["category"] for r in rows} - set(CATEGORY_LABELS))
    bad_pri = sorted({r["priority"] for r in rows} - set(PRIORITY_LABELS))
    if bad_cat or bad_pri:
        raise InvalidInput(f"{path}: labels outside the official set: {bad_cat + bad_pri}")


@dataclass(frozen=True)
class _Row:
    request_id: str
    raw: str
    model_text: str
    text_norm: str
    lang: Lang
    lang_script: str
    category: str
    priority: str
    cv_group: str
    cv_fold: int
    source: str
    scenario_id: str
    is_official: bool
    category_only: bool = False


def _to_pool(rows: Sequence[_Row]) -> Pool:
    return Pool(
        request_id=tuple(r.request_id for r in rows),
        raw=tuple(r.raw for r in rows),
        model_text=tuple(r.model_text for r in rows),
        text_norm=tuple(r.text_norm for r in rows),
        lang=tuple(r.lang for r in rows),
        lang_script=tuple(r.lang_script for r in rows),
        category=tuple(r.category for r in rows),
        priority=tuple(r.priority for r in rows),
        cv_group=tuple(r.cv_group for r in rows),
        cv_fold=tuple(r.cv_fold for r in rows),
        source=tuple(r.source for r in rows),
        scenario_id=tuple(r.scenario_id for r in rows),
        is_official=tuple(r.is_official for r in rows),
        category_only=tuple(r.category_only for r in rows),
    )


def load_pool(
    paths: Sequence[Path],
    normalizer: Normalizer,
    *,
    use_augmentation: bool = True,
    strip_wrappers: bool = True,
    folds_csv: Path = FOLDS_CSV,
    features_csv: Path = FEATURES_CSV,
    include_unreviewed: bool = False,
    include_model_reviewed: bool = False,
    model_panel_csv: Path = MODEL_PANEL_CSV,
    model_reviewed_priority: bool = True,
) -> Pool:
    """Build the training pool from official and augmented CSVs (see the module docstring).

    Args:
        paths: CSV files; the official file has `scenario_id` (the `train_val_combined.csv` schema), an
            augmented file has the §4.2 augmentation schema. Rows keep file order, files keep `paths` order.
        normalizer: the inference `Normalizer` (`DefaultNormalizer` over the lexicon snapshot).
        use_augmentation: False skips augmented files (official-only ablation).
        strip_wrappers: False (P2.9 ablation) feeds the normalized raw `text` (wrappers kept) as
            `model_text` for EN/AR rows; Arabizi rows keep their normalizer `model_text`.
        folds_csv: frozen `cv_group,cv_fold` table (LD-31).
        features_csv: `train_val_features.csv` for the official `lang_script`.
        include_unreviewed: True keeps augmented rows still marked `needs_human_check=True`. Only two
            callers may pass it: `scripts/check_leakage.py` (it must see every candidate row) and the
            clearly labelled "unreviewed augmentation" ablation arm of `evaluate.py`. `train.py` never
            does, so a frozen model never trains on an unchecked row.
        include_model_reviewed: True also keeps rows still marked `needs_human_check=True` whose id
            has `review_status=model_panel_v1` in `model_panel_csv` (kept or fixed by the three-model panel,
            P8.1b). These rows are NOT human-reviewed: a separate, disclosed arm (D-049), default off.
        model_reviewed_priority: False marks those model-panel rows `category_only` (P8.1c, D-054): training
            keeps them out of every priority-side input (priority members, head, kNN priority index,
            priority temperature). Default True (C1 behaviour).

    Raises:
        InvalidInput: a holdout path, an unreadable file, an unknown schema or missing column, a label
            outside the official set, an augmented row without `source_scenario_id` or with a
            `needs_human_check` value other than True/False, a duplicate `request_id`, or a text the
            normalizer rejects.
    """
    for path in paths:
        if is_holdout(Path(path)):
            raise InvalidInput(f"refusing holdout path {path}: our_test/robustness are never trained on")
    fold_of = {r["cv_group"]: int(r["cv_fold"]) for r in _read(folds_csv)[1]}
    script_of = {r["request_id"]: r["lang_script"] for r in _read(features_csv)[1]}
    out: list[_Row] = []
    panel_ok: set[str] = set()
    if include_model_reviewed and not include_unreviewed:
        panel = _read(model_panel_csv)[1]
        panel_ok = {r["request_id"] for r in panel if r.get("review_status") == MODEL_PANEL_STATUS}

    def add(r: Mapping[str, str], *, lang_script: str, source: str, scenario_id: str, official: bool,
            category_only: bool = False) -> None:
        rid, raw = r["request_id"], r["text"]
        try:
            req = normalizer.normalize(raw)
        except InvalidInput as exc:
            raise InvalidInput(f"{rid}: {exc}") from exc
        model_text = req.model_text
        if not strip_wrappers and req.lang is not Lang.ARABIZI:
            model_text = normalize_text(collapse_ws(raw), script_lang(raw))
        out.append(_Row(rid, raw, model_text, req.text_norm, req.lang, lang_script, r["category"],
                        r["priority"],
                        r["cv_group"], fold_of.get(r["cv_group"], NO_FOLD), source, scenario_id, official,
                        category_only))

    for path in paths:
        columns, rows = _read(Path(path))
        if set(OFFICIAL_COLUMNS) <= set(columns) and "source_scenario_id" not in columns:
            _check_labels(path, rows)
            for r in rows:
                add(r, lang_script=script_of.get(r["request_id"]) or script_lang(r["text"]),
                    source=OFFICIAL_SOURCE, scenario_id=r["scenario_id"], official=True)
        elif tuple(columns) == AUGMENTED_COLUMNS:
            if not use_augmentation:
                continue
            _check_labels(path, rows)
            for r in rows:
                needs_check = _BOOLS.get(r["needs_human_check"].strip().lower())
                if needs_check is None:
                    raise InvalidInput(f"{path} {r['request_id']}: needs_human_check must be True/False")
                if not r["source_scenario_id"].strip():
                    raise InvalidInput(f"{path} {r['request_id']}: source_scenario_id is required")
                if needs_check and not include_unreviewed and r["request_id"] not in panel_ok:
                    continue  # not reviewed yet: never trained on
                add(r, lang_script=script_lang(r["text"]), source=r["source"],
                    scenario_id=r["source_scenario_id"].strip(), official=False,
                    category_only=needs_check and not model_reviewed_priority)
        else:
            raise InvalidInput(f"{path}: neither the official nor the augmentation schema: {columns}")
    counts = Counter(row.request_id for row in out)
    dupes = sorted(rid for rid, n in counts.items() if n > 1)
    if dupes:
        raise InvalidInput(f"duplicate request_id across pool files: {dupes[:5]}")
    return _to_pool(out)
