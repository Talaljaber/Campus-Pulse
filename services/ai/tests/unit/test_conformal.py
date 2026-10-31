"""LACConformal on synthetic probability vectors (P1.14, ARCHITECTURE §3.5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from campuspulse_ai.adapters.uncertainty.conformal import LACConformal, MondrianByLang
from campuspulse_ai.domain.labels import CATEGORY_LABELS
from campuspulse_ai.domain.ports import ConformalPredictor
from campuspulse_ai.domain.values import ProbVector

SEED = 42
N = 2000
ALPHA = 0.10
TOLERANCE = 0.03


def _synthetic(
    n: int, rng: np.random.Generator, concentration: float = 0.5
) -> tuple[list[ProbVector], list[str]]:
    """Calibrated toy model: p ~ Dirichlet, and the true label is drawn from p itself."""
    k = len(CATEGORY_LABELS)
    raw = rng.dirichlet(np.full(k, concentration), size=n)
    probs, labels = [], []
    for row in raw:
        values = tuple(float(v) for v in row / row.sum())
        fixed = (*values[:-1], 1.0 - sum(values[:-1]))  # exact sum for ProbVector validation
        probs.append(ProbVector(fixed, CATEGORY_LABELS))
        weights = np.clip(fixed, 0, None)
        labels.append(CATEGORY_LABELS[int(rng.choice(k, p=weights / weights.sum()))])
    return probs, labels


def test_coverage_within_3pts_at_n2000() -> None:
    rng = np.random.default_rng(SEED)
    cal_p, cal_y = _synthetic(N, rng)
    test_p, test_y = _synthetic(N, rng)
    lac = LACConformal("category", ALPHA)
    assert isinstance(lac, ConformalPredictor)
    lac.calibrate(cal_p, cal_y, groups=[str(i) for i in range(N)])
    covered = np.mean([y in lac.predict_set(p).labels for p, y in zip(test_p, test_y, strict=True)])
    assert abs(covered - (1 - ALPHA)) <= TOLERANCE, covered
    assert lac.n_calib == N and lac.n_groups == N and 0.0 <= lac.q <= 1.0


def test_set_size_monotone_in_alpha() -> None:
    rng = np.random.default_rng(SEED)
    cal_p, cal_y = _synthetic(N, rng)
    test_p, _ = _synthetic(500, rng)
    sizes = []
    for alpha in (0.05, 0.10, 0.20, 0.30):
        lac = LACConformal("category", alpha)
        lac.calibrate(cal_p, cal_y, groups=["g"] * N)
        sizes.append(np.mean([lac.predict_set(p).size for p in test_p]))
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > sizes[-1]
    with pytest.raises(ValueError, match="at least"):
        LACConformal("category", ALPHA).calibrate(cal_p[:9], cal_y[:9], ["g"] * 9)


def test_empty_set_falls_back_to_argmax() -> None:
    lac = LACConformal.from_quantile("priority", ALPHA, q=0.05, n_calib=100)  # threshold p >= 0.95
    flat = ProbVector((0.3, 0.3, 0.4), ("low", "medium", "high"))
    result = lac.predict_set(flat)
    assert result.labels == frozenset({"high"}) and lac.last_was_empty
    sure = ProbVector((0.01, 0.01, 0.98), ("low", "medium", "high"))
    assert lac.predict_set(sure).labels == frozenset({"high"}) and not lac.last_was_empty
    assert lac.predict_set_with_flag(flat) == (result, True)
    with pytest.raises(ValueError, match="not calibrated"):
        LACConformal("priority", ALPHA).predict_set(flat)


def test_save_load(tmp_path: Path) -> None:
    rng = np.random.default_rng(SEED)
    cal_p, cal_y = _synthetic(200, rng)
    lac = LACConformal("category", ALPHA)
    lac.calibrate(cal_p, cal_y, groups=[f"g{i % 30}" for i in range(200)])
    lac.save(tmp_path / "conformal" / "category")
    back = LACConformal.load(tmp_path / "conformal" / "category")
    got = (back.target, back.alpha, back.q, back.n_calib, back.n_groups)
    assert got == ("category", ALPHA, lac.q, 200, 30)
    assert all(back.predict_set(p) == lac.predict_set(p) for p in cal_p[:50])


def test_mondrian_uses_the_language_quantile_and_falls_back(tmp_path: Path) -> None:
    """P2.10: a wider Arabic quantile widens Arabic sets only; unknown languages use the global q."""
    glob = LACConformal.from_quantile("category", ALPHA, 0.5, 432, 30)
    ar = LACConformal.from_quantile("category", ALPHA, 0.9, 135, 15)
    mond = MondrianByLang({"ar": ar}, glob)
    p = ProbVector((0.6, 0.2, 0.1, 0.05, 0.03, 0.02), CATEGORY_LABELS)
    assert mond.predict_set_for(p, "en").size == 1  # q 0.5: labels with p >= 0.5
    assert mond.predict_set_for(p, "arabizi").size == 1  # no own quantile: the global one
    assert mond.predict_set_for(p, "ar").size == 3  # q 0.9: labels with p >= 0.1
    assert mond.predict_set(p) == glob.predict_set(p)
    mond.save(tmp_path / "category")
    again = MondrianByLang.load(tmp_path / "category")
    assert again.predict_set_for(p, "ar") == mond.predict_set_for(p, "ar")
    assert LACConformal.load(tmp_path / "category").q == pytest.approx(0.5)  # the fallback file stays readable
