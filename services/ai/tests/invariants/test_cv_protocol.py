"""CV protocol invariants (P1.8, LD-31, §3.2): frozen folds, groups never split, holdouts refused."""

from __future__ import annotations

import pandas as pd
import pytest

from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.cv import group_folds
from campuspulse_ai.adapters.training.pool import Pool, default_pool_paths, load_pool
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS, OUR_TEST, ROBUSTNESS
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS

K = int(pd.read_csv(DATA_CLEAN / "cv_folds.csv").cv_fold.max()) + 1
assert "k: 5" in (CONFIG_DIR / "train.yaml").read_text(encoding="utf-8") and K == 5


@pytest.fixture(scope="module")
def normalizer() -> DefaultNormalizer:
    return DefaultNormalizer.from_lexicons(LEXICONS, 256)


@pytest.fixture(scope="module")
def pool(normalizer: DefaultNormalizer) -> Pool:
    return load_pool(default_pool_paths(), normalizer)


def test_groups_disjoint_per_fold(pool: Pool) -> None:
    for train, test in group_folds(pool, K):
        assert not {pool.cv_group[i] for i in train} & {pool.cv_group[i] for i in test}
        assert len(train) + len(test) == len(pool)


def test_no_text_norm_overlap_across_folds(pool: Pool) -> None:
    for train, test in group_folds(pool, K):
        assert not {pool.text_norm[i] for i in train} & {pool.text_norm[i] for i in test}


def test_translation_pairs_same_side(pool: Pool) -> None:
    scenarios = pd.read_csv(DATA_CLEAN / "scenarios.csv", dtype=str, keep_default_na=False)
    pairs = [(a, b) for a, b in zip(scenarios.scenario_id, scenarios.translation_of, strict=True) if b]
    assert len(pairs) == 24  # 12 pairs, listed from both sides
    fold_of = {}
    for sid, fold in zip(pool.scenario_id, pool.cv_fold, strict=True):
        assert fold_of.setdefault(sid, fold) == fold
    assert all(fold_of[a] == fold_of[b] for a, b in pairs)


def test_train_refuses_holdout_paths(normalizer: DefaultNormalizer) -> None:
    holdouts = (OUR_TEST / "our_test.csv", ROBUSTNESS / "probes.csv",
                DATA_CLEAN.parent / "Our_Test" / "a.csv")
    for path in holdouts:
        with pytest.raises(InvalidInput, match="holdout"):
            load_pool([DATA_CLEAN / "train_val_combined.csv", path], normalizer)


def test_folds_come_from_cv_folds_csv_and_cover_6_categories(pool: Pool) -> None:
    frozen = pd.read_csv(DATA_CLEAN / "cv_folds.csv", dtype={"cv_group": str, "cv_fold": int})
    fold_of = dict(zip(frozen.cv_group, frozen.cv_fold, strict=True))
    assert all(fold_of[g] == f for g, f in zip(pool.cv_group, pool.cv_fold, strict=True))
    splits = group_folds(pool, K)
    assert len(splits) == K
    for _, test in splits:
        assert {pool.category[i] for i in test} == set(CATEGORY_LABELS)
        assert {pool.priority[i] for i in test} == {"low", "medium", "high"}
    assert sorted(i for _, test in splits for i in test) == list(range(len(pool)))
