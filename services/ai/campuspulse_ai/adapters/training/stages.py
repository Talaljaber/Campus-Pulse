"""Stages B and C of `train.py` (P1.16, ARCHITECTURE §3.4, §3.12) and the CV report.

- **Stage B (provisional, P1):** equal ensemble weights and `C` at the grid midpoint (P2.7 tunes both on
  OOF); LAC quantiles from the OOF ensemble (category) and the OOF head + safety floor (priority), i.e. the
  vectors the core actually turns into sets; `tau_ood` from the OOF max-similarity; `tau_injection` and
  `tau_safety` by the zero-hit rule over the pool (LD-18); `human_review_maxprob` from OOF accuracy; priors
  from the pool; `tau_faq`/`tau_inc` copied from `config/hand_tuned.yaml` (LD-11).
- **Stage C:** refit M1 and M2-LR on 100 % of the pool, the `train` index from every distinct pool text, the
  head on the OOF ensemble priority vectors (stacking: never in-sample vectors), the exemplar collections,
  the lexicon snapshot (LD-12), `config.json`, `oof.npz`, `MANIFEST.json` and `CURRENT`.
"""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
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
from campuspulse_ai.adapters.training.metrics import accuracy, coverage, macro_f1
from campuspulse_ai.adapters.training.oof import (
    TARGETS,
    OOFResult,
    TrainingKit,
    equal_weights,
    expanded,
    fit_text_member,
    index_entries,
)
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.adapters.training.tuning import human_review_maxprob, tau_from_zero_hits, tau_ood
from campuspulse_ai.adapters.uncertainty.conformal import LACConformal
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.config.frozen import SCHEMA_VERSION, FrozenConfig
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import SentenceEncoder
from campuspulse_ai.domain.values import Lang, Manifest, VectorItem

INJECTION_BANK = "injection_exemplars"
SAFETY_BANK = "safety_exemplars"
OOF_FILE = "oof.npz"
PROTOCOL = "scenario-held-out OOF over the frozen cv_fold folds (LD-31); metrics on official hard labels"


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


def stage_b(oof: OOFResult, cfg: TrainCfg, encoder: SentenceEncoder, lexicon_dir: Path) -> Tuned:
    """Provisional stage B (module docstring)."""
    pool = oof.pool
    p_cat = to_vectors(oof.probs["ensemble.category"], CATEGORY_LABELS)
    p_pri = to_vectors(oof.probs["final.priority"], PRIORITY_LABELS)
    lac_cat = LACConformal("category", cfg.alpha_category)
    lac_cat.calibrate(p_cat, pool.category, pool.cv_group)
    lac_pri = LACConformal("priority", cfg.alpha_priority)
    lac_pri.calibrate(p_pri, pool.priority, pool.cv_group)
    injection, distress = exemplar_texts(lexicon_dir)
    texts = list(pool.model_text)
    cat_pred = _argmax(oof.probs["ensemble.category"], CATEGORY_LABELS)
    maxprob = oof.probs["ensemble.category"].max(axis=1)
    correct = np.array([a == b for a, b in zip(cat_pred, pool.category, strict=True)])
    official = _official(oof)
    y_cat = [c for c, o in zip(pool.category, official, strict=True) if o]
    y_pri = [p for p, o in zip(pool.priority, official, strict=True) if o]
    pri_pred = _argmax(oof.probs["final.priority"], PRIORITY_LABELS)
    weights = equal_weights(oof.members)
    return Tuned(
        weights_category=weights,
        weights_priority=dict(weights),
        q_category=lac_cat.q,
        q_priority=lac_pri.q,
        n_calib=lac_cat.n_calib,
        n_groups=lac_cat.n_groups,
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
    )


def _frequencies(labels: Sequence[str], order: Sequence[str]) -> dict[str, float]:
    counts = Counter(labels)
    total = sum(counts.values())
    return {lab: counts.get(lab, 0) / total for lab in order}


# --- the CV report (reports/cv_p1.json) --------------------------------------------------------------


def _slice_metrics(
    y: Sequence[str], yhat: Sequence[str], labels: Sequence[str], mask: NDArray[np.bool_]
) -> dict[str, float]:
    ys = [a for a, m in zip(y, mask, strict=True) if m]
    ps = [b for b, m in zip(yhat, mask, strict=True) if m]
    return {"macro_f1": round(macro_f1(ys, ps, labels), 4), "accuracy": round(accuracy(ys, ps), 4)}


def cv_report(oof: OOFResult, tuned: Tuned, cfg: TrainCfg) -> dict[str, Any]:
    """The `reports/cv_p1.json` mapping (P1.16 keys plus slices, counts and conformal OOF coverage)."""
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
        for key in [f"{m}.priority" for m in oof.members]
        + ["ensemble.priority", "head.priority", "final.priority"]
    }
    cat_final, pri_final = cat_pred["ensemble.category"], pri_pred["final.priority"]
    joint = np.array(
        [
            a == b and c == d
            for a, b, c, d in zip(pool.category, cat_final, pool.priority, pri_final, strict=True)
        ]
    )
    langs = sorted(set(pool.lang_script))
    by_lang = {}
    for lang in langs:
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
        "stage_b": "provisional: equal weights, C = grid midpoint (P2.7 tunes on OOF)",
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
            "note": "quantile calibrated on these same OOF scores; approximate, effective n ~ groups",
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
    cfg: TrainCfg, tuned: Tuned, enc: EncoderInfo, members: Sequence[str], trained_at: str
) -> FrozenConfig:
    """Assemble and validate `config.json` (the only writer is `train.py`, §1.6)."""
    encoder = cfg.section("encoder")
    encoder.update({"model_id": enc.model_id, "revision": enc.revision, "runtime": enc.runtime})
    m1 = cfg.section("m1")
    cv = cfg.section("cv")
    data = {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": cfg.artifact_version,
        "trained_at": trained_at,
        "seed": cfg.seed,
        "encoder": encoder,
        "ensemble": {
            "members": list(members),
            "weights_category": tuned.weights_category,
            "weights_priority": tuned.weights_priority,
        },
        "m1": {"char_ngram": m1["char_ngram"], "word_ngram": m1["word_ngram"], "C": cfg.m1_C},
        "m2lr": {"C": cfg.m2lr_C},
        "knn": cfg.section("knn"),
        "priority_head": cfg.section("priority_head"),
        "conformal": {
            **cfg.section("conformal"),
            "alpha_category": cfg.alpha_category,
            "alpha_priority": cfg.alpha_priority,
            "q_category": tuned.q_category,
            "q_priority": tuned.q_priority,
            "n_calib": tuned.n_calib,
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
        }
    )
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
    written: list[Path] = []
    all_rows = list(range(len(pool)))
    for t in TARGETS:
        rows, labels, weights = expanded(kit, pool, t, all_rows, soft=True)
        for m in oof.members:
            if m == "m2knn":
                continue
            model = fit_text_member(m, t, cfg, rows, labels, weights, pool, emb)
            model.save(out / m / t)
            written += sorted(p for p in (out / m / t).iterdir() if p.is_file())
    head = LogisticPriorityHead(kit.features, float(cfg.section("priority_head")["C"]), cfg.seed)
    ens_pri = to_vectors(oof.probs["ensemble.priority"], PRIORITY_LABELS)
    rows, labels, weights = expanded(kit, pool, "priority", all_rows, soft=True)
    head.fit([ens_pri[i] for i in rows], [oof.evidence[i] for i in rows], labels, weights)
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

    for target, q, alpha in (
        ("category", tuned.q_category, cfg.alpha_category),
        ("priority", tuned.q_priority, cfg.alpha_priority),
    ):
        lac = LACConformal.from_quantile(target, alpha, q, tuned.n_calib, tuned.n_groups)  # type: ignore[arg-type]
        lac.save(out / "conformal" / target)
        written.append(out / "conformal" / target / "conformal.json")

    snapshot = out / "lexicons"
    snapshot.mkdir(exist_ok=True)
    for src in sorted(lexicon_dir.glob("*.yaml")):
        dst = snapshot / src.name
        dst.write_bytes(src.read_bytes())
        written.append(dst)

    trained_at = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    config = build_config(cfg, tuned, enc, oof.members, trained_at)
    config.save(out / "config.json")
    save_oof(out / OOF_FILE, oof)
    written += [out / "config.json", out / OOF_FILE, *enc.files]
    manifest = FileArtifactStore().write_manifest(out, written)
    with (out.parent / "CURRENT").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(out.name + "\n")
    return config, manifest
