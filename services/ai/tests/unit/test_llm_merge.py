"""P3.3: LLMMerger keeps the LLM inside the conformal sets (ARCHITECTURE §3.9)."""

from __future__ import annotations

import random

import pytest
from fixtures.backend_fakes import FakeLAC, fake_call, make_core

from campuspulse_ai.application.services.llm_merge import LLMMerger, merge_vector
from campuspulse_ai.domain.entities import OracleAnswer
from campuspulse_ai.domain.errors import LLMOutputOutOfSet
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.values import PredictionSet, ProbVector, Tier

W_LLM = 0.5  # FrozenConfig llm.w_llm default (LD-10)
CONF_CAT = FakeLAC("category", q=0.7)
CONF_PRI = FakeLAC("priority", q=0.7)


def answer(cat: str | None, pri: str | None, tier: Tier = Tier.TIER1) -> OracleAnswer:
    return OracleAnswer(
        category=Category(cat) if cat else None,
        priority=Priority(pri) if pri else None,
        rationale="r",
        call=fake_call(tier),
    )


def _random_vector(rng: random.Random, labels: tuple[str, ...]) -> ProbVector:
    raw = [rng.random() ** 3 for _ in labels]  # skewed, sometimes near one-hot
    total = sum(raw)
    return ProbVector(tuple(v / total for v in raw), labels)


def test_merged_argmax_always_in_allowed_set_property() -> None:
    rng = random.Random(42)
    merger = LLMMerger()
    for _ in range(200):
        p_cat = _random_vector(rng, CATEGORY_LABELS)
        p_pri = _random_vector(rng, PRIORITY_LABELS)
        s_cat = rng.sample(CATEGORY_LABELS, rng.randint(2, 4))
        s_pri = rng.sample(PRIORITY_LABELS, rng.randint(1, 3))
        core = make_core(p_cat.as_dict(), p_pri.as_dict(), set_cat=s_cat, set_pri=s_pri)
        w = rng.choice([0.0, 0.2, W_LLM, 0.8, 1.0])
        ans = answer(rng.choice(s_cat), rng.choice([*s_pri, None]))
        merged = merger.merge(core, ans, w, CONF_CAT, CONF_PRI)
        assert merged.p_cat.argmax() in s_cat and merged.p_pri.argmax() in s_pri
        assert all(merged.p_cat.prob(lab) == 0.0 for lab in CATEGORY_LABELS if lab not in s_cat)
        assert merged.set_cat.labels <= set(s_cat) and merged.set_pri.labels <= set(s_pri)
        assert merged.set_cat.size >= 1 and merged.set_pri.size >= 1


def test_llm_vote_breaks_the_tie_and_records_the_tier() -> None:
    core = make_core(
        {"Registration": 0.48, "IT Support": 0.44}, {"high": 0.9}, set_cat=["Registration", "IT Support"]
    )
    before = (core.p_cat, core.set_cat, dict(core.per_model), core.tier)
    merged = LLMMerger().merge(core, answer("IT Support", "high"), W_LLM, CONF_CAT, CONF_PRI)
    assert merged.p_cat.argmax() == "IT Support"
    assert merged.set_cat.labels == {"IT Support"}  # 0.5·(.44/.92) + .5 ≈ .74 ≥ 1 − q
    assert merged.tier == Tier.TIER1
    assert merged.per_model["tier1.category"].prob("IT Support") == 1.0
    assert (core.p_cat, core.set_cat, core.per_model, core.tier) == before  # the input is not mutated


def test_abstaining_tier_only_restricts_to_the_set() -> None:
    p = ProbVector((0.5, 0.3, 0.2), PRIORITY_LABELS)
    restricted = merge_vector(p, PredictionSet(frozenset({"medium", "high"})), None, W_LLM)
    assert restricted.as_dict() == pytest.approx({"low": 0.0, "medium": 0.6, "high": 0.4})


def test_out_of_set_answer_and_bad_weight_raise() -> None:
    core = make_core({"Registration": 0.5, "IT Support": 0.4}, set_cat=["Registration", "IT Support"])
    with pytest.raises(LLMOutputOutOfSet):
        LLMMerger().merge(core, answer("Finance", None), W_LLM, CONF_CAT, CONF_PRI)
    with pytest.raises(ValueError):
        LLMMerger().merge(core, answer("Registration", None), 1.5, CONF_CAT, CONF_PRI)
