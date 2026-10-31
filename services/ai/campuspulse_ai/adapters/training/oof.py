"""Stage A of `train.py`: out-of-fold predictions over the frozen folds (P1.16, ARCHITECTURE §3.4).

`run_cv` lives here rather than in `cv.py` so the leakage-critical splitter (`group_folds`) stays a small,
model-free module. Every number it produces is scenario-held-out: a row's probabilities come from members,
an index and a priority head that never saw its `cv_group`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.models.embed_lr import EmbedLR
from campuspulse_ai.adapters.models.knn import (
    SOURCE_OFFICIAL,
    TRAIN_COLLECTION,
    ExampleIndex,
    IndexEntry,
    KnnClassifier,
)
from campuspulse_ai.adapters.models.priority_head import LogisticPriorityHead
from campuspulse_ai.adapters.models.probs import Target, target_labels, to_matrix, to_vectors
from campuspulse_ai.adapters.models.soft_targets import SoftTargetExpander
from campuspulse_ai.adapters.models.tfidf_lr import TfidfLR
from campuspulse_ai.adapters.training.cv import group_folds
from campuspulse_ai.adapters.training.pool import Pool
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import PRIORITY_LABELS, Priority
from campuspulse_ai.domain.ports import EvidenceExtractor, Guard, Normalizer, SentenceEncoder
from campuspulse_ai.domain.values import EvidenceVector

TARGETS: tuple[Target, Target] = ("category", "priority")
HIGH = PRIORITY_LABELS.index(Priority.HIGH.value)
Member = TfidfLR | EmbedLR | KnnClassifier


@dataclass(frozen=True)
class PipelineToggles:
    """Switches for the P2.9 ablations; the defaults are the shipped pipeline."""

    strip_wrappers: bool = True
    use_augmentation: bool = True
    use_evidence: bool = True
    members: tuple[str, ...] = ("m1", "m2lr", "m2knn")
    soft_targets: bool = True
    arabizi_translit: bool = True


@dataclass(frozen=True)
class TrainingKit:
    """The non-learned collaborators (built from the same lexicons as inference)."""

    normalizer: Normalizer
    evidence: EvidenceExtractor
    safety: Guard
    expander: SoftTargetExpander
    features: tuple[str, ...]


@dataclass(frozen=True)
class OOFResult:
    """Out-of-fold outputs; row i is pool row i.

    `probs` keys: `"<member>.<target>"`, `ensemble.category`, `ensemble.priority` (the members' priority
    average, before the head), `head.priority` (OOF head) and `final.priority` (head + safety floor), each an
    (n, L) array in the target's label order. `embeddings` are the encoder vectors of `pool.model_text`.
    """

    probs: Mapping[str, NDArray[np.float64]]
    max_sim: NDArray[np.float64]
    fold: NDArray[np.int64]
    safety: NDArray[np.bool_]
    evidence: tuple[EvidenceVector, ...]
    embeddings: NDArray[np.float32]
    pool: Pool
    members: tuple[str, ...]

    @property
    def head_pri(self) -> NDArray[np.float64]:
        return self.probs["head.priority"]


def evidence_and_safety(
    pool: Pool, kit: TrainingKit, use_evidence: bool = True
) -> tuple[tuple[EvidenceVector, ...], NDArray[np.bool_]]:
    """Evidence flags and the offline safety floor per pool row, read from `model_text` as at inference."""
    evidence: list[EvidenceVector] = []
    safety = np.zeros(len(pool), dtype=bool)
    off = EvidenceVector(flags=dict.fromkeys(kit.features, False))
    for i, (raw, model_text) in enumerate(zip(pool.raw, pool.model_text, strict=True)):
        req = dataclasses.replace(kit.normalizer.normalize(raw), model_text=model_text)
        evidence.append(kit.evidence.extract(req) if use_evidence else off)
        safety[i] = kit.safety.inspect(req).kind == "danger"
    return tuple(evidence), safety


def index_entries(pool: Pool, rows: Sequence[int], emb: NDArray[np.float32]) -> list[IndexEntry]:
    """One entry per distinct `model_text` among `rows` (first occurrence; official hard labels)."""
    seen: set[str] = set()
    entries: list[IndexEntry] = []
    for i in rows:
        text = pool.model_text[i]
        if text in seen:
            continue
        seen.add(text)
        entries.append(IndexEntry(
            id=pool.request_id[i], text=text, embedding=tuple(float(x) for x in emb[i]),
            category=pool.category[i], priority=pool.priority[i], lang=pool.lang[i],
            source=SOURCE_OFFICIAL if pool.is_official[i] else pool.source[i],
            scenario_id=pool.scenario_id[i], cv_group=pool.cv_group[i],
        ))
    return entries


def build_index(pool: Pool, rows: Sequence[int], emb: NDArray[np.float32], dim: int) -> ExampleIndex:
    index = ExampleIndex(LocalNumpyVectorStore(dim), TRAIN_COLLECTION)
    index.add(index_entries(pool, rows, emb))
    return index


def expanded(
    kit: TrainingKit, pool: Pool, target: Target, rows: Sequence[int], soft: bool
) -> tuple[list[int], list[str], list[float]]:
    """(row, label, weight) for `rows`: the soft-target expansion (§3.3), or the hard labels."""
    allowed = {int(r) for r in rows}
    if soft:
        idx, labels, weights = kit.expander.expand(pool, target)
        keep = [j for j, i in enumerate(idx) if i in allowed]
        return [idx[j] for j in keep], [labels[j] for j in keep], [weights[j] for j in keep]
    hard = pool.category if target == "category" else pool.priority
    ordered = sorted(allowed)
    return ordered, [hard[i] for i in ordered], [1.0] * len(ordered)


def knn_member(target: Target, index: ExampleIndex, knn: Mapping[str, Any]) -> KnnClassifier:
    return KnnClassifier(target, index, None, int(knn["k"]), float(knn["memory_weight_cap"]),
                         int(knn["max_memory_neighbors"]), memory_min_sim=float(knn["memory_min_sim"]),
                         laplace_mass=float(knn["laplace_mass"]))


def fit_text_member(
    name: str, target: Target, cfg: TrainCfg, rows: Sequence[int], labels: Sequence[str],
    weights: Sequence[float], pool: Pool, emb: NDArray[np.float32],
) -> TfidfLR | EmbedLR:
    """Fit M1 or M2-LR for one target on (expanded) rows."""
    if name == "m1":
        m1 = cfg.section("m1")
        char = (int(m1["char_ngram"][0]), int(m1["char_ngram"][1]))
        word = (int(m1["word_ngram"][0]), int(m1["word_ngram"][1]))
        tfidf = TfidfLR(target, char, word, cfg.m1_C, cfg.seed)
        tfidf.fit([pool.model_text[i] for i in rows], labels, weights)
        return tfidf
    if name == "m2lr":
        lr = EmbedLR(target, None, cfg.m2lr_C, cfg.seed)
        lr.fit_embeddings(emb[list(rows)], labels, weights)
        return lr
    raise ValueError(f"unknown text member {name!r}")


def predict_member(model: Member, pool: Pool, rows: Sequence[int], emb: NDArray[np.float32]
                   ) -> NDArray[np.float64]:
    if isinstance(model, TfidfLR):
        vectors = model.predict_proba([pool.model_text[i] for i in rows])
    elif isinstance(model, EmbedLR):
        vectors = model.predict_proba_from_embeddings(emb[list(rows)])
    else:
        vectors = model.predict_from_embeddings(emb[list(rows)])
    return to_matrix(vectors, target_labels(model.target))


def equal_weights(members: Sequence[str]) -> dict[str, float]:
    """Provisional stage B (P1.16): every member weighs the same; P2.7 tunes the weights on OOF."""
    return {m: 1.0 / len(members) for m in members}


def ensemble_matrix(probs: Mapping[str, NDArray[np.float64]], members: Sequence[str], target: str,
                    weights: Mapping[str, float]) -> NDArray[np.float64]:
    out = np.zeros_like(probs[f"{members[0]}.{target}"])
    for m in members:
        out += weights[m] * probs[f"{m}.{target}"]
    result: NDArray[np.float64] = out / out.sum(axis=1, keepdims=True)
    return result


def floor_safety(p_pri: NDArray[np.float64], safety: NDArray[np.bool_]) -> NDArray[np.float64]:
    """`PriorityFinalizer`'s safety floor on a matrix: one-hot high where `safety`."""
    out = p_pri.copy()
    out[safety] = 0.0
    out[safety, HIGH] = 1.0
    return out


def run_cv(pool: Pool, encoder: SentenceEncoder, cfg: TrainCfg, toggles: PipelineToggles,
           kit: TrainingKit) -> OOFResult:
    """Stage A over the frozen `cv_fold` folds (§3.4).

    Per fold: M1 and M2-LR per target on fold-train rows (soft-target weights), a kNN index of fold-train
    rows only, held-out probabilities and max-similarity. Then the equal-weight ensemble, and the priority
    head per outer fold, fitted on the other folds' OOF ensemble priority vectors + evidence. Texts are
    encoded once here (wrap `encoder` in `CachingEncoder` to share them with stage C).

    Raises:
        InvalidInput: no member left after the toggles, or a fold problem (`group_folds`).
    """
    members = tuple(m for m in toggles.members if m in cfg.members)
    if not members:
        raise InvalidInput("no ensemble member left after the toggles")
    n = len(pool)
    emb = np.asarray(encoder.encode(list(pool.model_text)), dtype=np.float32).reshape(n, -1)
    folds = group_folds(pool, cfg.k)
    probs: dict[str, NDArray[np.float64]] = {
        f"{m}.{t}": np.zeros((n, len(target_labels(t))), dtype=np.float64) for m in members for t in TARGETS
    }
    max_sim = np.zeros(n, dtype=np.float64)
    knn_cfg = cfg.section("knn")
    for train_idx, test_idx in folds:
        tr, te = train_idx.tolist(), test_idx.tolist()
        index = build_index(pool, tr, emb, encoder.dim)
        for t in TARGETS:
            rows, labels, weights = expanded(kit, pool, t, tr, toggles.soft_targets)
            for m in members:
                model: Member = (knn_member(t, index, knn_cfg) if m == "m2knn"
                                 else fit_text_member(m, t, cfg, rows, labels, weights, pool, emb))
                probs[f"{m}.{t}"][test_idx] = predict_member(model, pool, te, emb)
        for i in te:
            max_sim[i] = index.max_similarity(emb[i].tolist())
    weights_eq = equal_weights(members)
    for t in TARGETS:
        probs[f"ensemble.{t}"] = ensemble_matrix(probs, members, t, weights_eq)
    evidence, safety = evidence_and_safety(pool, kit, toggles.use_evidence)
    ens_pri = to_vectors(probs["ensemble.priority"], PRIORITY_LABELS)
    head_pri = np.zeros((n, len(PRIORITY_LABELS)), dtype=np.float64)
    head_c = float(cfg.section("priority_head")["C"])
    for train_idx, test_idx in folds:
        rows, labels, weights = expanded(kit, pool, "priority", train_idx.tolist(), toggles.soft_targets)
        head = LogisticPriorityHead(kit.features, head_c, cfg.seed)
        head.fit([ens_pri[i] for i in rows], [evidence[i] for i in rows], labels, weights)
        x = head.matrix([ens_pri[i] for i in test_idx], [evidence[i] for i in test_idx])
        head_pri[test_idx] = to_matrix(head.predict_matrix(x), PRIORITY_LABELS)
    probs["head.priority"] = head_pri
    probs["final.priority"] = floor_safety(head_pri, safety)
    return OOFResult(probs=probs, max_sim=max_sim, fold=np.asarray(pool.cv_fold, dtype=np.int64),
                     safety=safety, evidence=evidence, embeddings=emb, pool=pool, members=members)
