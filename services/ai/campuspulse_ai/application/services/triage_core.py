"""`TriageCore`: the only path that produces labels (P1.15, ARCHITECTURE §1.4, §2.0).

Pure application service: every collaborator is a port, built by a composition root (`build_offline` for
`predict.py`/`train.py`/`evaluate.py`, `build_online` for the API). The same class runs offline and online;
only the `MemoryStore` differs (§3.11).

`classify(raw)` steps (§2.0):
 1. `Normalizer.normalize` → `NormalizedRequest` (raises `InvalidInput` on empty text).
 2. Guards, in the given order (Gibberish, Injection, Safety):
      gibberish → flag `gibberish` (the core still labels; the online policy decides);
      injection → `model_text := stripped_text`, flag `injection_attempt` (the LLM tiers are disabled for it);
      distress  → flag `distress` (online stops before labelling; batch keeps the label);
      danger    → `safety = True`, flag `safety`.
    Later guards see the stripped text.
 3. `Ensemble.predict([model_text], memory)` → `p_cat`, `p_pri_model`, `per_model`, `ood_score`, neighbours.
    If the injection guard left **no text at all** (the whole request was an injection), no model sees the
    request: `p_cat`/`p_pri` are the frozen training priors and `ood_score` is 0.0, so nothing in the
    injected text can steer a label, and the wide conformal sets mark the result as unsure.
 4. `EvidenceExtractor.extract` on the (stripped) request; never `stated_urgency`.
 5. `PriorityHead.predict(p_pri_model, evidence, constraints)`.
 6. `PriorityFinalizer.apply` → `p_pri` (safety → high; a priority answer → one-hot), `floors_applied`.
 7. Conformal sets on `p_cat` and the final `p_pri` (empty → argmax + flag `empty_set`). A category answer
    makes `p_cat` one-hot on it and `S_cat = {answer}`; a priority floor makes `S_pri = {floor label}`.
 8. `CoreResult(..., tier=TIER0)`. The core always returns both probability vectors.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence

from campuspulse_ai.application.services.priority_finalizer import PriorityFinalizer, onehot
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import Clock as ClockPort
from campuspulse_ai.domain.ports import (
    ConformalPredictor,
    Ensemble,
    EvidenceExtractor,
    Guard,
    MemoryStore,
    Normalizer,
    PriorityHead,
)
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    ClarificationConstraint,
    GuardVerdict,
    Location,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    Tier,
)

MS_PER_S = 1000
# Which verdict CoreResult.guard reports when several guards fire (the one the caller must act on first).
_VERDICT_RANK: Mapping[str, int] = {"injection": 0, "distress": 1, "danger": 2, "gibberish": 3, "none": 4}
_FLAG_FOR: Mapping[str, str] = {"gibberish": "gibberish", "injection": "injection_attempt",
                                "distress": "distress", "danger": "safety"}


def _vector(dist: Mapping[str, float], labels: tuple[str, ...]) -> ProbVector:
    total = sum(dist[lab] for lab in labels)
    return ProbVector(tuple(dist[lab] / total for lab in labels), labels)


class TriageCore:
    """Normalize → guard → ensemble → evidence → head → floors → conformal (module docstring).

    Raises:
        InvalidInput: from the normalizer (empty or punctuation-only text). Guards never raise; the other
            collaborators raise only on programming or artifact errors.
    """

    def __init__(
        self,
        normalizer: Normalizer,
        guards: Sequence[Guard],
        ensemble: Ensemble,
        evidence: EvidenceExtractor,
        head: PriorityHead,
        finalizer: PriorityFinalizer,
        conformal_cat: ConformalPredictor,
        conformal_pri: ConformalPredictor,
        memory: MemoryStore,
        clock: ClockPort,
        config: FrozenConfig,
        artifact: ArtifactVersion,
    ) -> None:
        self.normalizer = normalizer
        self.guards: tuple[Guard, ...] = tuple(guards)
        self.ensemble = ensemble
        self.evidence = evidence
        self.head = head
        self.finalizer = finalizer
        self.conformal_cat = conformal_cat
        self.conformal_pri = conformal_pri
        self.memory = memory
        self.clock = clock
        self.config = config
        self.artifact = artifact
        self._prior_cat = _vector(config.priors.category, CATEGORY_LABELS)
        self._prior_pri = _vector(config.priors.priority, PRIORITY_LABELS)

    @property
    def priors(self) -> tuple[ProbVector, ProbVector]:
        """The frozen training-pool label frequencies (category, priority)."""
        return self._prior_cat, self._prior_pri

    def classify(
        self,
        raw: str,
        picked_location: Location | None = None,
        constraints: Sequence[ClarificationConstraint] = (),
        memory: bool = True,
    ) -> tuple[NormalizedRequest, CoreResult]:
        """Classify one request (module docstring). `memory=False` ignores the live memory store."""
        started = time.perf_counter()
        req = self.normalizer.normalize(raw, picked_location)
        flags: set[str] = set()
        safety = False
        verdicts: list[GuardVerdict] = []
        injection = GuardVerdict(kind="none")
        for guard in self.guards:
            verdict = guard.inspect(req)
            verdicts.append(verdict)
            if verdict.kind in _FLAG_FOR:
                flags.add(_FLAG_FOR[verdict.kind])
            if verdict.kind == "injection":
                injection = verdict
                req = dataclasses.replace(req, model_text=verdict.stripped_text)
            elif verdict.kind == "danger":
                safety = True
        if req.truncated:
            flags.add("truncated")

        evidence = self.evidence.extract(req)
        if req.model_text:
            out = self.ensemble.predict([req.model_text], self.memory if memory else None)[0]
            p_cat, per_model = out.p_cat, dict(out.per_model)
            ood, neighbors, embedding = out.ood_score, out.neighbors, out.embedding
            p_pri_head = self.head.predict(out.p_pri_model, evidence, constraints)
        else:  # the whole request was an injection: no model sees anything (module docstring, step 3)
            p_cat, per_model, ood, neighbors, embedding = self._prior_cat, {}, 0.0, (), ()
            p_pri_head = self._prior_pri
        p_pri, floors = self.finalizer.apply(p_pri_head, safety, injection, constraints)

        answered_cat = [c.value for c in constraints if c.kind == "category"]
        if answered_cat:
            p_cat = onehot(p_cat, answered_cat[-1])
        set_cat, cat_empty = self._set(self.conformal_cat, p_cat)
        set_pri, pri_empty = self._set(self.conformal_pri, p_pri)
        if answered_cat:
            set_cat = PredictionSet(frozenset({answered_cat[-1]}))
        if floors:
            set_pri = PredictionSet(frozenset({p_pri.argmax()}))
        if cat_empty or pri_empty:
            flags.add("empty_set")

        top = min(verdicts, key=lambda v: _VERDICT_RANK[v.kind], default=GuardVerdict(kind="none"))
        latency_ms = int((time.perf_counter() - started) * MS_PER_S)
        return req, CoreResult(
            p_cat=p_cat,
            p_pri=p_pri,
            per_model=per_model,
            flags=frozenset(flags),
            set_cat=set_cat,
            set_pri=set_pri,
            ood_score=float(ood),
            neighbors=tuple(neighbors),
            evidence=evidence,
            guard=top,
            safety=safety,
            floors_applied=floors,
            tier=Tier.TIER0,
            latency_ms=latency_ms,
            artifact=self.artifact,
            embedding=tuple(embedding),
        )

    @staticmethod
    def _set(conformal: ConformalPredictor, p: ProbVector) -> tuple[PredictionSet, bool]:
        """(set, was_empty); uses the thread-safe form when the predictor offers it (LACConformal)."""
        with_flag = getattr(conformal, "predict_set_with_flag", None)
        if callable(with_flag):
            result = with_flag(p)
            return result[0], bool(result[1])
        s = conformal.predict_set(p)
        return s, bool(getattr(conformal, "last_was_empty", False))
