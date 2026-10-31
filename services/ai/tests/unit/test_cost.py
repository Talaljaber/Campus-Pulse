"""P3.3: LLM cost estimation and the in-memory cost logger."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fixtures.backend_fakes import FrozenClock, fake_call

from campuspulse_ai.adapters.llm.cost import PRICES_PER_MTOK, InMemoryCostLogger, estimate_cost
from campuspulse_ai.domain.ports import CostLogger
from campuspulse_ai.domain.values import Money


def test_estimate_from_the_pinned_price_table() -> None:
    # Appendix B: tier 1 at $0.10 / $0.50 per 1M tokens; ~400 in / 40 out per escalation.
    assert estimate_cost("anthropic/claude-haiku-5.5", 400, 40) == pytest.approx(0.00006)


def test_unknown_model_is_priced_at_the_highest_rate() -> None:
    top_in = max(p[0] for p in PRICES_PER_MTOK.values())
    top_out = max(p[1] for p in PRICES_PER_MTOK.values())
    assert estimate_cost("some/new-model", 1_000_000, 1_000_000) == pytest.approx(top_in + top_out)


def test_logger_totals_count_cached_calls() -> None:
    logger = InMemoryCostLogger()
    assert isinstance(logger, CostLogger)
    assert logger.totals() == {"usd": 0.0, "calls": 0.0, "cached": 0.0}
    paid = fake_call()
    paid.cost = Money(0.25)
    logger.log(paid)
    logger.log(fake_call(cached=True))
    assert logger.totals() == {"usd": pytest.approx(0.25), "calls": 2.0, "cached": 1.0}
    assert len(logger.calls) == 2


def test_totals_are_per_day_with_a_clock() -> None:
    clock = FrozenClock()
    logger = InMemoryCostLogger(clock)
    paid = fake_call()
    paid.cost = Money(4.0)
    logger.log(paid)
    assert logger.totals()["usd"] == pytest.approx(4.0)
    clock.at = clock.at + timedelta(days=1)  # a new Amman day: the daily budget starts again
    assert logger.totals() == {"usd": 0.0, "calls": 0.0, "cached": 0.0}
    assert len(logger.calls) == 1
