"""`NullOracle`: the LLM tier when the LLM is off (offline default, `ENABLE_LLM=false`, no key)."""

from __future__ import annotations

from campuspulse_ai.domain.entities import OracleAnswer, OracleContext
from campuspulse_ai.domain.errors import LLMUnavailable
from campuspulse_ai.domain.values import NormalizedRequest, PredictionSet, Tier

NULL_MODEL_ID = "none"


class NullOracle:
    """Implements `LabelOracle`; `choose` always raises LLMUnavailable, so callers fall back to tier 0.

    No network, no imports beyond the domain: safe in the offline container (`predict.py`).
    """

    def __init__(self, tier: Tier = Tier.TIER1) -> None:
        self.tier = tier
        self.model_id = NULL_MODEL_ID

    def choose(
        self,
        req: NormalizedRequest,
        allowed_cat: PredictionSet,
        allowed_pri: PredictionSet,
        context: OracleContext,
    ) -> OracleAnswer:
        raise LLMUnavailable("the LLM tier is disabled (NullOracle)")
