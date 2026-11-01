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
 6. `PriorityFinalizer.apply` → `p_pri` (safety → high; a priority answer → one-hot; an urgency-floor
    family on the stripped text → high, flag `urgency_floor:<family>`), `floors_applied`.
 7. Conformal sets on `p_cat` and the final `p_pri` (empty → argmax + flags `empty_set`,
    `empty_set_cat` / `empty_set_pri`, P7.1). A category answer
    makes `p_cat` one-hot on it and `S_cat = {answer}`; a priority floor makes `S_pri = {floor label}`.
 8. `CoreResult(..., tier=TIER0)`. The core always returns both probability vectors.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from campuspulse_ai.application.services.priority_finalizer import (
    FLOOR_LLM_CUE,
    FLOOR_URGENCY,
    PriorityFinalizer,
    onehot,
)
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import Clock as ClockPort
from campuspulse_ai.domain.ports import (
    ConformalPredictor,
    CueFloor,
    Ensemble,
    EvidenceExtractor,
    Guard,
    MemoryStore,
    Normalizer,
    PriorityHead,
    UrgencyFloor,
)
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    ClarificationConstraint,
    EnsembleOutput,
    GuardVerdict,
    Location,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    Tier,
)

MS_PER_S = 1000
# Which verdict CoreResult.guard reports when several guards fire (the one the caller must act on first).
_VERDICT_RANK: Mapping[str, int] = {
    "injection": 0, "distress": 1, "danger": 2, "gibberish": 3, "queue_jump": 4, "vague": 5, "none": 6,
}
_FLAG_FOR: Mapping[str, str] = {"gibberish": "gibberish", "injection": "injection_attempt",
                                "distress": "distress", "danger": "safety", "queue_jump": "queue_jump",
                                "vague": "too_vague"}
FLAG_LLM_CUE_PREFIX = "llm_cue:"


@dataclass(frozen=True)
class _Prepared:
    """A request after steps 1–2 (normalized, guarded)."""

    req: NormalizedRequest
    flags: frozenset[str] | set[str]
    safety: bool
    verdicts: tuple[GuardVerdict, ...]
    injection: GuardVerdict
    # P7.9: the request without its queue-jump pressure phrases. Only the priority path (model, evidence,
    # floors, LLM cues) reads it; the category path keeps `req.model_text`, so pressure never moves a
    # category label either way. None when no pressure phrase was found.
    priority_text: str | None = None

    @property
    def pri_text(self) -> str:
        return self.req.model_text if self.priority_text is None else self.priority_text


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
        urgency_floor: UrgencyFloor | None = None,
        cue_floor: CueFloor | None = None,
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
        self.urgency_floor = urgency_floor
        self.cue_floor = cue_floor
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
        prepared = self._prepare(raw, picked_location)
        out = self._ensemble([prepared], memory)[0]
        return self._finish(prepared, out, constraints, started)

    def classify_many(
        self, raws: Sequence[str], memory: bool = False
    ) -> list[tuple[NormalizedRequest, CoreResult] | InvalidInput]:
        """Classify a batch: one ensemble call for all rows (batch speed), same results as `classify`.

        Each entry is the `classify` result, or the `InvalidInput` that row raised (empty text), so one bad
        row never fails the batch. No constraints, no picked location (batch mode, §2.5).
        """
        started = time.perf_counter()
        prepared: list[_Prepared | InvalidInput] = []
        for raw in raws:
            try:
                prepared.append(self._prepare(raw, None))
            except InvalidInput as exc:
                prepared.append(exc)
        valid = [p for p in prepared if not isinstance(p, InvalidInput)]
        outs = iter(self._ensemble(valid, memory))
        return [p if isinstance(p, InvalidInput) else self._finish(p, next(outs), (), started)
                for p in prepared]

    def _prepare(self, raw: str, picked_location: Location | None) -> _Prepared:
        """Steps 1–2: normalize and run the guards."""
        req = self.normalizer.normalize(raw, picked_location)
        flags: set[str] = set()
        safety = False
        verdicts: list[GuardVerdict] = []
        injection = GuardVerdict(kind="none")
        priority_text: str | None = None
        for guard in self.guards:
            verdict = guard.inspect(req)
            verdicts.append(verdict)
            if verdict.kind in _FLAG_FOR:
                flags.add(_FLAG_FOR[verdict.kind])
            if verdict.kind == "injection":
                injection = verdict
                req = dataclasses.replace(req, model_text=verdict.stripped_text)
            elif verdict.kind == "queue_jump":
                priority_text = verdict.stripped_text
            elif verdict.kind == "danger":
                safety = True
        if req.truncated:
            flags.add("truncated")
        return _Prepared(req, flags, safety, tuple(verdicts), injection, priority_text)

    def _ensemble(self, prepared: Sequence[_Prepared], memory: bool) -> list[EnsembleOutput | None]:
        """Step 3 for every row with text, one call per distinct text; None for a row with no text left.

        A text's ensemble output does not depend on the other texts in the call (the encoder runs one text at
        a time and every member scores rows independently), so scoring each distinct `model_text` once is
        exact: wrapper variants of one request share a `model_text` and its result.
        """
        texts = [p.req.model_text for p in prepared] + [p.priority_text or "" for p in prepared]
        distinct = list(dict.fromkeys(t for t in texts if t))
        outs = self.ensemble.predict(distinct, self.memory if memory else None) if distinct else []
        by_text = dict(zip(distinct, outs, strict=True))
        result: list[EnsembleOutput | None] = []
        for p in prepared:
            out = by_text[p.req.model_text] if p.req.model_text else None
            if out is not None and p.priority_text is not None:
                # queue-jump pressure: the priority model reads the text without the pressure phrase
                pri = by_text[p.priority_text].p_pri_model if p.priority_text else self._prior_pri
                out = dataclasses.replace(out, p_pri_model=pri)
            result.append(out)
        return result

    def _finish(
        self,
        prepared: _Prepared,
        out: EnsembleOutput | None,
        constraints: Sequence[ClarificationConstraint],
        started: float,
    ) -> tuple[NormalizedRequest, CoreResult]:
        """Steps 4–8."""
        req, flags = prepared.req, set(prepared.flags)
        # the priority path (evidence, floors, LLM cues) reads the text without queue-jump pressure
        pri_req = req if prepared.priority_text is None else dataclasses.replace(
            req, model_text=prepared.priority_text
        )
        evidence = self.evidence.extract(pri_req)
        if out is not None:
            p_cat, per_model = out.p_cat, dict(out.per_model)
            ood, neighbors, embedding = out.ood_score, out.neighbors, out.embedding
            p_pri_head = self.head.predict(out.p_pri_model, evidence, constraints)
        else:  # the whole request was an injection: no model sees anything (module docstring, step 3)
            p_cat, per_model, ood, neighbors, embedding = self._prior_cat, {}, 0.0, (), ()
            p_pri_head = self._prior_pri
        floor_hits = self.urgency_floor.hits(pri_req) if self.urgency_floor is not None else ()
        cue_hits: tuple[str, ...] = ()
        if self.cue_floor is not None and out is not None:
            cue_hits = self.cue_floor.hits(prepared.pri_text)
        p_pri, floors = self.finalizer.apply(
            p_pri_head, prepared.safety, prepared.injection, constraints, floor_hits, cue_hits
        )
        if FLOOR_URGENCY in floors:
            flags.update(f"urgency_floor:{family}" for family in floor_hits)
        if FLOOR_LLM_CUE in floors:
            flags.update(f"{FLAG_LLM_CUE_PREFIX}{name}" for name in cue_hits)

        answered_cat = [c.value for c in constraints if c.kind == "category"]
        if answered_cat:
            p_cat = onehot(p_cat, answered_cat[-1])
        set_cat, cat_empty = self._set(self.conformal_cat, p_cat, str(req.lang))
        set_pri, pri_empty = self._set(self.conformal_pri, p_pri, str(req.lang))
        if answered_cat:
            set_cat = PredictionSet(frozenset({answered_cat[-1]}))
        if floors:
            set_pri = PredictionSet(frozenset({p_pri.argmax()}))
        # A set that a floor or an answer replaced is a real singleton, not an empty one (P7.1).
        cat_empty = cat_empty and not answered_cat
        pri_empty = pri_empty and not floors
        if cat_empty:
            flags.add("empty_set_cat")
        if pri_empty:
            flags.add("empty_set_pri")
        if cat_empty or pri_empty:
            flags.add("empty_set")

        top = min(prepared.verdicts, key=lambda v: _VERDICT_RANK[v.kind], default=GuardVerdict(kind="none"))
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
            safety=prepared.safety,
            floors_applied=floors,
            tier=Tier.TIER0,
            latency_ms=latency_ms,
            artifact=self.artifact,
            embedding=tuple(embedding),
        )

    @staticmethod
    def _set(conformal: ConformalPredictor, p: ProbVector, lang: str) -> tuple[PredictionSet, bool]:
        """(set, was_empty); the per-language form when the predictor is a MondrianByLang (P2.10), else the
        thread-safe form when the predictor offers it (LACConformal)."""
        by_lang = getattr(conformal, "predict_set_with_flag_for", None)
        if callable(by_lang):
            result = by_lang(p, lang)
            return result[0], bool(result[1])
        with_flag = getattr(conformal, "predict_set_with_flag", None)
        if callable(with_flag):
            result = with_flag(p)
            return result[0], bool(result[1])
        s = conformal.predict_set(p)
        return s, bool(getattr(conformal, "last_was_empty", False))
