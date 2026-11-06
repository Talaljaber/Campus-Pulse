"""`BatchPredictUseCase`: labels for a CSV of requests (P1.15, ARCHITECTURE §2.5, SPEC §5.5).

Used by `predict.py` (offline, the judges' command), `evaluate.py` and `/v1/batch`. For each chunk it runs
`TriageCore.classify_many(texts, memory=False)` (the same steps as `classify`, one ensemble call)
and takes the argmax of `p_cat` and of the final `p_pri` (safety and
other floors are already inside `p_pri`). Batch never applies the decision policy and never emits
`out_of_scope` (§6.2 flag 13): every row gets one official category and priority.

- **Empty or punctuation-only text** (`InvalidInput` from the normalizer): the argmax of the frozen training
  priors, with the debug-only flag `empty_input` (LD-17).
- **`use_llm=True`**: rows whose conformal sets are not both singletons ask the oracle, which may only choose
  inside the sets; `LLMMerger` folds the answer in. Rows flagged `injection_attempt` never reach the oracle.
  `LLMUnavailable` and `LLMOutputOutOfSet` keep the tier-0 labels. Offline, `build_offline` refuses
  `use_llm` until the P3 oracle exists, so `predict.py` never calls a network.
- **`llm_priority=True`** (D-058, predict.py's LLM mode): the priority set is opened to every label before
  the oracle is asked, so the LLM may move low and medium in either direction or raise to high, but a row
  the model already puts at high stays high (safety and deadline floors are never lowered). The trained
  priority sets are almost always singletons, so without this the tie-breaker could never touch priority.
  With `lower_unflagged_high=True` (D-059) a model `high` is opened too when no floor fired (no `safety`,
  `urgency_floor:*` or `llm_cue:*` flag): such a `high` is the model's own guess, not a rule, and the LLM may
  correct it. A `high` set by a safety or deadline rule is never lowered.
- **Failed LLM calls** (D-060): a row whose oracle call fails (unavailable, timeout, out-of-set answer) keeps
  the model's labels and is retried once after the whole batch, when a burst of load has passed.
  `llm_failures` counts the rows still without an answer; predict.py prints it.
- **Never opened** for the LLM: rows flagged `injection_attempt` (nothing is asked) and rows flagged
  `queue_jump` (the priority stays the model's: the pressure phrase is still in the text the LLM would see).
- **`category_top_k=k`** (D-060, k > 0): before the oracle is asked, the category set is widened to include
  the model's k most probable categories. The calibrated sets are almost always one label for English, so
  without this the tie-breaker never sees an English category; the LLM still chooses only among labels the
  model itself ranks highly.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from campuspulse_ai.application.services.llm_merge import LLMMerger
from campuspulse_ai.application.services.triage_core import TriageCore
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.domain.entities import CoreResult, OracleContext
from campuspulse_ai.domain.errors import InvalidInput, LLMOutputOutOfSet, LLMUnavailable
from campuspulse_ai.domain.labels import PRIORITY_LABELS, Priority
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.ports import LabelOracle
from campuspulse_ai.domain.values import ClarificationBudget, NormalizedRequest, Outcome, PredictionSet, Tier

log = logging.getLogger(__name__)
EMPTY_INPUT_FLAG = "empty_input"
_ROUTE_QUESTIONS = 1  # the clarification budget the debug `route` assumes
_ROUTES: Mapping[Outcome, str] = {
    Outcome.ACCEPT: "auto", Outcome.ASK: "ask", Outcome.OUT_OF_SCOPE: "out_of_scope",
}


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

    def __init__(
        self,
        core: TriageCore,
        oracle: LabelOracle,
        config: FrozenConfig,
        *,
        llm_priority: bool = False,
        lower_unflagged_high: bool = False,
        category_top_k: int = 0,
    ) -> None:
        self.core = core
        self.oracle = oracle
        self.config = config
        self.llm_priority = llm_priority
        self.lower_unflagged_high = lower_unflagged_high
        self.category_top_k = category_top_k
        self._merger = LLMMerger()
        self._policy = DefaultDecisionPolicy(config.thresholds.tau_ood)
        self.llm_calls = 0
        self.llm_failures = 0
        self._failed = False

    def run(
        self, rows: Sequence[BatchRow], *, use_llm: bool = False, batch_size: int = 64
    ) -> list[BatchPrediction]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        out: list[BatchPrediction] = []
        retry: list[tuple[int, BatchRow, tuple[NormalizedRequest, CoreResult] | InvalidInput]] = []
        for start in range(0, len(rows), batch_size):  # one ensemble call per chunk; memory stays flat
            chunk = rows[start : start + batch_size]
            results = self.core.classify_many([r.text for r in chunk], memory=False)
            for row, result in zip(chunk, results, strict=True):
                self._failed = False
                out.append(self._one(row, result, use_llm))
                if self._failed:
                    retry.append((len(out) - 1, row, result))
        self.llm_failures = 0
        for i, row, result in retry:  # one more attempt once the burst is over
            self._failed = False
            out[i] = self._one(row, result, use_llm)
            self.llm_failures += int(self._failed)
        return out

    def _one(
        self, row: BatchRow, result: tuple[NormalizedRequest, CoreResult] | InvalidInput, use_llm: bool
    ) -> BatchPrediction:
        if isinstance(result, InvalidInput):
            p_cat, p_pri = self.core.priors
            empty = {"flags": [EMPTY_INPUT_FLAG], "tier": str(Tier.TIER0),
                     "artifact_version": self.core.artifact.name, "p_cat": p_cat.as_dict(),
                     "p_pri": p_pri.as_dict(), "set_cat": 0, "set_pri": 0, "ood_score": 0.0}
            return BatchPrediction(row.request_id, p_cat.argmax(), p_pri.argmax(), empty)
        req, core = result
        if use_llm and "injection_attempt" not in core.flags:
            if "queue_jump" in core.flags:  # the LLM may never move the priority of a pressure message
                core = dataclasses.replace(core, set_pri=PredictionSet(frozenset({core.p_pri.argmax()})))
            elif self.llm_priority:
                core = self._open_priority(core, self.lower_unflagged_high)
            if self.category_top_k > 0:
                core = self._open_category(core, self.category_top_k)
            if self._needs_llm(core):
                core = self._ask(req, core)
        debug = {
            "flags": sorted(core.flags),
            "tier": str(core.tier),
            "artifact_version": core.artifact.name,
            "p_cat": core.p_cat.as_dict(),
            "p_pri": core.p_pri.as_dict(),
            # 0 when the conformal set was empty (the labels are the argmax singleton, P7.1)
            "set_cat": 0 if "empty_set_cat" in core.flags else core.set_cat.size,
            "set_pri": 0 if "empty_set_pri" in core.flags else core.set_pri.size,
            "ood_score": core.ood_score,
            "lang": str(req.lang),
            "route": self._route(core),
        }
        cue_floor = self.core.cue_floor
        if cue_floor is not None:  # the LLM's cue values: debug output only, never in an API response
            debug["llm_cues"] = cue_floor.cues(req.model_text)
        return BatchPrediction(row.request_id, core.p_cat.argmax(), core.p_pri.argmax(), debug)

    def _route(self, core: CoreResult) -> str:
        """What the online decision policy would do with this row: auto, ask, review or out_of_scope.

        Debug-only (batch itself never applies the policy and labels every row, §6.2 flag 13)."""
        outcome = self._policy.decide(core, ClarificationBudget(max_questions=_ROUTE_QUESTIONS), False)
        return _ROUTES.get(outcome, "review")

    @staticmethod
    def _needs_llm(core: CoreResult) -> bool:
        if "injection_attempt" in core.flags:
            return False
        return core.set_cat.size >= 2 or core.set_pri.size >= 2

    @staticmethod
    def _open_priority(core: CoreResult, lower_unflagged_high: bool = False) -> CoreResult:
        """Every priority label is allowed, except that a model `high` is kept (raise-only at the top);
        with `lower_unflagged_high`, only a `high` that a safety or deadline floor set is kept."""
        if core.p_pri.argmax() == str(Priority.HIGH) and (not lower_unflagged_high or _floored(core)):
            return core
        return dataclasses.replace(core, set_pri=PredictionSet(frozenset(PRIORITY_LABELS)))

    @staticmethod
    def _open_category(core: CoreResult, k: int) -> CoreResult:
        """The category set plus the model's `k` most probable categories (D-060)."""
        p = core.p_cat
        ranked = sorted(p.labels, key=lambda lab: p.values[p.labels.index(lab)], reverse=True)
        widened = frozenset(core.set_cat.labels) | frozenset(ranked[:k])
        if widened == core.set_cat.labels:
            return core
        return dataclasses.replace(core, set_cat=PredictionSet(widened))

    def _ask(self, req: NormalizedRequest, core: CoreResult) -> CoreResult:
        version = self.config.llm.prompt_version
        context = OracleContext(lang=req.lang, neighbors=core.neighbors, prompt_version=version)
        try:
            answer = self.oracle.choose(req, core.set_cat, core.set_pri, context)
            self.llm_calls += 1
            return self._merger.merge(core, answer, self.config.llm.w_llm, self.core.conformal_cat,
                                      self.core.conformal_pri)
        except (LLMUnavailable, LLMOutputOutOfSet) as exc:
            self._failed = True
            log.warning("LLM tie-breaker gave no usable answer (%s: %s); keeping the model's labels",
                        type(exc).__name__, str(exc)[:160])
            return core


FLOOR_FLAG_PREFIXES = ("urgency_floor:", "llm_cue:")


def _floored(core: CoreResult) -> bool:
    """A safety, distress, urgency or LLM-cue floor fired on this row (its `high` comes from a rule)."""
    if core.safety or core.floors_applied or {"safety", "distress"} & core.flags:
        return True
    return any(f.startswith(FLOOR_FLAG_PREFIXES) for f in core.flags)
