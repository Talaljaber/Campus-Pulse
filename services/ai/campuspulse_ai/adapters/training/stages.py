"""Stages B and C of `train.py` (P1.16, P2.7, ARCHITECTURE §3.4, §3.12) and the CV report.

- **Stage B (P2.7):** the OOF choices of `run_cv` (`m1.C`, `m2lr.C`, ensemble weights per target, the
  prototype and head temperatures; official OOF rows only, never our own test set); LAC quantiles from the
  OOF ensemble (category) and the OOF head + safety floor (priority), i.e. the vectors the core turns into
  sets, with the `conformal_calibration` rule (`group`: the pooled-CDF quantile over cv_groups); `tau_ood`
  from the OOF max-similarity; `tau_injection` and `tau_safety` by the zero-hit rule over the pool (LD-18);
  `human_review_maxprob` from OOF accuracy; priors from the pool; `tau_faq`/`tau_inc` copied from
  `config/hand_tuned.yaml` (LD-11).
- **Stage C:** refit M1 and M2-LR (at the chosen `C`) on 100 % of the pool, the prototypes from every row
  plus the embedded office descriptions, the `train` index from every distinct pool text, the head on the
  OOF ensemble priority vectors (stacking: never in-sample vectors), the exemplar collections, the lexicon
  snapshot (LD-12), `config.json`, `oof.npz`, `MANIFEST.json` and `CURRENT`.
- **`retune`:** recompute the stage-B values that depend only on OOF scores (conformal quantiles and
  `human_review_maxprob`) from a frozen `oof.npz`, for the config-only decisions of P2.10, without refitting
  any model. The pool hash in `oof.npz` must match the current pool (`ArtifactVersionMismatch`).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.artifacts.io import FileArtifactStore
from campuspulse_ai.adapters.guards.bank import load_texts
from campuspulse_ai.adapters.models.knn import TRAIN_COLLECTION, ExampleIndex
from campuspulse_ai.adapters.models.priority_head import LogisticPriorityHead
from campuspulse_ai.adapters.models.probs import to_vectors
from campuspulse_ai.adapters.models.prototype import NAME as PROTO
from campuspulse_ai.adapters.models.prototype import PrototypeClassifier, PrototypeSet, learned_prototypes
from campuspulse_ai.adapters.training.metrics import accuracy, coverage, macro_f1
from campuspulse_ai.adapters.training.oof import (
    CATEGORY_ONLY,
    TARGETS,
    TEXT_MEMBERS,
    OOFResult,
    TrainingKit,
    expanded,
    fit_text_member,
    index_entries,
)
from campuspulse_ai.adapters.training.pool import Pool
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.adapters.training.tuning import (
    conformal_quantile,
    human_review_maxprob,
    tau_from_zero_hits,
    tau_ood,
)
from campuspulse_ai.adapters.uncertainty.conformal import MONDRIAN_FILE, LACConformal, MondrianByLang
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.config.frozen import SCHEMA_VERSION, FrozenConfig
from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import SentenceEncoder
from campuspulse_ai.domain.values import Lang, Manifest, VectorItem

INJECTION_BANK = "injection_exemplars"
SAFETY_BANK = "safety_exemplars"
OOF_FILE = "oof.npz"
PROTOCOL = "scenario-held-out OOF over the frozen cv_fold folds (LD-31); metrics on official hard labels"
INCLUSION_TOLERANCE = 1e-12


@dataclass(frozen=True)
class EncoderInfo:
    """What `config.json encoder` records about the encoder used for training."""

    model_id: str
    revision: str
    runtime: str  # onnx_int8 | hashing
    files: tuple[Path, ...]  # encoder files to list in the manifest (none for hashing)


@dataclass(frozen=True)
class Tuned:
    """Stage-B outputs (all OOF-derived except the hand-tuned and copied values)."""

    weights_category: dict[str, float]
    weights_priority: dict[str, float]
    q_category: float
    q_priority: float
    n_calib: int
    n_groups: int
    tau_ood: float
    tau_injection: float
    tau_safety: float
    human_review_maxprob: float
    priors_category: dict[str, float]
    priors_priority: dict[str, float]
    oof_macro_f1_category: float
    oof_macro_f1_priority: float
    m1_C: float
    m2lr_C: float
    proto_temperature: float
    head_temperature: float
    q_category_by_lang: dict[str, float] = field(default_factory=dict)
    q_priority_by_lang: dict[str, float] = field(default_factory=dict)


def _argmax(matrix: NDArray[np.float64], labels: Sequence[str]) -> list[str]:
    return [labels[int(j)] for j in np.argmax(matrix, axis=1)]


def _official(oof: OOFResult) -> NDArray[np.bool_]:
    return np.asarray(oof.pool.is_official, dtype=bool)


def _max_exemplar_sim(texts: Sequence[str], exemplars: Sequence[str], encoder: SentenceEncoder) -> float:
    if not exemplars or not texts:
        return 0.0
    a = np.asarray(encoder.encode(list(dict.fromkeys(texts))), dtype=np.float64)
    b = np.asarray(encoder.encode(list(exemplars)), dtype=np.float64)
    return float((a @ b.T).max())


def exemplar_texts(lexicon_dir: Path) -> tuple[list[str], list[str]]:
    """(injection exemplars, distress exemplars) from the lexicon snapshot (LD-20, LD-27)."""
    return (
        load_texts(lexicon_dir / "injection.yaml", "exemplars"),
        load_texts(lexicon_dir / "safety.yaml", "exemplars.distress"),
    )


def pool_hash(pool: Pool) -> str:
    """sha256 over the rows that define the OOF arrays (id, model text, labels, group, fold)."""
    h = hashlib.sha256()
    for row in zip(
        pool.request_id,
        pool.model_text,
        pool.category,
        pool.priority,
        pool.cv_group,
        pool.cv_fold,
        strict=True,
    ):
        h.update("\x1f".join(map(str, row)).encode("utf-8") + b"\x1e")
    return h.hexdigest()


def quantiles(
    p_cat: NDArray[np.float64],
    p_pri: NDArray[np.float64],
    y_cat: Sequence[str],
    y_pri: Sequence[str],
    groups: Sequence[str],
    cfg: TrainCfg,
) -> tuple[float, float]:
    """(q_category, q_priority) with the configured calibration rule (LAC scores 1 - p(true label))."""
    out = []
    for p, y, labels, alpha in (
        (p_cat, y_cat, CATEGORY_LABELS, cfg.alpha_category),
        (p_pri, y_pri, PRIORITY_LABELS, cfg.alpha_priority),
    ):
        idx = np.array([labels.index(v) for v in y], dtype=np.int64)
        scores = 1.0 - p[np.arange(len(idx)), idx]
        out.append(conformal_quantile(scores, groups, alpha, cfg.conformal_calibration))
    return out[0], out[1]


def quantiles_by_lang(
    p_cat: NDArray[np.float64],
    p_pri: NDArray[np.float64],
    y_cat: Sequence[str],
    y_pri: Sequence[str],
    groups: Sequence[str],
    langs: Sequence[str],
    cfg: TrainCfg,
) -> tuple[dict[str, float], dict[str, float]]:
    """Per-language quantiles for the `mondrian.targets` when `conformal.mondrian_by_lang` is on (P2.10):
    the same rule as `quantiles` on each language's rows, for languages with at least `mondrian.min_groups`
    calibration groups (the others use the global q). Empty dicts when Mondrian is off."""
    if not bool(cfg.section("conformal")["mondrian_by_lang"]):
        return {}, {}
    mond = cfg.section("mondrian")
    targets, min_groups = set(mond["targets"]), int(mond["min_groups"])
    lang_arr = np.asarray([str(x) for x in langs])
    out: list[dict[str, float]] = []
    for target, p, y, labels, alpha in (
        ("category", p_cat, y_cat, CATEGORY_LABELS, cfg.alpha_category),
        ("priority", p_pri, y_pri, PRIORITY_LABELS, cfg.alpha_priority),
    ):
        per: dict[str, float] = {}
        if target in targets:
            idx = np.array([labels.index(v) for v in y], dtype=np.int64)
            scores = 1.0 - p[np.arange(len(idx)), idx]
            for lang in sorted(set(lang_arr.tolist())):
                rows = np.nonzero(lang_arr == lang)[0]
                g = [groups[int(i)] for i in rows]
                if len(set(g)) >= min_groups:
                    per[lang] = conformal_quantile(scores[rows], g, alpha, cfg.conformal_calibration)
        out.append(per)
    return out[0], out[1]


def stage_b(oof: OOFResult, cfg: TrainCfg, encoder: SentenceEncoder, lexicon_dir: Path) -> Tuned:
    """Stage B (module docstring): the OOF choices plus the OOF-score thresholds."""
    pool = oof.pool
    q_cat, q_pri = quantiles(
        oof.probs["ensemble.category"],
        oof.probs["final.priority"],
        pool.category,
        pool.priority,
        pool.cv_group,
        cfg,
    )
    q_cat_lang, q_pri_lang = quantiles_by_lang(
        oof.probs["ensemble.category"],
        oof.probs["final.priority"],
        pool.category,
        pool.priority,
        pool.cv_group,
        [str(x) for x in pool.lang],
        cfg,
    )
    injection, distress = exemplar_texts(lexicon_dir)
    texts = list(pool.model_text)
    cat_pred = _argmax(oof.probs["ensemble.category"], CATEGORY_LABELS)
    maxprob = oof.probs["ensemble.category"].max(axis=1)
    correct = np.array([a == b for a, b in zip(cat_pred, pool.category, strict=True)])
    official = _official(oof)
    y_cat = [c for c, o in zip(pool.category, official, strict=True) if o]
    y_pri = [p for p, o in zip(pool.priority, official, strict=True) if o]
    pri_pred = _argmax(oof.probs["final.priority"], PRIORITY_LABELS)
    ch = oof.choices
    return Tuned(
        weights_category=dict(ch.weights_category),
        weights_priority=dict(ch.weights_priority),
        q_category=q_cat,
        q_priority=q_pri,
        n_calib=len(pool),
        n_groups=len(set(pool.cv_group)),
        tau_ood=tau_ood(oof.max_sim, cfg.tau_ood_percentile),
        tau_injection=tau_from_zero_hits(
            np.array([_max_exemplar_sim(texts, injection, encoder)]), cfg.tau_margin
        ),
        tau_safety=tau_from_zero_hits(
            np.array([_max_exemplar_sim(texts, distress, encoder)]), cfg.tau_margin
        ),
        human_review_maxprob=human_review_maxprob(maxprob, correct, cfg.human_review_min_acc),
        priors_category=_frequencies(pool.category, CATEGORY_LABELS),
        priors_priority=_frequencies(pool.priority, PRIORITY_LABELS),
        oof_macro_f1_category=macro_f1(
            y_cat, [p for p, o in zip(cat_pred, official, strict=True) if o], CATEGORY_LABELS
        ),
        oof_macro_f1_priority=macro_f1(
            y_pri, [p for p, o in zip(pri_pred, official, strict=True) if o], PRIORITY_LABELS
        ),
        m1_C=ch.m1_C,
        m2lr_C=ch.m2lr_C,
        proto_temperature=ch.proto_temperature,
        head_temperature=ch.head_temperature,
        q_category_by_lang=q_cat_lang,
        q_priority_by_lang=q_pri_lang,
    )


def _frequencies(labels: Sequence[str], order: Sequence[str]) -> dict[str, float]:
    counts = Counter(labels)
    total = sum(counts.values())
    return {lab: counts.get(lab, 0) / total for lab in order}


# --- the CV report (reports/cv_p2.json) --------------------------------------------------------------


def _slice_metrics(
    y: Sequence[str], yhat: Sequence[str], labels: Sequence[str], mask: NDArray[np.bool_]
) -> dict[str, float]:
    ys = [a for a, m in zip(y, mask, strict=True) if m]
    ps = [b for b, m in zip(yhat, mask, strict=True) if m]
    return {"macro_f1": round(macro_f1(ys, ps, labels), 4), "accuracy": round(accuracy(ys, ps), 4)}


def cv_report(oof: OOFResult, tuned: Tuned, cfg: TrainCfg) -> dict[str, Any]:
    """The CV report mapping: P1.16 keys plus slices, counts, conformal OOF coverage, the stage-B choices
    with their grid scores, and the leave-one-fold-out (`nested`) estimates."""
    pool = oof.pool
    official = _official(oof)
    everything = np.ones(len(pool), dtype=bool)
    groups = np.asarray(pool.cv_group)

    def counts(mask: NDArray[np.bool_]) -> dict[str, int]:
        return {
            "rows": int(mask.sum()),
            "groups": len(set(groups[mask].tolist())),
            "distinct_texts": len({t for t, m in zip(pool.model_text, mask, strict=True) if m}),
        }

    cat_pred = {
        key: _argmax(oof.probs[key], CATEGORY_LABELS)
        for key in [f"{m}.category" for m in oof.members] + ["ensemble.category"]
    }
    pri_pred = {
        key: _argmax(oof.probs[key], PRIORITY_LABELS)
        for key in [f"{m}.priority" for m in oof.members if m not in CATEGORY_ONLY]
        + ["ensemble.priority", "head.priority", "final.priority"]
    }
    cat_final, pri_final = cat_pred["ensemble.category"], pri_pred["final.priority"]
    joint = np.array(
        [
            a == b and c == d
            for a, b, c, d in zip(pool.category, cat_final, pool.priority, pri_final, strict=True)
        ]
    )
    by_lang = {}
    for lang in sorted(set(pool.lang_script)):
        mask = official & (np.asarray(pool.lang_script) == lang)
        by_lang[lang] = {
            "counts": counts(mask),
            "category": _slice_metrics(pool.category, cat_final, CATEGORY_LABELS, mask),
            "priority": _slice_metrics(pool.priority, pri_final, PRIORITY_LABELS, mask),
            "joint_accuracy": round(float(joint[mask].mean()), 4) if mask.any() else 0.0,
        }
    sets_cat = [
        LACConformal.from_quantile(
            "category", cfg.alpha_category, tuned.q_category, tuned.n_calib
        ).predict_set(p)
        for p in to_vectors(oof.probs["ensemble.category"], CATEGORY_LABELS)
    ]
    sets_pri = [
        LACConformal.from_quantile(
            "priority", cfg.alpha_priority, tuned.q_priority, tuned.n_calib
        ).predict_set(p)
        for p in to_vectors(oof.probs["final.priority"], PRIORITY_LABELS)
    ]
    cov_cat, cov_pri = coverage(sets_cat, pool.category), coverage(sets_pri, pool.priority)
    ask = float(np.mean([a.size == 2 or b.size == 2 for a, b in zip(sets_cat, sets_pri, strict=True)]))
    return {
        "protocol": PROTOCOL,
        "artifact_version": cfg.artifact_version,
        "k": cfg.k,
        "members": list(oof.members),
        "stage_b": "tuned on official OOF rows only (P2.7); nested = leave-one-fold-out selection",
        "choices": {**oof.choices.as_dict(), "conformal_calibration": cfg.conformal_calibration},
        "selection": dict(oof.selection),
        "nested": dict(oof.nested),
        "counts": {"official": counts(official), "all": counts(everything)},
        "category": {
            "macro_f1_oof_official": round(tuned.oof_macro_f1_category, 4),
            "macro_f1_oof_all": _slice_metrics(pool.category, cat_final, CATEGORY_LABELS, everything)[
                "macro_f1"
            ],
            "accuracy_oof_official": _slice_metrics(pool.category, cat_final, CATEGORY_LABELS, official)[
                "accuracy"
            ],
            "per_member": {
                key.split(".")[0]: _slice_metrics(pool.category, pred, CATEGORY_LABELS, official)
                for key, pred in cat_pred.items()
            },
        },
        "priority": {
            "macro_f1_model_oof_official": _slice_metrics(
                pool.priority, pri_pred["ensemble.priority"], PRIORITY_LABELS, official
            )["macro_f1"],
            "macro_f1_head_oof_official": _slice_metrics(
                pool.priority, pri_pred["head.priority"], PRIORITY_LABELS, official
            )["macro_f1"],
            "macro_f1_oof_official": round(tuned.oof_macro_f1_priority, 4),
            "macro_f1_oof_all": _slice_metrics(pool.priority, pri_final, PRIORITY_LABELS, everything)[
                "macro_f1"
            ],
            "accuracy_oof_official": _slice_metrics(pool.priority, pri_final, PRIORITY_LABELS, official)[
                "accuracy"
            ],
            "per_member": {
                key.split(".")[0]: _slice_metrics(pool.priority, pred, PRIORITY_LABELS, official)
                for key, pred in pri_pred.items()
            },
        },
        "joint_accuracy_oof_official": round(float(joint[official].mean()), 4),
        "by_lang_script_official": by_lang,
        "conformal_oof": {
            "note": "quantile calibrated on these same OOF scores (in-sample for q); see nested for the "
            "leave-one-fold-out coverage. Approximate: effective n ~ groups",
            "calibration": cfg.conformal_calibration,
            "category": {
                "q": round(tuned.q_category, 6),
                "coverage": round(cov_cat.coverage, 4),
                "mean_size": round(cov_cat.mean_size, 4),
                "n": cov_cat.n,
            },
            "priority": {
                "q": round(tuned.q_priority, 6),
                "coverage": round(cov_pri.coverage, 4),
                "mean_size": round(cov_pri.mean_size, 4),
                "n": cov_pri.n,
            },
            "n_groups": tuned.n_groups,
            "ask_proxy_rate": round(ask, 4),
        },
        "thresholds": {
            "tau_ood": round(tuned.tau_ood, 6),
            "tau_injection": round(tuned.tau_injection, 6),
            "tau_safety": round(tuned.tau_safety, 6),
            "human_review_maxprob": round(tuned.human_review_maxprob, 6),
        },
        "safety_floor_rows": int(oof.safety.sum()),
    }


# --- stage C: freeze ---------------------------------------------------------------------------------


def build_config(
    cfg: TrainCfg,
    tuned: Tuned,
    enc: EncoderInfo,
    members: Sequence[str],
    trained_at: str,
    proto_parts: Sequence[str] | None = None,
) -> FrozenConfig:
    """Assemble and validate `config.json` (the only writer is `train.py`, §1.6)."""
    encoder = cfg.section("encoder")
    encoder.update({"model_id": enc.model_id, "revision": enc.revision, "runtime": enc.runtime})
    m1 = cfg.section("m1")
    cv = cfg.section("cv")
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": cfg.artifact_version,
        "trained_at": trained_at,
        "seed": cfg.seed,
        "encoder": encoder,
        "ensemble": {
            "members": list(members),
            "weights_category": {m: tuned.weights_category[m] for m in members},
            "weights_priority": {m: tuned.weights_priority.get(m, 0.0) for m in members},
            "memory_weight_category": float(cfg.section("ensemble").get("memory_weight_category", 0.0)),
        },
        "m1": {"char_ngram": m1["char_ngram"], "word_ngram": m1["word_ngram"], "C": tuned.m1_C},
        "m2lr": {"C": tuned.m2lr_C},
        "knn": cfg.section("knn"),
        "priority_head": {**cfg.section("priority_head"), "temperature": tuned.head_temperature},
        "conformal": {
            **cfg.section("conformal"),
            "alpha_category": cfg.alpha_category,
            "alpha_priority": cfg.alpha_priority,
            "q_category": tuned.q_category,
            "q_priority": tuned.q_priority,
            "n_calib": tuned.n_calib,
            "calibration": cfg.conformal_calibration,
            "q_category_by_lang": dict(tuned.q_category_by_lang),
            "q_priority_by_lang": dict(tuned.q_priority_by_lang),
        },
        "thresholds": {
            "tau_ood": tuned.tau_ood,
            "tau_faq": cfg.hand_tuned["tau_faq"],
            "tau_inc": cfg.hand_tuned["tau_inc"],
            "tau_injection": tuned.tau_injection,
            "tau_safety": tuned.tau_safety,
            "human_review_maxprob": tuned.human_review_maxprob,
        },
        "guards": cfg.section("guards"),
        "llm": cfg.section("llm"),
        "explain": cfg.section("explain"),
        "priors": {"category": tuned.priors_category, "priority": tuned.priors_priority},
        "cv": {
            "k": cfg.k,
            "group_col": cv["group_col"],
            "fold_col": cv["fold_col"],
            "folds_file": cv["folds_file"],
            "oof_macro_f1_category": tuned.oof_macro_f1_category,
            "oof_macro_f1_priority": tuned.oof_macro_f1_priority,
        },
    }
    if PROTO in members:
        proto = cfg.section("prototype")
        data["prototype"] = {
            "parts": list(proto_parts if proto_parts is not None else proto["parts"]),
            "mix": float(proto["mix"]),
            "temperature": tuned.proto_temperature,
        }
    return FrozenConfig.from_dict(data, source="train.py")


def save_oof(path: Path, oof: OOFResult) -> None:
    pool = oof.pool
    arrays: dict[str, NDArray[Any]] = {k.replace(".", "__"): v for k, v in oof.probs.items()}
    arrays.update(
        {
            "request_id": np.asarray(pool.request_id, dtype=str),
            "cv_group": np.asarray(pool.cv_group, dtype=str),
            "category": np.asarray(pool.category, dtype=str),
            "priority": np.asarray(pool.priority, dtype=str),
            "lang": np.asarray([str(x) for x in pool.lang], dtype=str),
            "lang_script": np.asarray(pool.lang_script, dtype=str),
            "is_official": np.asarray(pool.is_official, dtype=bool),
            "fold": oof.fold,
            "max_sim": oof.max_sim,
            "safety": oof.safety,
            "pool_hash": np.asarray(pool_hash(pool)),
            "choices": np.asarray(json.dumps(oof.choices.as_dict(), sort_keys=True)),
        }
    )
    if oof.proto_scores is not None:
        arrays["m2proto__scores"] = oof.proto_scores
    np.savez_compressed(path, **arrays)  # type: ignore[arg-type]


def freeze(
    out: Path,
    oof: OOFResult,
    tuned: Tuned,
    cfg: TrainCfg,
    kit: TrainingKit,
    encoder: SentenceEncoder,
    enc: EncoderInfo,
    lexicon_dir: Path,
    *,
    now: datetime | None = None,
) -> tuple[FrozenConfig, Manifest]:
    """Stage C: write the frozen model directory `out` (module docstring). Returns (config, manifest)."""
    pool, emb = oof.pool, oof.embeddings
    out.mkdir(parents=True, exist_ok=True)
    for stale in (out / PROTO,):  # a member dropped since the last freeze must not linger in the dir
        if stale.exists() and PROTO not in oof.members:
            shutil.rmtree(stale)
    written: list[Path] = []
    all_rows = list(range(len(pool)))
    for t in TARGETS:
        rows, labels, weights = expanded(kit, pool, t, all_rows, soft=True)
        for m in oof.members:
            if m not in TEXT_MEMBERS:
                continue
            c = tuned.m1_C if m == "m1" else tuned.m2lr_C
            model = fit_text_member(m, t, cfg, rows, labels, weights, pool, emb, c)
            model.save(out / m / t)
            written += sorted(p for p in (out / m / t).iterdir() if p.is_file())
    if PROTO in oof.members:
        proto_cfg = cfg.section("prototype")
        sets = []
        if "learned" in oof.proto_parts:
            sets.append(learned_prototypes(emb, list(pool.category), list(pool.scenario_id)))
        if "office" in oof.proto_parts and kit.office is not None:
            sets.append(kit.office)
        protos = PrototypeSet.concat(sets, encoder.dim)
        for t in TARGETS:
            member = PrototypeClassifier(
                t, protos if t == "category" else None, tuned.proto_temperature, float(proto_cfg["mix"])
            )
            member.save(out / PROTO / t)
            written += sorted(p for p in (out / PROTO / t).iterdir() if p.is_file())
    head = LogisticPriorityHead(kit.features, float(cfg.section("priority_head")["C"]), cfg.seed)
    ens_pri = to_vectors(oof.probs["ensemble.priority"], PRIORITY_LABELS)
    rows, labels, weights = expanded(kit, pool, "priority", all_rows, soft=True)
    head.fit([ens_pri[i] for i in rows], [oof.evidence[i] for i in rows], labels, weights)
    head.temperature = tuned.head_temperature
    head.save(out / "head")
    written += sorted(p for p in (out / "head").iterdir() if p.is_file())

    store = LocalNumpyVectorStore(encoder.dim)
    ExampleIndex(store, TRAIN_COLLECTION).add(index_entries(pool, all_rows, emb))
    injection, distress = exemplar_texts(lexicon_dir)
    for bank, texts in ((INJECTION_BANK, injection), (SAFETY_BANK, distress)):
        vectors = encoder.encode(texts)
        store.upsert(
            bank,
            [
                VectorItem(
                    id=f"{bank}-{i:03d}", embedding=tuple(v), text=t, lang=Lang.EN, meta={"bank": bank}
                )
                for i, (t, v) in enumerate(zip(texts, vectors, strict=True))
            ],
        )
    index_dir = out / "index"
    if index_dir.exists():
        shutil.rmtree(index_dir)
    written += store.save(index_dir)
    written += _write_conformal(out, cfg, tuned)

    snapshot = out / "lexicons"
    snapshot.mkdir(exist_ok=True)
    for src in sorted(lexicon_dir.glob("*.yaml")):
        dst = snapshot / src.name
        dst.write_bytes(src.read_bytes())
        written.append(dst)

    trained_at = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    config = build_config(cfg, tuned, enc, oof.members, trained_at, oof.proto_parts)
    config.save(out / "config.json")
    save_oof(out / OOF_FILE, oof)
    written += [out / "config.json", out / OOF_FILE, *enc.files]
    manifest = FileArtifactStore().write_manifest(out, written)
    with (out.parent / "CURRENT").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(out.name + "\n")
    return config, manifest


def write_conformal(
    out: Path,
    alphas: tuple[float, float],
    qs: tuple[float, float],
    by_lang: tuple[dict[str, float], dict[str, float]],
    n_calib: int,
    n_groups: int,
) -> list[Path]:
    """`conformal/<target>/conformal.json` (+ `mondrian.json` when per-language quantiles exist)."""
    paths = []
    for target, q, alpha, per in zip(("category", "priority"), qs, alphas, by_lang, strict=True):
        lac = LACConformal.from_quantile(target, alpha, q, n_calib, n_groups)  # type: ignore[arg-type]
        directory = out / "conformal" / target
        stale = directory / MONDRIAN_FILE
        if stale.exists() and not per:
            stale.unlink()
        if per:
            inner = {
                lang: LACConformal.from_quantile(target, alpha, v, n_calib, n_groups)  # type: ignore[arg-type]
                for lang, v in per.items()
            }
            MondrianByLang(inner, lac).save(directory)
            paths.append(directory / MONDRIAN_FILE)
        else:
            lac.save(directory)
        paths.append(directory / "conformal.json")
    return paths


def _write_conformal(out: Path, cfg: TrainCfg, tuned: Tuned) -> list[Path]:
    return write_conformal(
        out,
        (cfg.alpha_category, cfg.alpha_priority),
        (tuned.q_category, tuned.q_priority),
        (tuned.q_category_by_lang, tuned.q_priority_by_lang),
        tuned.n_calib,
        tuned.n_groups,
    )


# --- retune: stage-B values from a frozen oof.npz (P2.7 / P2.10) ----------------------------------------


RETUNE_KEYS = (
    "conformal.alpha_category",
    "conformal.alpha_priority",
    "conformal.q_category",
    "conformal.q_priority",
    "conformal.calibration",
    "conformal.mondrian_by_lang",
    "conformal.q_category_by_lang",
    "conformal.q_priority_by_lang",
    "thresholds.human_review_maxprob",
)


def retune(
    model_dir: Path, cfg: TrainCfg, current_pool: Pool, *, now: datetime | None = None
) -> tuple[FrozenConfig, Manifest, dict[str, tuple[Any, Any]]]:
    """Recompute the OOF-score stage-B keys (`RETUNE_KEYS`) from `model_dir/oof.npz` and rewrite
    `config.json`, the conformal files and `MANIFEST.json`. No model is refitted.

    Returns (config, manifest, {key: (old, new)} for the keys that changed).

    Raises:
        ArtifactMissing: no `oof.npz` or `config.json`.
        ArtifactVersionMismatch: `oof.npz` was computed on another pool (hash mismatch).
    """
    path = model_dir / OOF_FILE
    if not path.is_file():
        raise ArtifactMissing(f"{path} not found; run train.py without --retune first")
    z = np.load(path, allow_pickle=False)
    if "pool_hash" not in z.files or str(z["pool_hash"]) != pool_hash(current_pool):
        raise ArtifactVersionMismatch(f"{path} comes from another training pool; retrain instead of --retune")
    old = FrozenConfig.load(model_dir / "config.json")
    groups = [str(g) for g in z["cv_group"]]
    y_cat, y_pri = [str(v) for v in z["category"]], [str(v) for v in z["priority"]]
    q_cat, q_pri = quantiles(z["ensemble__category"], z["final__priority"], y_cat, y_pri, groups, cfg)
    by_lang = quantiles_by_lang(
        z["ensemble__category"], z["final__priority"], y_cat, y_pri, groups, [str(v) for v in z["lang"]], cfg
    )
    p_cat = z["ensemble__category"]
    pred = _argmax(p_cat, CATEGORY_LABELS)
    correct = np.array([a == b for a, b in zip(pred, y_cat, strict=True)])
    hr = human_review_maxprob(p_cat.max(axis=1), correct, cfg.human_review_min_acc)
    data = json.loads(old.to_json())
    data["conformal"].update(
        {
            "alpha_category": cfg.alpha_category,
            "alpha_priority": cfg.alpha_priority,
            "q_category": q_cat,
            "q_priority": q_pri,
            "calibration": cfg.conformal_calibration,
            "mondrian_by_lang": bool(cfg.section("conformal")["mondrian_by_lang"]),
            "q_category_by_lang": by_lang[0],
            "q_priority_by_lang": by_lang[1],
        }
    )
    data["thresholds"]["human_review_maxprob"] = hr
    data["trained_at"] = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    config = FrozenConfig.from_dict(data, source="train.py --retune")
    changed = _changed(json.loads(old.to_json()), data)
    config.save(model_dir / "config.json")
    conformal_files = write_conformal(
        model_dir,
        (cfg.alpha_category, cfg.alpha_priority),
        (q_cat, q_pri),
        by_lang,
        old.conformal.n_calib,
        len(set(groups)),
    )
    # the old manifest is read for its file list only: config.json and the conformal files just changed
    listed = json.loads((model_dir / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
    keep = {model_dir / rel for rel in listed if (model_dir / rel).is_file()} | set(conformal_files)
    manifest = FileArtifactStore().write_manifest(model_dir, sorted(keep))
    return config, manifest, changed


def _changed(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, tuple[Any, Any]]:
    out: dict[str, tuple[Any, Any]] = {}
    for key in RETUNE_KEYS:
        section, name = key.split(".")
        a, b = old.get(section, {}).get(name), new.get(section, {}).get(name)
        if a != b:
            out[key] = (a, b)
    return out
