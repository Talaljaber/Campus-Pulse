"""`build_offline`: the composition root of `predict.py`, `train.py` checks and `evaluate.py` (§1.5, §3.11).

Wires one `TriageCore` from a frozen model directory (`models/frozen/vN`) with offline-only adapters:
`NullMemoryStore`, `NullOracle`, `LocalNumpyVectorStore` and the ONNX encoder. Nothing on this import graph
touches Supabase, httpx, notifiers, calendars, Linear or torch (`tests/test_architecture.py` checks the
loaded modules in a subprocess).

Steps (§1.5):
 1. `FileArtifactStore.load_manifest(model_dir)`: sha256 of every listed file, encoder included.
 2. `FrozenConfig.load(model_dir / "config.json")`.
 3. encoder = `encoder_override` or `OnnxEncoder(model_dir / "encoder")`; its id, revision and width must
    match the config (a model trained with the test `hashing` encoder needs `encoder_override`). With
    `config.translate.enabled` the ONNX encoder is wrapped by `TranslatingEncoder` (D-019); the translator
    files must be present (`ArtifactMissing`, never a silent fallback).
 4. vectors = `LocalNumpyVectorStore.load(model_dir / "index")`, exactly `train`, `injection_exemplars` and
    `safety_exemplars` (LD-20).
 5. members per `config.ensemble.members`: `TfidfLR.load`, `EmbedLR.load`, `KnnClassifier` over `train`,
    `PrototypeClassifier.load` (m2proto, D-014: the office descriptions are already embedded in the dir).
 6. guards Gibberish → Injection (`strip_regex_only`, Arabizi-aware) → Safety (danger from the lexicon only,
    no exemplars: LD-19), all built from the model dir's lexicon snapshot (LD-12).
 7. memory = `NullMemoryStore`; oracle = `NullOracle` (`use_llm=True` raises `LLMUnavailable` until P3).
 8. `TriageCore`, then `BatchPredictUseCase`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from campuspulse_ai.adapters.artifacts.io import FileArtifactStore
from campuspulse_ai.adapters.clock import SystemClock
from campuspulse_ai.adapters.guards.bank import compile_bank
from campuspulse_ai.adapters.guards.gibberish import GibberishGuard
from campuspulse_ai.adapters.guards.injection import InjectionGuard
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.llm.null import NullOracle
from campuspulse_ai.adapters.memory.null import NullMemoryStore
from campuspulse_ai.adapters.models.embed_lr import EmbedLR
from campuspulse_ai.adapters.models.encoder import OnnxEncoder
from campuspulse_ai.adapters.models.ensemble import WeightedEnsemble
from campuspulse_ai.adapters.models.evidence import LexiconEvidenceExtractor
from campuspulse_ai.adapters.models.knn import TRAIN_COLLECTION, ExampleIndex, KnnClassifier
from campuspulse_ai.adapters.models.priority_head import LogisticPriorityHead
from campuspulse_ai.adapters.models.prototype import PrototypeClassifier
from campuspulse_ai.adapters.models.tfidf_lr import TfidfLR
from campuspulse_ai.adapters.models.urgency_floor import UrgencyFloorRule
from campuspulse_ai.adapters.preprocess.arabizi import ArabiziTransliterator
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.uncertainty.conformal import LACConformal, MondrianByLang
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.application.services.priority_finalizer import PriorityFinalizer
from campuspulse_ai.application.services.triage_core import TriageCore
from campuspulse_ai.application.use_cases.batch import read_batch_csv, write_predictions_csv
from campuspulse_ai.application.use_cases.batch_predict import BatchPredictUseCase, BatchRow
from campuspulse_ai.composition.arabizi_llm import has_key, llm_arabizi_requested, wrap_llm_arabizi
from campuspulse_ai.composition.translation import make_translator, wrap_encoder
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactVersionMismatch, LLMUnavailable
from campuspulse_ai.domain.ports import Guard, LabelOracle, ProbabilisticClassifier, SentenceEncoder
from campuspulse_ai.domain.values import ArtifactVersion, Manifest

__all__ = [
    "BatchRow",
    "OfflineBatchLabeler",
    "OfflineContainer",
    "build_offline",
    "read_batch_csv",
    "resolve_model_dir",
    "write_predictions_csv",
]

INDEX_DIR = "index"
LEXICON_DIR = "lexicons"
ENCODER_DIR = "encoder"
HEAD_DIR = "head"
PROTO_TOLERANCE = 1e-9  # m2proto meta.json and config.json must carry the same temperature
OFFLINE_COLLECTIONS = frozenset({TRAIN_COLLECTION, "injection_exemplars", "safety_exemplars"})
USE_LLM_MESSAGE = (
    "--use-llm needs OPENROUTER_API_KEY (the optional LLM Arabizi translator, D-025); "
    "run without --use-llm (tier 0 is fully offline)"
)


class OfflineBatchLabeler:
    """Adapts `BatchPredictUseCase` to the `BatchLabeler` port of `/v1/batch` (`use_cases/ports.py`).

    `label([(request_id, text)], use_llm=...)` returns `[(request_id, category, priority)]` in input order:
    the same labels `predict.py` writes (empty text gets the priors' argmax, LD-17).
    Raises `ArtifactError` only from construction (`build_offline`); labelling itself does not.
    """

    def __init__(self, batch: BatchPredictUseCase) -> None:
        self._batch = batch

    def label(self, rows: Sequence[tuple[str, str]], *, use_llm: bool) -> list[tuple[str, str, str]]:
        predictions = self._batch.run([BatchRow(rid, text) for rid, text in rows], use_llm=use_llm)
        return [(p.request_id, p.category, p.priority) for p in predictions]


@dataclass(frozen=True)
class OfflineContainer:
    core: TriageCore
    oracle: LabelOracle
    config: FrozenConfig
    manifest: Manifest
    batch: BatchPredictUseCase
    vectors: LocalNumpyVectorStore
    encoder: SentenceEncoder  # translate-test + ONNX: the space of the index, members and live memory
    raw_encoder: SentenceEncoder | None = None  # ONNX only: the FAQ vectors space (scripts/seed_faq.py)

    @property
    def labeler(self) -> OfflineBatchLabeler:
        """The `BatchLabeler` for `/v1/batch` (same labels as `predict.py`)."""
        return OfflineBatchLabeler(self.batch)


def resolve_model_dir(path: Path) -> Path:
    """`models/frozen` → `models/frozen/<CURRENT>`; a version directory is returned as is."""
    path = Path(path)
    current = path / "CURRENT"
    if not (path / "config.json").exists() and current.is_file():
        return path / current.read_text(encoding="utf-8").strip()
    return path


def build_offline(
    model_dir: Path,
    *,
    use_llm: bool = False,
    settings: Settings | None = None,
    encoder_override: SentenceEncoder | None = None,
) -> OfflineContainer:
    """Build the offline container from a frozen model directory (module docstring).

    Raises:
        ArtifactMissing, ArtifactChecksumMismatch, ArtifactVersionMismatch: an unusable model directory.
        LLMUnavailable: `use_llm=True` without an OpenRouter key. With a key, `use_llm` (or
            `LLM_ARABIZI_TRANSLATE=true`) puts the optional LLM Arabizi translator in front of the encoder
            (P2.20, D-025); the offline oracle stays `NullOracle`.
    """
    settings = settings or Settings()
    if use_llm and not has_key(settings):
        raise LLMUnavailable(USE_LLM_MESSAGE)
    model_dir = resolve_model_dir(model_dir)
    manifest = FileArtifactStore().load_manifest(model_dir)
    config = FrozenConfig.load(model_dir / "config.json")
    raw_encoder = encoder_override or _onnx_encoder(model_dir, config, settings)
    # D-019: translation sits in front of the encoder only; guards, langid, M1 and conformal never see it.
    # An `encoder_override` is complete as given (training and ablations already wrap their own).
    encoder = (
        raw_encoder
        if encoder_override is not None
        else wrap_encoder(raw_encoder, make_translator(model_dir, config.translate), config.translate)
    )
    if encoder_override is None and llm_arabizi_requested(settings, use_llm):
        # P2.20 (D-025): optional LLM Arabizi translation, in front of the encoder only; off by default.
        encoder = wrap_llm_arabizi(encoder, settings)
    if encoder.dim != config.encoder.dim:
        raise ArtifactVersionMismatch(f"encoder dim {encoder.dim} != config encoder.dim {config.encoder.dim}")

    vectors = LocalNumpyVectorStore.load(model_dir / INDEX_DIR, expected_dim=config.encoder.dim)
    if vectors.collections() != OFFLINE_COLLECTIONS:
        found = sorted(vectors.collections())
        raise ArtifactVersionMismatch(
            f"{model_dir / INDEX_DIR}: collections {found}, expected {sorted(OFFLINE_COLLECTIONS)}"
        )
    index = ExampleIndex(vectors, TRAIN_COLLECTION)
    members: dict[str, tuple[ProbabilisticClassifier, ProbabilisticClassifier]] = {}
    for name in config.ensemble.members:
        members[name] = _member(name, model_dir, config, encoder, index)
    ensemble = WeightedEnsemble(
        members,
        encoder,
        index,
        config.ensemble.weights_category,
        config.ensemble.weights_priority,
        memory_weight_category=config.ensemble.memory_weight_category,
    )

    lex = model_dir / LEXICON_DIR
    g = config.guards
    translit = ArabiziTransliterator.from_yaml(lex / "arabizi.yaml")
    guards: list[Guard] = [
        GibberishGuard(g.gibberish_min_tokens, g.gibberish_min_letter_ratio),
        InjectionGuard(
            compile_bank(lex / "injection.yaml", "patterns"),
            "strip_regex_only",
            g.injection_sentence_strip_ratio,
            arabizi_model_text=translit.model_text,
        ),
        SafetyGuard(
            compile_bank(lex / "safety.yaml", "danger"), compile_bank(lex / "safety.yaml", "distress")
        ),
    ]
    head = LogisticPriorityHead.load(model_dir / HEAD_DIR)
    if head.features != config.priority_head.features:
        expected = config.priority_head.features
        raise ArtifactVersionMismatch(f"head features {head.features} != config {expected}")
    head.temperature = config.priority_head.temperature  # config.json is the source of truth (P2.7)
    core = TriageCore(
        normalizer=DefaultNormalizer.from_lexicons(lex, g.max_tokens),
        guards=guards,
        ensemble=ensemble,
        evidence=LexiconEvidenceExtractor.from_yaml(lex / "urgency.yaml", config.priority_head.features),
        head=head,
        finalizer=PriorityFinalizer(),
        conformal_cat=conformal_predictor(config, "category"),
        conformal_pri=conformal_predictor(config, "priority"),
        memory=NullMemoryStore(),
        clock=SystemClock(),
        config=config,
        artifact=ArtifactVersion(name=config.artifact_version, sha256=manifest.sha),
        urgency_floor=UrgencyFloorRule.from_yaml(lex / "urgency.yaml"),
    )
    oracle = NullOracle()
    return OfflineContainer(
        core=core,
        oracle=oracle,
        config=config,
        manifest=manifest,
        batch=BatchPredictUseCase(core, oracle, config),
        vectors=vectors,
        encoder=encoder,
        raw_encoder=raw_encoder,
    )


def _onnx_encoder(model_dir: Path, config: FrozenConfig, settings: Settings) -> OnnxEncoder:
    if config.encoder.runtime != "onnx_int8":
        raise ArtifactVersionMismatch(
            f"{model_dir} was trained with the {config.encoder.runtime!r} encoder; pass encoder_override"
        )
    encoder = OnnxEncoder(
        model_dir / ENCODER_DIR,
        query_prefix=config.encoder.query_prefix,
        max_tokens=config.encoder.max_tokens,
        intra_op_threads=settings.ort_intra_op_threads,
        low_memory=settings.ort_low_memory,
    )
    if (encoder.model_id, encoder.revision) != (config.encoder.model_id, config.encoder.revision):
        raise ArtifactVersionMismatch(
            f"encoder {encoder.model_id}@{encoder.revision} != config "
            f"{config.encoder.model_id}@{config.encoder.revision}"
        )
    return encoder


def conformal_predictor(config: FrozenConfig, target: str) -> LACConformal | MondrianByLang:
    """The target's conformal predictor from `config.json`: one global LAC quantile, or `MondrianByLang`
    when per-language quantiles were frozen (P2.10)."""
    c = config.conformal
    if target == "category":
        alpha, q, per = c.alpha_category, c.q_category, c.q_category_by_lang
    else:
        alpha, q, per = c.alpha_priority, c.q_priority, c.q_priority_by_lang
    lac = LACConformal.from_quantile(target, alpha, q, c.n_calib)  # type: ignore[arg-type]
    if not (c.mondrian_by_lang and per):
        return lac
    inner = {lang: LACConformal.from_quantile(target, alpha, v, c.n_calib) for lang, v in per.items()}  # type: ignore[arg-type]
    for lang, donor in c.q_lang_alias.items():  # P2.18: no rows of its own: borrow the donor q
        if donor in inner:
            inner[lang] = inner[donor]
    return MondrianByLang(inner, lac)


def _member(
    name: str, model_dir: Path, config: FrozenConfig, encoder: SentenceEncoder, index: ExampleIndex
) -> tuple[ProbabilisticClassifier, ProbabilisticClassifier]:
    if name == "m1":
        return TfidfLR.load(model_dir / "m1" / "category"), TfidfLR.load(model_dir / "m1" / "priority")
    if name == "m2lr":
        return (
            EmbedLR.load(model_dir / "m2lr" / "category", encoder),
            EmbedLR.load(model_dir / "m2lr" / "priority", encoder),
        )
    if name == "m2knn":
        k = config.knn
        settings = {"memory_min_sim": k.memory_min_sim, "laplace_mass": k.laplace_mass}
        return (
            KnnClassifier(
                "category", index, encoder, k.k, k.memory_weight_cap, k.max_memory_neighbors, **settings
            ),
            KnnClassifier(
                "priority", index, encoder, k.k, k.memory_weight_cap, k.max_memory_neighbors, **settings
            ),
        )
    if name == "m2proto":
        cat = PrototypeClassifier.load(model_dir / "m2proto" / "category", encoder)
        pri = PrototypeClassifier.load(model_dir / "m2proto" / "priority", encoder)
        frozen_t = config.prototype.temperature if config.prototype is not None else None
        if frozen_t is None or abs(cat.temperature - frozen_t) > PROTO_TOLERANCE:
            raise ArtifactVersionMismatch("m2proto temperature differs from config.json prototype")
        return cat, pri
    raise ArtifactVersionMismatch(f"ensemble member {name!r} is not available offline (M3 is cut, UD-4)")
