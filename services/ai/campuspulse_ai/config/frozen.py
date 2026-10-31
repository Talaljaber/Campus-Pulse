"""`FrozenConfig`: the validated schema of `models/frozen/vN/config.json` (P1.4, ARCHITECTURE §1.6).

Every learned value (weights, conformal quantiles, thresholds, priors, OOF scores) and every non-learned
model setting lives here; no component reads a threshold from a literal. `train.py` is the only writer.
Inputs come from `config/train.yaml` (knobs) and `config/hand_tuned.yaml` (`tau_faq`, `tau_inc`, LD-11).

Validation is strict (`extra="forbid"`, frozen). `FrozenConfig.load` maps any problem to the domain error
`ArtifactVersionMismatch`; untrained thresholds (≤ 0) are reported as "thresholds not trained".
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS

SCHEMA_VERSION = 1
SUM_TOLERANCE = 1e-6
FETCH_HINT = "run `python scripts/fetch_models.py` (or `python services/ai/train.py`) to create it"

Member = Literal["m1", "m2lr", "m2knn", "m2proto", "m3"]
MEMBERS: tuple[str, ...] = ("m1", "m2lr", "m2knn", "m2proto", "m3")
CATEGORY_ONLY_MEMBERS = frozenset({"m2proto"})  # no priority opinion: weights_priority must be 0 (D-014)
FORBIDDEN_HEAD_FEATURES = frozenset({"stated_urgency"})  # §3.8: never a priority feature

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
OpenUnit = Annotated[float, Field(gt=0.0, le=1.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonEmptyStr = Annotated[str, Field(min_length=1)]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_distribution(name: str, dist: Mapping[str, float], keys: tuple[str, ...]) -> None:
    if set(dist) != set(keys):
        raise ValueError(f"{name} keys must be exactly {sorted(keys)}, got {sorted(dist)}")
    if any(v < 0 or math.isnan(v) for v in dist.values()):
        raise ValueError(f"{name} values must be non-negative")
    if abs(math.fsum(dist.values()) - 1.0) > SUM_TOLERANCE:
        raise ValueError(f"{name} must sum to 1 (got {math.fsum(dist.values())!r})")


class EncoderCfg(_Section):
    """Frozen sentence encoder (ONNX int8 at inference; `hashing` only in test fixtures)."""

    model_id: NonEmptyStr
    revision: NonEmptyStr
    dim: PositiveInt
    max_tokens: PositiveInt
    query_prefix: str
    runtime: Literal["onnx_int8", "hashing"]
    file: str
    pooling: Literal["mean"]
    normalize: bool


class EnsembleCfg(_Section):
    """Config-driven members and per-target weights (each a distribution over exactly the members)."""

    members: tuple[Member, ...] = Field(min_length=1)
    weights_category: dict[str, float]
    weights_priority: dict[str, float]

    @model_validator(mode="after")
    def _weights_match_members(self) -> EnsembleCfg:
        if len(set(self.members)) != len(self.members):
            raise ValueError(f"duplicate ensemble members {self.members}")
        _check_distribution("ensemble.weights_category", self.weights_category, self.members)
        _check_distribution("ensemble.weights_priority", self.weights_priority, self.members)
        nonzero = sorted(m for m in CATEGORY_ONLY_MEMBERS if self.weights_priority.get(m, 0.0) > 0)
        if nonzero:
            raise ValueError(f"{nonzero} have no priority opinion; their weights_priority must be 0")
        return self


class M1Cfg(_Section):
    """TF-IDF (char_wb + word n-grams) → LogisticRegression."""

    char_ngram: tuple[PositiveInt, PositiveInt]
    word_ngram: tuple[PositiveInt, PositiveInt]
    C: PositiveFloat

    @field_validator("char_ngram", "word_ngram")
    @classmethod
    def _ordered(cls, v: tuple[int, int]) -> tuple[int, int]:
        if v[0] > v[1]:
            raise ValueError(f"n-gram range {v} must be (low, high)")
        return v


class M2LrCfg(_Section):
    """Encoder embedding → LogisticRegression."""

    C: PositiveFloat


class KnnCfg(_Section):
    """kNN over the frozen index; memory neighbours are capped (online only)."""

    k: PositiveInt
    memory_weight_cap: Probability
    max_memory_neighbors: NonNegativeInt
    memory_min_sim: Probability
    laplace_mass: PositiveFloat  # pseudo-votes spread evenly over the labels (no label gets probability 0)


class HeadCfg(_Section):
    """LogisticPriorityHead over [p_pri_model ‖ evidence flags]."""

    features: tuple[NonEmptyStr, ...] = Field(min_length=1)
    C: PositiveFloat
    temperature: PositiveFloat = 1.0  # P2.7 calibration (OOF NLL); 1.0 = raw LR (rc1 configs omit it)

    @field_validator("features")
    @classmethod
    def _valid_features(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError(f"duplicate priority_head.features {v}")
        banned = FORBIDDEN_HEAD_FEATURES & set(v)
        if banned:
            raise ValueError(f"{sorted(banned)} must never be a priority feature (§3.8)")
        return v


class ConformalCfg(_Section):
    """LAC conformal quantiles per target (cross-conformal on OOF scores)."""

    method: Literal["lac"]
    alpha_category: Annotated[float, Field(gt=0.0, lt=1.0)]
    alpha_priority: Annotated[float, Field(gt=0.0, lt=1.0)]
    q_category: Probability
    q_priority: Probability
    n_calib: NonNegativeInt
    mondrian_by_lang: bool
    calibration: Literal["row", "group"] = "row"  # how q was computed (P2.7); rc1 configs omit it


class PrototypeCfg(_Section):
    """The department-prototype member m2proto (D-014): softmax(score / temperature) over the prototypes."""

    parts: tuple[Literal["learned", "office"], ...] = Field(min_length=1)
    mix: Probability
    temperature: PositiveFloat


class ThresholdsCfg(_Section):
    """Tuned or hand-tuned thresholds. All must be > 0 after training (§1.6)."""

    tau_ood: float
    tau_faq: float
    tau_inc: float
    tau_injection: float  # may exceed 1: max pool similarity + margin means "no official row fires" (LD-18)
    tau_safety: float
    human_review_maxprob: float

    @model_validator(mode="after")
    def _trained(self) -> ThresholdsCfg:
        values = self.model_dump()
        untrained = sorted(k for k, v in values.items() if not v > 0)  # also catches NaN
        if untrained:
            raise ValueError(f"thresholds not trained: {untrained} must be > 0")
        if self.human_review_maxprob > 1:
            raise ValueError("thresholds.human_review_maxprob must be <= 1")
        return self


class GuardsCfg(_Section):
    """Guard and normalizer limits."""

    max_tokens: PositiveInt
    gibberish_min_tokens: PositiveInt
    gibberish_min_letter_ratio: OpenUnit
    injection_sentence_strip_ratio: OpenUnit


class LlmCfg(_Section):
    """LLM tier merge settings (the tiers themselves are configured in Settings/env)."""

    w_llm: Probability
    prompt_version: NonEmptyStr


class ExplainCfg(_Section):
    """Occlusion explainer budget."""

    max_occlusions: PositiveInt


class PriorsCfg(_Section):
    """Label frequencies of the training pool; their argmax labels empty input (LD-17)."""

    category: dict[str, float]
    priority: dict[str, float]

    @model_validator(mode="after")
    def _distributions(self) -> PriorsCfg:
        _check_distribution("priors.category", self.category, CATEGORY_LABELS)
        _check_distribution("priors.priority", self.priority, PRIORITY_LABELS)
        return self


class CvCfg(_Section):
    """The frozen-fold CV protocol and its OOF results (LD-31)."""

    k: Annotated[int, Field(ge=2)]
    group_col: NonEmptyStr
    fold_col: NonEmptyStr
    folds_file: NonEmptyStr
    oof_macro_f1_category: Probability
    oof_macro_f1_priority: Probability


class FrozenConfig(_Section):
    """Schema of `config.json` (ARCHITECTURE §1.6 + LD-10 keys). Immutable once loaded."""

    schema_version: Literal[1]
    artifact_version: NonEmptyStr
    trained_at: NonEmptyStr
    seed: int
    encoder: EncoderCfg
    ensemble: EnsembleCfg
    m1: M1Cfg
    m2lr: M2LrCfg
    knn: KnnCfg
    priority_head: HeadCfg
    conformal: ConformalCfg
    thresholds: ThresholdsCfg
    guards: GuardsCfg
    llm: LlmCfg
    explain: ExplainCfg
    priors: PriorsCfg
    cv: CvCfg
    prototype: PrototypeCfg | None = None  # required when m2proto is a member (D-014)

    @model_validator(mode="after")
    def _prototype_when_member(self) -> FrozenConfig:
        if "m2proto" in self.ensemble.members and self.prototype is None:
            raise ValueError("ensemble member m2proto needs the `prototype` section")
        return self

    @classmethod
    def load(cls, path: Path) -> FrozenConfig:
        """Read and validate `config.json`.

        Raises:
            ArtifactMissing: the file does not exist (message carries the fetch/train hint).
            ArtifactVersionMismatch: invalid JSON, wrong schema version, an unknown or missing key, an
                invalid value, or untrained thresholds ("thresholds not trained").
        """
        path = Path(path)
        if not path.is_file():
            raise ArtifactMissing(f"{path} not found; {FETCH_HINT}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactVersionMismatch(f"{path}: unreadable config.json: {exc}") from exc
        return cls.from_dict(data, source=str(path))

    @classmethod
    def from_dict(cls, data: object, *, source: str = "config") -> FrozenConfig:
        """Validate an in-memory mapping (what `load` does after parsing).

        Raises:
            ArtifactVersionMismatch: as for `load`.
        """
        if isinstance(data, dict) and data.get("schema_version") != SCHEMA_VERSION:
            found = data.get("schema_version")
            message = f"{source}: schema_version {found!r}, code expects {SCHEMA_VERSION}"
            raise ArtifactVersionMismatch(message)
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            reason = "thresholds not trained" if "thresholds not trained" in str(exc) else "invalid config"
            raise ArtifactVersionMismatch(f"{source}: {reason}: {exc}") from exc

    def to_json(self) -> str:
        """Canonical JSON: sorted keys, indent 2, UTF-8 characters kept, trailing newline."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False) + "\n"

    def save(self, path: Path) -> None:
        """Write `to_json()` with LF line endings (byte-stable across OSes)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.to_json())
