"""A tiny fitted `TriageCore` built directly from components (P1.15 tests; no model directory, no ONNX).

Everything is real except the encoder (`HashingEncoder`) and the training data (a dozen sentences). The
conformal quantiles are fixed test values. Lexicons are the live `config/lexicons`.
"""

from __future__ import annotations

from collections.abc import Callable

from campuspulse_ai.adapters.clock import SystemClock
from campuspulse_ai.adapters.guards.bank import compile_bank
from campuspulse_ai.adapters.guards.gibberish import GibberishGuard
from campuspulse_ai.adapters.guards.injection import InjectionGuard
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.memory.null import NullMemoryStore
from campuspulse_ai.adapters.models.embed_lr import EmbedLR
from campuspulse_ai.adapters.models.ensemble import WeightedEnsemble
from campuspulse_ai.adapters.models.evidence import LexiconEvidenceExtractor
from campuspulse_ai.adapters.models.knn import ExampleIndex, IndexEntry, KnnClassifier
from campuspulse_ai.adapters.models.priority_head import LogisticPriorityHead
from campuspulse_ai.adapters.models.tfidf_lr import TfidfLR
from campuspulse_ai.adapters.preprocess.arabizi import ArabiziTransliterator
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.uncertainty.conformal import LACConformal
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.application.services.priority_finalizer import PriorityFinalizer
from campuspulse_ai.application.services.triage_core import TriageCore
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.config.paths import LEXICONS
from campuspulse_ai.domain.ports import SentenceEncoder
from campuspulse_ai.domain.values import ArtifactVersion, Lang
from fixtures.fakes import HashingEncoder
from fixtures.frozen_config import valid_config_dict

ROWS = [
    ("the projector in the lecture room is broken", "Facilities", "medium"),
    ("where is the lost and found office", "Facilities", "low"),
    ("water is leaking near the socket in the lab", "Facilities", "high"),
    ("where is the bus timetable", "Transportation", "low"),
    ("the bus is late again", "Transportation", "medium"),
    ("the last bus was cancelled and students are stranded", "Transportation", "high"),
    ("how do i pay the tuition in installments", "Finance", "low"),
    ("i was charged twice for tuition", "Finance", "medium"),
    ("my university email password expired", "IT Support", "medium"),
    ("the exam portal crashed during my online exam today", "IT Support", "high"),
    ("how do i add a course", "Registration", "low"),
    ("the system removed my registered course", "Registration", "high"),
    ("where can i meet my academic advisor", "Academic Support", "low"),
    ("my grade is wrong on the portal", "Academic Support", "medium"),
]
Q_CATEGORY = 0.9
Q_PRIORITY = 0.8


def build_tiny_core(wrap_encoder: Callable[[SentenceEncoder], SentenceEncoder] | None = None) -> TriageCore:
    """`wrap_encoder`: put a decorator (e.g. `TranslatingEncoder`) in front of the hashing encoder."""
    cfg = FrozenConfig.from_dict(valid_config_dict())
    enc: SentenceEncoder = HashingEncoder()
    if wrap_encoder is not None:
        enc = wrap_encoder(enc)
    texts = [t for t, _, _ in ROWS]
    cats, pris = [c for _, c, _ in ROWS], [p for _, _, p in ROWS]
    m1 = (TfidfLR("category", (2, 5), (1, 2), 4.0, 42), TfidfLR("priority", (2, 5), (1, 2), 4.0, 42))
    m2 = (EmbedLR("category", enc, 4.0, 42), EmbedLR("priority", enc, 4.0, 42))
    for cat_model, pri_model in (m1, m2):
        cat_model.fit(texts, cats)
        pri_model.fit(texts, pris)
    index = ExampleIndex(LocalNumpyVectorStore(enc.dim))
    index.add([IndexEntry(f"r{i}", t, tuple(e), c, p, Lang.EN, "official", f"S{i}", f"G{i}")
               for i, ((t, c, p), e) in enumerate(zip(ROWS, enc.encode(texts), strict=True))])
    k = cfg.knn
    knn = (KnnClassifier("category", index, enc, k.k, k.memory_weight_cap, k.max_memory_neighbors,
                         memory_min_sim=k.memory_min_sim, laplace_mass=k.laplace_mass),
           KnnClassifier("priority", index, enc, k.k, k.memory_weight_cap, k.max_memory_neighbors,
                         memory_min_sim=k.memory_min_sim, laplace_mass=k.laplace_mass))
    members = {"m1": m1, "m2lr": m2, "m2knn": knn}
    even = {m: 1.0 / len(members) for m in members}
    ensemble = WeightedEnsemble(members, enc, index, even, dict(even))  # type: ignore[arg-type]
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, cfg.guards.max_tokens)
    evidence = LexiconEvidenceExtractor.from_yaml(LEXICONS / "urgency.yaml")
    head = LogisticPriorityHead(cfg.priority_head.features, cfg.priority_head.C, cfg.seed)
    reqs = [normalizer.normalize(t) for t in texts]
    head.fit(ensemble_pri := [o.p_pri_model for o in ensemble.predict(texts, None)],
             [evidence.extract(r) for r in reqs], pris, None)
    assert len(ensemble_pri) == len(texts)
    g = cfg.guards
    translit = ArabiziTransliterator.from_yaml(LEXICONS / "arabizi.yaml")
    guards = [
        GibberishGuard(g.gibberish_min_tokens, g.gibberish_min_letter_ratio),
        InjectionGuard(compile_bank(LEXICONS / "injection.yaml", "patterns"), "strip_regex_only",
                       g.injection_sentence_strip_ratio, arabizi_model_text=translit.model_text),
        SafetyGuard(compile_bank(LEXICONS / "safety.yaml", "danger"),
                    compile_bank(LEXICONS / "safety.yaml", "distress")),
    ]
    return TriageCore(
        normalizer=normalizer, guards=guards, ensemble=ensemble, evidence=evidence, head=head,
        finalizer=PriorityFinalizer(),
        conformal_cat=LACConformal.from_quantile("category", 0.1, Q_CATEGORY, 100),
        conformal_pri=LACConformal.from_quantile("priority", 0.1, Q_PRIORITY, 100),
        memory=NullMemoryStore(), clock=SystemClock(), config=cfg,
        artifact=ArtifactVersion(name="tiny", sha256="0" * 64),
    )
