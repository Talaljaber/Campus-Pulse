"""Backend-stream test fakes (P3.2, P3.3, P3.3a).

Kept apart from `tests/fixtures/fakes.py` (created by the ML stream in P1.4) so the two streams do not
edit the same file; P3.8 re-exports these from `fakes.py` for `build_test()`.

- `make_core(...)`: a `CoreResult` with chosen probabilities, sets and flags.
- `FakeLAC`: a tiny LAC-style `ConformalPredictor` (set = labels with p ≥ 1 − q) until the ML
  stream's `LACConformal` (P1.14) exists.
- `FrozenClock`: a `Clock` fixed at one Asia/Amman instant.
- `ScriptedOracle`: a `LabelOracle` that replays scripted answers or errors and records its calls.
- `make_request(...)`: a `NormalizedRequest` without running the normalizer.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from campuspulse_ai.domain.entities import CoreResult, LLMCall, OracleAnswer, OracleContext
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    EvidenceVector,
    GuardVerdict,
    Lang,
    Location,
    Money,
    NormalizedRequest,
    PredictionSet,
    ProbabilityTarget,
    ProbVector,
    Tier,
)

AMMAN = timezone(timedelta(hours=3), "Asia/Amman")


def prob_vector(labels: tuple[str, ...], given: Mapping[str, float] | None) -> ProbVector:
    """A ProbVector over `labels`; labels missing from `given` share the remaining mass equally."""
    given = dict(given or {})
    rest = [lab for lab in labels if lab not in given]
    remaining = max(0.0, 1.0 - math.fsum(given.values()))
    values = [given.get(lab, remaining / len(rest) if rest else 0.0) for lab in labels]
    total = math.fsum(values)
    return ProbVector(tuple(v / total for v in values), labels)


def make_core(
    p_cat: Mapping[str, float] | None = None,
    p_pri: Mapping[str, float] | None = None,
    *,
    set_cat: Sequence[str] | None = None,
    set_pri: Sequence[str] | None = None,
    flags: frozenset[str] = frozenset(),
    safety: bool = False,
    tier: Tier = Tier.TIER0,
) -> CoreResult:
    """A CoreResult; sets default to the argmax singleton of each vector."""
    pc = prob_vector(CATEGORY_LABELS, p_cat)
    pp = prob_vector(PRIORITY_LABELS, p_pri)
    return CoreResult(
        p_cat=pc,
        p_pri=pp,
        per_model={},
        flags=flags,
        set_cat=PredictionSet(frozenset(set_cat or [pc.argmax()])),
        set_pri=PredictionSet(frozenset(set_pri or [pp.argmax()])),
        ood_score=0.9,
        neighbors=(),
        evidence=EvidenceVector(flags={}),
        guard=GuardVerdict(kind="injection" if "injection_attempt" in flags else "none"),
        safety=safety,
        floors_applied=(),
        tier=tier,
        latency_ms=0,
        artifact=ArtifactVersion(name="v1", sha256="0" * 64),
    )


def make_request(
    text: str,
    *,
    lang: Lang = Lang.EN,
    is_arabizi: bool = False,
    model_text: str | None = None,
    location: Location | None = None,
) -> NormalizedRequest:
    """A NormalizedRequest whose core/text_norm/model_text are `text` (or `model_text`)."""
    return NormalizedRequest(
        raw=text,
        core=text,
        text_norm=text,
        model_text=model_text or text,
        lang=lang,
        is_arabizi=is_arabizi,
        stated_urgency=False,
        truncated=False,
        location=location,
    )


@dataclass
class FakeLAC:
    """LAC-style conformal predictor: S = {l : p(l) ≥ 1 − q}; an empty set becomes the argmax singleton."""

    target: ProbabilityTarget
    q: float
    alpha: float = 0.1

    def predict_set(self, p: ProbVector) -> PredictionSet:
        chosen = frozenset(lab for lab, v in zip(p.labels, p.values, strict=True) if v >= 1.0 - self.q)
        return PredictionSet(chosen or frozenset({p.argmax()}))

    def calibrate(self, probs: Sequence[ProbVector], y: Sequence[str], groups: Sequence[str]) -> None:
        raise NotImplementedError

    def save(self, dir: Path) -> None:
        raise NotImplementedError

    @classmethod
    def load(cls, dir: Path) -> FakeLAC:
        raise NotImplementedError


@dataclass
class FrozenClock:
    """A Clock that always returns `at` (tz-aware, Asia/Amman by default)."""

    at: datetime = field(default_factory=lambda: datetime(2026, 11, 5, 9, 5, tzinfo=AMMAN))

    def now(self) -> datetime:
        return self.at


def fake_call(tier: Tier = Tier.TIER1, model: str = "scripted/model", *, cached: bool = False) -> LLMCall:
    return LLMCall(
        id=str(uuid.uuid4()),
        request_id=None,
        tier=tier,
        model=model,
        prompt_hash="0" * 64,
        tokens_in=0,
        tokens_out=0,
        cost=Money(0.0),
        latency_ms=0,
        cached=cached,
    )


ScriptStep = tuple[Category | None, Priority | None] | Exception


@dataclass
class ScriptedOracle:
    """A LabelOracle that replays `script` in order (a label pair or an exception to raise).

    Every call is recorded in `calls` as (request, allowed_cat, allowed_pri). When the script runs out,
    the last step repeats.
    """

    script: Sequence[ScriptStep]
    tier: Tier = Tier.TIER1
    model_id: str = "scripted/model"
    calls: list[tuple[NormalizedRequest, PredictionSet, PredictionSet]] = field(default_factory=list)

    def choose(
        self,
        req: NormalizedRequest,
        allowed_cat: PredictionSet,
        allowed_pri: PredictionSet,
        context: OracleContext,
    ) -> OracleAnswer:
        self.calls.append((req, allowed_cat, allowed_pri))
        step = self.script[min(len(self.calls), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        cat, pri = step
        return OracleAnswer(
            category=cat, priority=pri, rationale="scripted", call=fake_call(self.tier, self.model_id)
        )
