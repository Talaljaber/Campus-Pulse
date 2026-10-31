"""`BatchPredictUseCase`: labels for a CSV of requests (P1.15, ARCHITECTURE §2.5, SPEC §5.5).

Used by `predict.py` (offline, the judges' command), `evaluate.py` and `/v1/batch`. For each row it runs
`TriageCore.classify(text, memory=False)` and takes the argmax of `p_cat` and of the final `p_pri` (safety and
other floors are already inside `p_pri`). Batch never applies the decision policy and never emits
`out_of_scope` (§6.2 flag 13): every row gets one official category and priority.

- **Empty or punctuation-only text** (`InvalidInput` from the normalizer): the argmax of the frozen training
  priors, with the debug-only flag `empty_input` (LD-17).
- **`use_llm=True`**: rows whose conformal sets are not both singletons ask the oracle, which may only choose
  inside the sets; `LLMMerger` folds the answer in. Rows flagged `injection_attempt` never reach the oracle.
  `LLMUnavailable` and `LLMOutputOutOfSet` keep the tier-0 labels. Offline, `build_offline` refuses
  `use_llm` until the P3 oracle exists, so `predict.py` never calls a network.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from campuspulse_ai.application.services.llm_merge import LLMMerger
from campuspulse_ai.application.services.triage_core import TriageCore
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.domain.entities import CoreResult, OracleContext
from campuspulse_ai.domain.errors import InvalidInput, LLMOutputOutOfSet, LLMUnavailable
from campuspulse_ai.domain.ports import LabelOracle
from campuspulse_ai.domain.values import NormalizedRequest, Tier

EMPTY_INPUT_FLAG = "empty_input"


@dataclass(frozen=True)
class BatchRow:
    request_id: str
    text: str


@dataclass(frozen=True)
class BatchPrediction:
    """One output row; `debug` holds the `--debug` columns (probabilities, sets, tier, flags, OOD...)."""

    request_id: str
    category: str
    priority: str
    debug: Mapping[str, object] = field(default_factory=dict)


class BatchPredictUseCase:
    """`run(rows, use_llm=False, batch_size=64)` → one `BatchPrediction` per row, in input order.

    Raises:
        ValueError: `batch_size` < 1. Other errors from the core (artifact problems) propagate.
    """

    def __init__(self, core: TriageCore, oracle: LabelOracle, config: FrozenConfig) -> None:
        self.core = core
        self.oracle = oracle
        self.config = config
        self._merger = LLMMerger()
        self.llm_calls = 0

    def run(
        self, rows: Sequence[BatchRow], *, use_llm: bool = False, batch_size: int = 64
    ) -> list[BatchPrediction]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        out: list[BatchPrediction] = []
        for start in range(0, len(rows), batch_size):  # chunks keep memory flat on very large inputs
            out.extend(self._one(row, use_llm) for row in rows[start : start + batch_size])
        return out

    def _one(self, row: BatchRow, use_llm: bool) -> BatchPrediction:
        try:
            req, core = self.core.classify(row.text, memory=False)
        except InvalidInput:
            p_cat, p_pri = self.core.priors
            debug = {"flags": [EMPTY_INPUT_FLAG], "tier": str(Tier.TIER0),
                     "artifact_version": self.core.artifact.name, "p_cat": p_cat.as_dict(),
                     "p_pri": p_pri.as_dict(), "set_cat": 0, "set_pri": 0, "ood_score": 0.0}
            return BatchPrediction(row.request_id, p_cat.argmax(), p_pri.argmax(), debug)
        if use_llm and self._needs_llm(core):
            core = self._ask(req, core)
        debug = {
            "flags": sorted(core.flags),
            "tier": str(core.tier),
            "artifact_version": core.artifact.name,
            "p_cat": core.p_cat.as_dict(),
            "p_pri": core.p_pri.as_dict(),
            "set_cat": core.set_cat.size,
            "set_pri": core.set_pri.size,
            "ood_score": core.ood_score,
            "lang": str(req.lang),
        }
        return BatchPrediction(row.request_id, core.p_cat.argmax(), core.p_pri.argmax(), debug)

    @staticmethod
    def _needs_llm(core: CoreResult) -> bool:
        if "injection_attempt" in core.flags:
            return False
        return core.set_cat.size >= 2 or core.set_pri.size >= 2

    def _ask(self, req: NormalizedRequest, core: CoreResult) -> CoreResult:
        version = self.config.llm.prompt_version
        context = OracleContext(lang=req.lang, neighbors=core.neighbors, prompt_version=version)
        try:
            answer = self.oracle.choose(req, core.set_cat, core.set_pri, context)
            self.llm_calls += 1
            return self._merger.merge(core, answer, self.config.llm.w_llm, self.core.conformal_cat,
                                      self.core.conformal_pri)
        except (LLMUnavailable, LLMOutputOutOfSet):
            return core
