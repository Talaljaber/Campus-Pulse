"""`LLMMerger`: folds an LLM tier's answer into the core result (ARCHITECTURE §3.9, P3.3).

Pure application service (domain imports only). The LLM acts as one more ensemble member that may
only vote inside the current conformal sets (UD-5).
"""

from __future__ import annotations

import dataclasses
import math

from campuspulse_ai.domain.entities import CoreResult, OracleAnswer
from campuspulse_ai.domain.errors import LLMOutputOutOfSet
from campuspulse_ai.domain.ports import ConformalPredictor
from campuspulse_ai.domain.values import PredictionSet, ProbVector


def merge_vector(p: ProbVector, allowed: PredictionSet, label: str | None, w_llm: float) -> ProbVector:
    """p' = (1 − w)·p_S + w·onehot(label), where p_S is p restricted to the allowed set S and renormalised.

    With no label (the tier abstained) p' = p_S. If S holds no probability mass, p_S is uniform over S.
    The result has zero mass outside S, so its argmax is always inside S.
    """
    inside = [lab in allowed.labels for lab in p.labels]
    if not any(inside):
        raise ValueError(f"the allowed set {sorted(allowed.labels)} shares no label with the vector")
    mass = math.fsum(v for v, keep in zip(p.values, inside, strict=True) if keep)
    if mass > 0.0:
        restricted = [v / mass if keep else 0.0 for v, keep in zip(p.values, inside, strict=True)]
    else:
        n = sum(inside)
        restricted = [1.0 / n if keep else 0.0 for keep in inside]
    if label is None:
        mixed = restricted
    else:
        mixed = [
            (1.0 - w_llm) * v + (w_llm if lab == label else 0.0)
            for lab, v in zip(p.labels, restricted, strict=True)
        ]
    total = math.fsum(mixed)
    return ProbVector(tuple(v / total for v in mixed), p.labels)


def _onehot(p: ProbVector, label: str) -> ProbVector:
    return ProbVector(tuple(1.0 if lab == label else 0.0 for lab in p.labels), p.labels)


def _recompute(
    conformal: ConformalPredictor, p: ProbVector, allowed: PredictionSet
) -> tuple[PredictionSet, bool]:
    """The conformal set of the merged vector, kept inside the allowed set; (set, was_empty)."""
    s = conformal.predict_set(p).labels & allowed.labels
    if s:
        return PredictionSet(s), False
    return PredictionSet(frozenset({p.argmax()})), True


class LLMMerger:
    """Merges an `OracleAnswer` into a `CoreResult` and recomputes the prediction sets.

    `merge(core, answer, w_llm, conf_cat, conf_pri)` returns a new `CoreResult` (the input is not
    mutated) with:
      - `p_cat`/`p_pri` = `merge_vector(...)` over the current sets, so the merged argmax is always in the
        allowed set;
      - `set_cat`/`set_pri` recomputed with the same conformal predictors (same quantile) and intersected
        with the previous sets (a set never grows); an empty result becomes the argmax singleton and adds
        flag `empty_set`. Coverage is guaranteed for tier 0 only; after a merge it is a heuristic;
      - `per_model["<tier>.category"]` / `["<tier>.priority"]` = the LLM's one-hot vote (LD-13 keys);
      - `tier` = `answer.call.tier`.

    Raises LLMOutputOutOfSet if the answer names a label outside the current set (an oracle should
    already have refused it) and ValueError if `w_llm` is not in [0, 1].
    """

    def merge(
        self,
        core: CoreResult,
        answer: OracleAnswer,
        w_llm: float,
        conf_cat: ConformalPredictor,
        conf_pri: ConformalPredictor,
    ) -> CoreResult:
        if not 0.0 <= w_llm <= 1.0:
            raise ValueError(f"w_llm must be in [0, 1], got {w_llm!r}")
        cat = str(answer.category) if answer.category is not None else None
        pri = str(answer.priority) if answer.priority is not None else None
        if cat is not None and cat not in core.set_cat.labels:
            raise LLMOutputOutOfSet(f"category {cat!r} is outside {sorted(core.set_cat.labels)}")
        if pri is not None and pri not in core.set_pri.labels:
            raise LLMOutputOutOfSet(f"priority {pri!r} is outside {sorted(core.set_pri.labels)}")

        p_cat = merge_vector(core.p_cat, core.set_cat, cat, w_llm)
        p_pri = merge_vector(core.p_pri, core.set_pri, pri, w_llm)
        set_cat, cat_empty = _recompute(conf_cat, p_cat, core.set_cat)
        set_pri, pri_empty = _recompute(conf_pri, p_pri, core.set_pri)

        member = str(answer.call.tier)
        per_model = dict(core.per_model)
        for target, label, p in (("category", cat, core.p_cat), ("priority", pri, core.p_pri)):
            if label is not None:
                per_model[f"{member}.{target}"] = _onehot(p, label)
        flags = core.flags | ({"empty_set"} if cat_empty or pri_empty else set())
        return dataclasses.replace(
            core,
            p_cat=p_cat,
            p_pri=p_pri,
            set_cat=set_cat,
            set_pri=set_pri,
            per_model=per_model,
            flags=frozenset(flags),
            tier=answer.call.tier,
        )
