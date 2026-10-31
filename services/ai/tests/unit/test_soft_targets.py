"""SoftTargetExpander on the official pool (P1.8, ARCHITECTURE §3.3)."""

from __future__ import annotations

from collections import defaultdict

import pytest

from campuspulse_ai.adapters.models.soft_targets import SoftTargetExpander
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.pool import OFFICIAL_CSV, Pool, load_pool
from campuspulse_ai.config.paths import DATA_CLEAN, LEXICONS

FLAGS = DATA_CLEAN / "label_flags.csv"
TARGETS = ("category", "priority")


@pytest.fixture(scope="module")
def pool() -> Pool:
    return load_pool([OFFICIAL_CSV], DefaultNormalizer.from_lexicons(LEXICONS, 256))


@pytest.fixture(scope="module")
def expander() -> SoftTargetExpander:
    return SoftTargetExpander(FLAGS)


def _hard(pool: Pool, target: str) -> tuple[str, ...]:
    return pool.category if target == "category" else pool.priority


def test_weights_sum_to_original_count(pool: Pool, expander: SoftTargetExpander) -> None:
    for target in TARGETS:
        _check_sums(pool, expander, target)


def _check_sums(pool: Pool, expander: SoftTargetExpander, target: str) -> None:
    idx, _, weights = expander.expand(pool, target)  # type: ignore[arg-type]
    per_scenario: dict[str, float] = defaultdict(float)
    for i, w in zip(idx, weights, strict=True):
        per_scenario[pool.scenario_id[i]] += w
    counts: dict[str, int] = defaultdict(int)
    for sid in pool.scenario_id:
        counts[sid] += 1
    assert per_scenario == pytest.approx(dict(counts))
    assert sorted(set(idx)) == list(range(len(pool)))  # every row kept


def test_argmax_equals_official_label(pool: Pool, expander: SoftTargetExpander) -> None:
    for target in TARGETS:
        _check_argmax(pool, expander, target)


def _check_argmax(pool: Pool, expander: SoftTargetExpander, target: str) -> None:
    idx, labels, weights = expander.expand(pool, target)  # type: ignore[arg-type]
    best: dict[int, tuple[float, str]] = {}
    for i, lab, w in zip(idx, labels, weights, strict=True):
        if i not in best or w > best[i][0]:
            best[i] = (w, lab)
    hard = _hard(pool, target)
    assert all(best[i][1] == hard[i] for i in range(len(pool)))
    # the flagged scenarios really are expanded (never 50/50)
    flagged = set(expander.flagged(target))  # type: ignore[arg-type]
    expected = {"priority": {"TR-S27", "TR-S33", "TR-S06"}, "category": {"TR-S18"}}[target]
    assert flagged == expected
    for i in range(len(pool)):
        if pool.scenario_id[i] in flagged:
            assert idx.count(i) == 2


def test_unflagged_rows_unchanged(pool: Pool, expander: SoftTargetExpander) -> None:
    for target in TARGETS:
        idx, labels, weights = expander.expand(pool, target)  # type: ignore[arg-type]
        flagged = set(expander.flagged(target))  # type: ignore[arg-type]
        hard = _hard(pool, target)
        rows = [(i, lab, w) for i, lab, w in zip(idx, labels, weights, strict=True)
                if pool.scenario_id[i] not in flagged]
        assert rows == [(i, hard[i], 1.0) for i in range(len(pool)) if pool.scenario_id[i] not in flagged]
