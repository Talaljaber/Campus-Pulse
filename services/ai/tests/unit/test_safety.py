"""SafetyGuard on the official data and the distress fixtures (P1.5, LD-19)."""

from __future__ import annotations

import pandas as pd
import pytest
import yaml

from campuspulse_ai.adapters.guards.bank import compile_bank
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS, REPO_ROOT
from campuspulse_ai.domain.values import GuardVerdict

FIXTURES = REPO_ROOT / "services" / "ai" / "tests" / "fixtures"
MAX_TOKENS = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))["guards"]["max_tokens"]
SAFETY_SCENARIOS = {"TR-S03", "TR-S19", "TR-S29", "TR-S31"}  # stuck lab door, leak near power x2, stranded


@pytest.fixture(scope="module")
def guard() -> SafetyGuard:
    path = LEXICONS / "safety.yaml"
    return SafetyGuard(compile_bank(path, "danger"), compile_bank(path, "distress"))


@pytest.fixture(scope="module")
def verdicts(guard: SafetyGuard) -> pd.DataFrame:
    """One row per official request with its safety verdict kind."""
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)
    df = pd.read_csv(DATA_CLEAN / "train_val_combined.csv", dtype=str, keep_default_na=False)
    df["kind"] = [guard.inspect(normalizer.normalize(t)).kind for t in df.text]
    return df


def test_official_safety_scenarios_are_danger(verdicts: pd.DataFrame) -> None:
    danger = verdicts[verdicts.kind == "danger"]
    assert set(danger.scenario_id) == SAFETY_SCENARIOS
    expected = verdicts[verdicts.scenario_id.isin(SAFETY_SCENARIOS)]
    assert (expected.kind == "danger").all()


def test_zero_danger_on_non_high_official_rows(verdicts: pd.DataFrame) -> None:
    non_high = verdicts[verdicts.priority != "high"]
    assert len(non_high) > 0
    assert list(non_high[non_high.kind != "none"].request_id) == []


def test_distress_fixtures_flag_and_zero_on_official(guard: SafetyGuard, verdicts: pd.DataFrame) -> None:
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)
    lines = [ln for ln in (FIXTURES / "distress_fixtures.txt").read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 10
    for line in lines:
        verdict = guard.inspect(normalizer.normalize(line))
        assert isinstance(verdict, GuardVerdict)
        assert verdict.kind == "distress", line
    assert list(verdicts[verdicts.kind == "distress"].request_id) == []


TRAPPED = [
    "The elevator in building C is stuck between floors with people inside",
    "Two students are stuck inside the lift on the 3rd floor",
    "المصعد علق بين الطوابق وفيه ناس جواه",
    "في ناس محبوسين بالأسانسير بمبنى C",
]
NOT_DANGER = [
    "The elevator in building C is stuck on the ground floor",
    "My locker door is stuck",
    "The registration page is stuck on loading",
    "المصعد واقف عن الشغل من مبارح",
]


def test_people_trapped_in_a_lift_is_danger_but_a_stuck_lift_is_not(guard: SafetyGuard) -> None:
    """Live rc1 finding: trapped people must floor priority to high; a stuck lift alone stays a fault."""
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)
    assert [t for t in TRAPPED if guard.inspect(normalizer.normalize(t)).kind != "danger"] == []
    assert [t for t in NOT_DANGER if guard.inspect(normalizer.normalize(t)).kind == "danger"] == []
