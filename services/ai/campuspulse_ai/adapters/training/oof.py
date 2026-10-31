"""Stage A and the OOF selections of stage B (P1.16, P2.7, D-014; ARCHITECTURE §3.4).

`run_cv` lives here rather than in `cv.py` so the leakage-critical splitter (`group_folds`) stays a small,
model-free module. Every number it produces is scenario-held-out: a row's probabilities come from members,
prototypes, an index and a priority head that never saw its `cv_group`.

Stage A computes, over the frozen `cv_fold` folds, the OOF probabilities of every member: M1 and M2-LR for
every `C` of their grids, M2-kNN, and the raw prototype scores of `m2proto` (learned prototypes from each
fold's training groups only, plus the office descriptions). Stage B then chooses, **on official OOF rows
only** (never our own test set):
  1. `m1.C`, `m2lr.C`: the best member OOF category macro-F1 (tie: priority macro-F1, then the grid midpoint);
  2. the prototype temperature: the lowest OOF category negative log-likelihood;
  3. `weights_category`: the simplex grid point with the best ensemble OOF category macro-F1;
  4. `weights_priority` (members with a priority opinion; `m2proto` is fixed at 0): the best OOF macro-F1
     of the whole priority path (members -> head -> safety floor);
  5. the head temperature: the lowest OOF negative log-likelihood of the final priority vectors.
The same selection is repeated five times with one fold left out and applied to that fold (`nested`), so
the report can show how much of the tuned OOF score is selection optimism (LD-32: about 30 groups).
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
from campuspulse_ai.adapters.models.probs import (
    Target,
    target_labels,
    temperature_scale,
    to_matrix,
    to_vectors,
)
from campuspulse_ai.adapters.models.prototype import (
    NAME as PROTO,
)
from campuspulse_ai.adapters.models.prototype import (
    PARTS,
    PrototypeSet,
    category_scores,
    learned_prototypes,
    softmax,
)
from campuspulse_ai.adapters.models.soft_targets import SoftTargetExpander
from campuspulse_ai.adapters.models.tfidf_lr import TfidfLR
from campuspulse_ai.adapters.training.cv import group_folds
from campuspulse_ai.adapters.training.metrics import macro_f1
from campuspulse_ai.adapters.training.pool import Pool
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.adapters.training.tuning import (
    best_temperature,
    conformal_quantile,
    nll,
    select_from_grid,
    simplex_weights,
)
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Priority
from campuspulse_ai.domain.ports import EvidenceExtractor, Guard, Normalizer, SentenceEncoder
from campuspulse_ai.domain.values import EvidenceVector

TARGETS: tuple[Target, Target] = ("category", "priority")
HIGH = PRIORITY_LABELS.index(Priority.HIGH.value)
ALL_MEMBERS: tuple[str, ...] = ("m1", "m2lr", "m2knn", PROTO)
CATEGORY_ONLY: frozenset[str] = frozenset({PROTO})  # members without a priority opinion (weight fixed at 0)
TEXT_MEMBERS: tuple[str, str] = ("m1", "m2lr")
Member = TfidfLR | EmbedLR | KnnClassifier
Folds = list[tuple[NDArray[np.int64], NDArray[np.int64]]]


@dataclass(frozen=True)
class PipelineToggles:
    """Switches for the P2.9 ablations; the defaults are the shipped pipeline (members come from config)."""

    strip_wrappers: bool = True
    use_augmentation: bool = True
    use_evidence: bool = True
    members: tuple[str, ...] = ALL_MEMBERS
    soft_targets: bool = True
    arabizi_translit: bool = True
    proto_parts: tuple[str, ...] = PARTS
    include_unreviewed: bool = False  # the labelled "unreviewed augmentation" arm only; never train.py


@dataclass(frozen=True)
class TrainingKit:
    """The non-learned collaborators (built from the same lexicons as inference)."""

    normalizer: Normalizer
    evidence: EvidenceExtractor
    safety: Guard
    expander: SoftTargetExpander
    features: tuple[str, ...]
    office: PrototypeSet | None = None  # embedded office descriptions (D-014); None without m2proto


@dataclass(frozen=True)
class StageBChoices:
    """Everything stage B picks on OOF (P2.7). Weights cover exactly the members."""

    m1_C: float
    m2lr_C: float
    proto_temperature: float
    weights_category: dict[str, float]
    weights_priority: dict[str, float]
    head_temperature: float

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class OOFResult:
    """Out-of-fold outputs; row i is pool row i.

    `probs` keys: `"<member>.<target>"` (members at the chosen `C`; `m2proto.category` at the chosen
    temperature, `m2proto.priority` uniform), `ensemble.category`, `ensemble.priority` (the weighted members'
    priority, before the head), `head.priority` (OOF head, temperature-scaled) and `final.priority` (head +
    safety floor), each an (n, L) array in the target's label order. `proto_scores` are the raw (n, 6)
    prototype similarities (None without `m2proto`). `selection` holds the grid scores behind every choice,
    `nested` the leave-one-fold-out estimates (empty when not computed).
    """

    probs: Mapping[str, NDArray[np.float64]]
    max_sim: NDArray[np.float64]
    fold: NDArray[np.int64]
    safety: NDArray[np.bool_]
    evidence: tuple[EvidenceVector, ...]
    embeddings: NDArray[np.float32]
    pool: Pool
    members: tuple[str, ...]
    choices: StageBChoices
    proto_scores: NDArray[np.float64] | None = None
    selection: Mapping[str, Any] = field(default_factory=dict)
    nested: Mapping[str, Any] = field(default_factory=dict)
    head_members: tuple[str, ...] = ()

    @property
    def head_pri(self) -> NDArray[np.float64]:
        return self.probs["head.priority"]


# --- stage A building blocks ---------------------------------------------------------------------------


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
        entries.append(
            IndexEntry(
                id=pool.request_id[i],
                text=text,
                embedding=tuple(float(x) for x in emb[i]),
                category=pool.category[i],
                priority=pool.priority[i],
                lang=pool.lang[i],
                source=SOURCE_OFFICIAL if pool.is_official[i] else pool.source[i],
                scenario_id=pool.scenario_id[i],
                cv_group=pool.cv_group[i],
            )
        )
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
    return KnnClassifier(
        target,
        index,
        None,
        int(knn["k"]),
        float(knn["memory_weight_cap"]),
        int(knn["max_memory_neighbors"]),
        memory_min_sim=float(knn["memory_min_sim"]),
        laplace_mass=float(knn["laplace_mass"]),
    )


def fit_text_member(
    name: str,
    target: Target,
    cfg: TrainCfg,
    rows: Sequence[int],
    labels: Sequence[str],
    weights: Sequence[float],
    pool: Pool,
    emb: NDArray[np.float32],
    C: float,
) -> TfidfLR | EmbedLR:
    """Fit M1 or M2-LR for one target on (expanded) rows with regularization `C`."""
    if name == "m1":
        m1 = cfg.section("m1")
        char = (int(m1["char_ngram"][0]), int(m1["char_ngram"][1]))
        word = (int(m1["word_ngram"][0]), int(m1["word_ngram"][1]))
        tfidf = TfidfLR(target, char, word, C, cfg.seed)
        tfidf.fit([pool.model_text[i] for i in rows], labels, weights)
        return tfidf
    if name == "m2lr":
        lr = EmbedLR(target, None, C, cfg.seed)
        lr.fit_embeddings(emb[list(rows)], labels, weights)
        return lr
    raise ValueError(f"unknown text member {name!r}")


def predict_member(
    model: Member, pool: Pool, rows: Sequence[int], emb: NDArray[np.float32]
) -> NDArray[np.float64]:
    if isinstance(model, TfidfLR):
        vectors = model.predict_proba([pool.model_text[i] for i in rows])
    elif isinstance(model, EmbedLR):
        vectors = model.predict_proba_from_embeddings(emb[list(rows)])
    else:
        vectors = model.predict_from_embeddings(emb[list(rows)])
    return to_matrix(vectors, target_labels(model.target))


def equal_weights(members: Sequence[str]) -> dict[str, float]:
    """Every member weighs the same (the P1 provisional stage B; kept for tests and fallbacks)."""
    return {m: 1.0 / len(members) for m in members}


def ensemble_matrix(
    probs: Mapping[str, NDArray[np.float64]],
    members: Sequence[str],
    target: str,
    weights: Mapping[str, float],
) -> NDArray[np.float64]:
    out = np.zeros_like(probs[f"{members[0]}.{target}"])
    for m in members:
        out += weights.get(m, 0.0) * probs[f"{m}.{target}"]
    result: NDArray[np.float64] = out / out.sum(axis=1, keepdims=True)
    return result


def floor_safety(p_pri: NDArray[np.float64], safety: NDArray[np.bool_]) -> NDArray[np.float64]:
    """`PriorityFinalizer`'s safety floor on a matrix: one-hot high where `safety`."""
    out = p_pri.copy()
    out[safety] = 0.0
    out[safety, HIGH] = 1.0
    return out


def text_member_oof(
    name: str,
    pool: Pool,
    emb: NDArray[np.float32],
    cfg: TrainCfg,
    kit: TrainingKit,
    folds: Folds,
    C: float,
    soft: bool,
) -> dict[str, NDArray[np.float64]]:
    """OOF probabilities of M1 or M2-LR at one `C`, both targets."""
    n = len(pool)
    out: dict[str, NDArray[np.float64]] = {
        t: np.zeros((n, len(target_labels(t))), dtype=np.float64) for t in TARGETS
    }
    for train_idx, test_idx in folds:
        tr, te = train_idx.tolist(), test_idx.tolist()
        for t in TARGETS:
            rows, labels, weights = expanded(kit, pool, t, tr, soft)
            model = fit_text_member(name, t, cfg, rows, labels, weights, pool, emb, C)
            out[t][test_idx] = predict_member(model, pool, te, emb)
    return out


def knn_oof(
    pool: Pool, emb: NDArray[np.float32], cfg: TrainCfg, folds: Folds, dim: int
) -> tuple[dict[str, NDArray[np.float64]], NDArray[np.float64]]:
    """OOF kNN probabilities (both targets) and the OOF max-similarity to the fold-train index."""
    n = len(pool)
    out: dict[str, NDArray[np.float64]] = {
        t: np.zeros((n, len(target_labels(t))), dtype=np.float64) for t in TARGETS
    }
    max_sim = np.zeros(n, dtype=np.float64)
    knn_cfg = cfg.section("knn")
    for train_idx, test_idx in folds:
        tr, te = train_idx.tolist(), test_idx.tolist()
        index = build_index(pool, tr, emb, dim)
        for t in TARGETS:
            out[t][test_idx] = predict_member(knn_member(t, index, knn_cfg), pool, te, emb)
        for i in te:
            max_sim[i] = index.max_similarity(emb[i].tolist())
    return out, max_sim


def proto_scores_oof(
    pool: Pool,
    emb: NDArray[np.float32],
    folds: Folds,
    office: PrototypeSet | None,
    parts: Sequence[str],
    mix: float,
) -> NDArray[np.float64]:
    """Raw (n, 6) prototype scores; learned prototypes come from each fold's training rows only."""
    scores = np.zeros((len(pool), len(CATEGORY_LABELS)), dtype=np.float64)
    for train_idx, test_idx in folds:
        sets = []
        if "learned" in parts:
            tr = train_idx.tolist()
            sets.append(
                learned_prototypes(emb[tr], [pool.category[i] for i in tr], [pool.scenario_id[i] for i in tr])
            )
        if "office" in parts and office is not None:
            sets.append(office)
        protos = PrototypeSet.concat(sets, emb.shape[1])
        scores[test_idx] = category_scores(emb[test_idx], protos, mix)
    return scores


def head_oof(
    ens_pri: NDArray[np.float64],
    evidence: Sequence[EvidenceVector],
    pool: Pool,
    kit: TrainingKit,
    folds: Folds,
    head_c: float,
    seed: int,
    soft: bool,
) -> NDArray[np.float64]:
    """OOF priority-head probabilities (temperature 1): per outer fold, a head fitted on the other folds'
    OOF ensemble priority vectors + evidence (stacking, never in-sample vectors)."""
    vectors = to_vectors(ens_pri, PRIORITY_LABELS)
    out = np.zeros((len(pool), len(PRIORITY_LABELS)), dtype=np.float64)
    for train_idx, test_idx in folds:
        rows, labels, weights = expanded(kit, pool, "priority", train_idx.tolist(), soft)
        head = LogisticPriorityHead(kit.features, head_c, seed)
        head.fit([vectors[i] for i in rows], [evidence[i] for i in rows], labels, weights)
        x = head.matrix([vectors[i] for i in test_idx], [evidence[i] for i in test_idx])
        out[test_idx] = to_matrix(head.predict_matrix(x), PRIORITY_LABELS)
    return out


# --- stage B selection ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Candidates:
    """Everything the selection needs, precomputed once per run."""

    text: Mapping[str, Mapping[float, Mapping[str, NDArray[np.float64]]]]  # member -> C -> target -> (n, L)
    knn: Mapping[str, NDArray[np.float64]]
    proto_scores: NDArray[np.float64] | None
    members: tuple[str, ...]
    y_cat: NDArray[np.int64]
    y_pri: NDArray[np.int64]
    safety: NDArray[np.bool_]


def _argmax_labels(p: NDArray[np.float64], labels: Sequence[str]) -> list[str]:
    return [labels[int(j)] for j in np.argmax(p, axis=1)]


def _f1(
    p: NDArray[np.float64], y_idx: NDArray[np.int64], mask: NDArray[np.bool_], labels: Sequence[str]
) -> float:
    gold = [labels[int(j)] for j in y_idx[mask]]
    return macro_f1(gold, _argmax_labels(p[mask], labels), labels)


class _Selector:
    """Runs the stage-B choices on a row mask (all official rows, or all but one fold for `nested`)."""

    def __init__(
        self,
        cand: _Candidates,
        pool: Pool,
        kit: TrainingKit,
        folds: Folds,
        cfg: TrainCfg,
        toggles: PipelineToggles,
        evidence: Sequence[EvidenceVector],
        fixed_C: tuple[float, float] | None,
    ) -> None:
        self.cand, self.pool, self.kit, self.folds, self.cfg = cand, pool, kit, folds, cfg
        self.toggles, self.evidence, self.fixed_C = toggles, evidence, fixed_C
        self.head_c = float(cfg.section("priority_head")["C"])
        self._head_cache: dict[tuple[tuple[str, float], ...], NDArray[np.float64]] = {}

    def member_probs(self, m1_C: float, m2lr_C: float, proto_t: float) -> dict[str, NDArray[np.float64]]:
        probs: dict[str, NDArray[np.float64]] = {}
        for m in self.cand.members:
            if m in TEXT_MEMBERS:
                c = m1_C if m == "m1" else m2lr_C
                for t in TARGETS:
                    probs[f"{m}.{t}"] = np.asarray(self.cand.text[m][c][t])
            elif m == "m2knn":
                for t in TARGETS:
                    probs[f"m2knn.{t}"] = np.asarray(self.cand.knn[t])
            elif m == PROTO and self.cand.proto_scores is not None:
                probs[f"{PROTO}.category"] = softmax(self.cand.proto_scores, proto_t)
                n = len(self.pool)
                probs[f"{PROTO}.priority"] = np.full((n, len(PRIORITY_LABELS)), 1.0 / len(PRIORITY_LABELS))
        return probs

    def head(
        self, probs: Mapping[str, NDArray[np.float64]], weights: Mapping[str, float]
    ) -> NDArray[np.float64]:
        pri_members = [m for m in self.cand.members if m not in CATEGORY_ONLY]
        key = tuple(sorted((m, round(weights.get(m, 0.0), 6)) for m in pri_members))
        if key not in self._head_cache:
            ens = ensemble_matrix(probs, pri_members, "priority", weights)
            self._head_cache[key] = head_oof(
                ens,
                self.evidence,
                self.pool,
                self.kit,
                self.folds,
                self.head_c,
                self.cfg.seed,
                self.toggles.soft_targets,
            )
        return self._head_cache[key]

    def select(
        self, mask: NDArray[np.bool_], cal_mask: NDArray[np.bool_] | None = None
    ) -> tuple[StageBChoices, dict[str, Any]]:
        """Stage-B choices on `mask` (official rows). The temperatures are calibrated on `cal_mask` (every
        OOF row, augmentation included: calibration wants the widest range of phrasing), default `mask`."""
        cand, cfg = self.cand, self.cfg
        cal = mask if cal_mask is None else cal_mask
        fixed = cfg.stage_b_mode == "fixed"
        trace: dict[str, Any] = {"mode": cfg.stage_b_mode}
        chosen_c: dict[str, float] = {}
        for m, grid in (("m1", cfg.m1_C_grid), ("m2lr", cfg.m2lr_C_grid)):
            if fixed and self.fixed_C is None:
                chosen_c[m] = cfg.fixed_C[0] if m == "m1" else cfg.fixed_C[1]
                continue
            if m not in cand.members:
                chosen_c[m] = cfg.m1_C if m == "m1" else cfg.m2lr_C
                continue
            if self.fixed_C is not None:
                chosen_c[m] = self.fixed_C[0] if m == "m1" else self.fixed_C[1]
                continue
            scores = {
                c: (
                    _f1(cand.text[m][c]["category"], cand.y_cat, mask, CATEGORY_LABELS),
                    _f1(cand.text[m][c]["priority"], cand.y_pri, mask, PRIORITY_LABELS),
                )
                for c in grid
            }
            chosen_c[m] = select_from_grid(scores, grid)
            trace[f"{m}_C"] = {str(c): [round(s, 4) for s in v] for c, v in scores.items()}
        proto_t = float(cfg.proto_temperature_grid[len(cfg.proto_temperature_grid) // 2])
        if cand.proto_scores is not None and PROTO in cand.members:
            sc = cand.proto_scores
            proto_t = best_temperature(
                lambda t: softmax(sc[cal], t), cand.y_cat[cal], cfg.proto_temperature_grid
            )
            trace["proto_temperature_nll"] = {
                str(t): round(nll(softmax(sc[cal], t), cand.y_cat[cal]), 4)
                for t in cfg.proto_temperature_grid
            }
        probs = self.member_probs(chosen_c["m1"], chosen_c["m2lr"], proto_t)
        cat = {m: probs[f"{m}.category"] for m in cand.members}
        y_cat_labels = [CATEGORY_LABELS[int(j)] for j in cand.y_cat]
        pri_members = [m for m in cand.members if m not in CATEGORY_ONLY]
        if fixed:
            w_cat = declared_weights(cfg.fixed_weights_category, cand.members)
            w_pri_all = declared_weights(cfg.fixed_weights_priority, cand.members, exclude=CATEGORY_ONLY)
            return self._temperatures(probs, chosen_c, proto_t, w_cat, w_pri_all, cal, trace)
        w_cat = simplex_weights(cat, y_cat_labels, cfg.weight_step, CATEGORY_LABELS, mask=mask)

        def pri_objective(w: Mapping[str, float]) -> float:
            final = floor_safety(self.head(probs, w), cand.safety)
            return _f1(final, cand.y_pri, mask, PRIORITY_LABELS)

        pri = {m: probs[f"{m}.priority"] for m in pri_members}
        y_pri_labels = [PRIORITY_LABELS[int(j)] for j in cand.y_pri]
        w_pri = simplex_weights(
            pri, y_pri_labels, cfg.weight_step, PRIORITY_LABELS, mask=mask, objective=pri_objective
        )
        w_pri_all = {m: w_pri.get(m, 0.0) for m in cand.members}
        return self._temperatures(probs, chosen_c, proto_t, w_cat, w_pri_all, cal, trace)

    def _temperatures(
        self,
        probs: Mapping[str, NDArray[np.float64]],
        chosen_c: Mapping[str, float],
        proto_t: float,
        w_cat: dict[str, float],
        w_pri: dict[str, float],
        cal: NDArray[np.bool_],
        trace: dict[str, Any],
    ) -> tuple[StageBChoices, dict[str, Any]]:
        cand, cfg = self.cand, self.cfg
        head_raw = self.head(probs, w_pri)

        def final(t: float) -> NDArray[np.float64]:
            return floor_safety(temperature_scale(head_raw, t), cand.safety)[cal]

        head_t = best_temperature(final, cand.y_pri[cal], cfg.head_temperature_grid)
        trace["head_temperature_nll"] = {
            str(t): round(nll(final(t), cand.y_pri[cal]), 4) for t in cfg.head_temperature_grid
        }
        choices = StageBChoices(chosen_c["m1"], chosen_c["m2lr"], float(proto_t), w_cat, w_pri, float(head_t))
        return choices, trace


def declared_weights(
    weights: Mapping[str, float], members: Sequence[str], exclude: frozenset[str] = frozenset()
) -> dict[str, float]:
    """Pre-declared weights (D-016) restricted to the present members and renormalized; members in `exclude`
    get 0. If no listed member is present (an ablation removed them all), the rest weigh the same."""
    keep = [m for m in members if m not in exclude]
    w = {m: float(weights.get(m, 0.0)) for m in keep}
    total = sum(w.values())
    w = {m: (v / total if total > 0 else 1.0 / len(keep)) for m, v in w.items()}
    return {m: w.get(m, 0.0) for m in members}


def _final_probs(sel: _Selector, ch: StageBChoices) -> dict[str, NDArray[np.float64]]:
    probs = sel.member_probs(ch.m1_C, ch.m2lr_C, ch.proto_temperature)
    members = list(sel.cand.members)
    probs["ensemble.category"] = ensemble_matrix(probs, members, "category", ch.weights_category)
    pri_members = [m for m in members if m not in CATEGORY_ONLY]
    probs["ensemble.priority"] = ensemble_matrix(probs, pri_members, "priority", ch.weights_priority)
    probs["head.priority"] = temperature_scale(sel.head(probs, ch.weights_priority), ch.head_temperature)
    probs["final.priority"] = floor_safety(probs["head.priority"], sel.cand.safety)
    return probs


def _nested(
    sel: _Selector,
    official: NDArray[np.bool_],
    fold: NDArray[np.int64],
    k: int,
    alpha: Mapping[str, float],
    method: str,
    groups: Sequence[str],
) -> dict[str, Any]:
    """Leave-one-fold-out selection: choose on the other folds' official rows, score the held-out fold."""
    n = len(sel.pool)
    cat_p = np.zeros((n, len(CATEGORY_LABELS)))
    pri_p = np.zeros((n, len(PRIORITY_LABELS)))
    covered: dict[str, NDArray[np.bool_]] = {t: np.zeros(n, dtype=bool) for t in TARGETS}
    size: dict[str, NDArray[np.float64]] = {t: np.zeros(n) for t in TARGETS}
    per_fold: list[dict[str, Any]] = []
    for f in range(k):
        held = fold == f
        ch, _ = sel.select(official & ~held, ~held)
        probs = _final_probs(sel, ch)
        cat_p[held] = probs["ensemble.category"][held]
        pri_p[held] = probs["final.priority"][held]
        calib = official & ~held
        for t, p, y in (
            ("category", probs["ensemble.category"], sel.cand.y_cat),
            ("priority", probs["final.priority"], sel.cand.y_pri),
        ):
            scores = 1.0 - p[np.arange(n), y]
            q = conformal_quantile(
                scores[calib], [g for g, c in zip(groups, calib, strict=True) if c], alpha[t], method
            )
            inside = p >= 1.0 - q - 1e-12
            empty = ~inside.any(axis=1)
            inside[empty, np.argmax(p[empty], axis=1)] = True
            covered[t][held] = inside[held][np.arange(int(held.sum())), y[held]]
            size[t][held] = inside[held].sum(axis=1)
        per_fold.append(
            {
                "fold": f,
                "m1_C": ch.m1_C,
                "m2lr_C": ch.m2lr_C,
                "weights_category": ch.weights_category,
                "weights_priority": ch.weights_priority,
                "proto_temperature": ch.proto_temperature,
                "head_temperature": ch.head_temperature,
            }
        )
    m = official
    return {
        "note": "selection repeated on 4 folds and applied to the 5th: the honest estimate of the tuned "
        "system",
        "category_macro_f1_oof_official": round(_f1(cat_p, sel.cand.y_cat, m, CATEGORY_LABELS), 4),
        "priority_macro_f1_oof_official": round(_f1(pri_p, sel.cand.y_pri, m, PRIORITY_LABELS), 4),
        "coverage_official": {t: round(float(covered[t][m].mean()), 4) for t in TARGETS},
        "mean_set_size_official": {t: round(float(size[t][m].mean()), 4) for t in TARGETS},
        "per_fold": per_fold,
    }


def run_cv(
    pool: Pool,
    encoder: SentenceEncoder,
    cfg: TrainCfg,
    toggles: PipelineToggles,
    kit: TrainingKit,
    *,
    nested: bool = True,
    fixed_C: tuple[float, float] | None = None,
    fast: bool = False,
) -> OOFResult:
    """Stage A over the frozen `cv_fold` folds plus the stage-B selections (module docstring).

    Args:
        nested: also compute the leave-one-fold-out estimates (the report's honest numbers).
        fixed_C: use these (m1, m2lr) `C` values instead of the grid search (ablation arms reuse the full
            model's choice so only the toggled part changes).
        fast: one `C` per member (the grid midpoint), for tests.

    Raises:
        InvalidInput: no member left after the toggles, or a fold problem (`group_folds`).
    """
    members = tuple(m for m in toggles.members if m in cfg.members)
    if not members:
        raise InvalidInput("no ensemble member left after the toggles")
    if PROTO in members and not toggles.proto_parts:
        members = tuple(m for m in members if m != PROTO)
    n = len(pool)
    emb = np.asarray(encoder.encode(list(pool.model_text)), dtype=np.float32).reshape(n, -1)
    folds = group_folds(pool, cfg.k)
    if fixed_C is None and cfg.stage_b_mode == "fixed":
        fixed_C = cfg.fixed_C  # D-016: pre-declared, no C grid
    if fast and fixed_C is None:
        fixed_C = (cfg.m1_C, cfg.m2lr_C)
    text: dict[str, dict[float, dict[str, NDArray[np.float64]]]] = {}
    for m in TEXT_MEMBERS:
        if m in members:
            grid = (
                (cfg.m1_C_grid if m == "m1" else cfg.m2lr_C_grid)
                if fixed_C is None
                else ((fixed_C[0],) if m == "m1" else (fixed_C[1],))
            )
            text[m] = {
                c: text_member_oof(m, pool, emb, cfg, kit, folds, c, toggles.soft_targets) for c in grid
            }
    knn_probs, max_sim = knn_oof(pool, emb, cfg, folds, encoder.dim)
    proto_cfg = cfg.section("prototype")
    scores = (
        proto_scores_oof(pool, emb, folds, kit.office, toggles.proto_parts, float(proto_cfg["mix"]))
        if PROTO in members
        else None
    )
    evidence, safety = evidence_and_safety(pool, kit, toggles.use_evidence)
    cand = _Candidates(
        text,
        knn_probs,
        scores,
        members,
        np.array([CATEGORY_LABELS.index(c) for c in pool.category], dtype=np.int64),
        np.array([PRIORITY_LABELS.index(p) for p in pool.priority], dtype=np.int64),
        safety,
    )
    sel = _Selector(cand, pool, kit, folds, cfg, toggles, evidence, fixed_C)
    official = np.asarray(pool.is_official, dtype=bool)
    choices, trace = sel.select(official, np.ones(len(pool), dtype=bool))
    probs = _final_probs(sel, choices)
    fold = np.asarray(pool.cv_fold, dtype=np.int64)
    nested_out: dict[str, Any] = {}
    if nested:
        alpha = {"category": cfg.alpha_category, "priority": cfg.alpha_priority}
        nested_out = _nested(sel, official, fold, cfg.k, alpha, cfg.conformal_calibration, pool.cv_group)
    if not math.isfinite(float(probs["final.priority"].sum())):
        raise InvalidInput("non-finite OOF probabilities")
    return OOFResult(
        probs=probs,
        max_sim=max_sim,
        fold=fold,
        safety=safety,
        evidence=evidence,
        embeddings=emb,
        pool=pool,
        members=members,
        choices=choices,
        proto_scores=scores,
        selection=trace,
        nested=nested_out,
        head_members=tuple(m for m in members if m not in CATEGORY_ONLY),
    )
