#!/usr/bin/env python3
"""D-016 encoder and category-head bake-off, plus the P2.6 int8-vs-fp32 OOF parity (training machine).

    python scripts/encoder_bakeoff.py [--minilm-dir .tmp/enc_minilm]
                                      [--translations .tmp/translations_full.csv]
                                      [--aug-folds .tmp/cv_folds_aug.csv] [--fp32] [--boot 2000]
                                      [--out reports/encoder_bakeoff.json]

Grid: {e5-small, MiniLM-L12} (both ONNX int8, as they would ship) x {LR, ridge, prototype} x {raw, language-
mean centred} x data {official only, + translate-train, unreviewed augmentation arm}. Every score is
scenario-held-out OOF over the frozen `cv_fold` folds, on the **official rows only** (432), row-level
macro-F1, with EN/AR slices. Comparisons use a paired bootstrap over the official cv_groups (B resamples,
90 % interval = 5th..95th percentile). Training rows of the two augmented conditions are drafts that are
not human-checked yet: they are measured here and never frozen (`needs_human_check=True`).

The D-016 decision rule (both debaters): adopt the more complex/new option only if ALL hold: dF1 >= +0.05,
the 90 % lower bound > 0, no language slice worse by > 0.03, and the gain holds for >= 2 of the 3 heads. An
encoder switch also needs the measured gates (pruned-int8 RSS <= 300 MB, parity min cosine >= 0.98,
latency <= 1.5x), which `scripts/encoder_gates` evidence in reports/encoder_export*.json provides.

Heads (fixed settings, never tuned here): LR C = `stage_b.m2lr_C` (0.5, "strongly regularized"), ridge
alpha 1.0, prototype = the learned m2proto prototypes (category centroid of scenario centroids). All use
balanced class weights on hard labels. `--fp32` adds the e5-small fp32 encoder (sentence-transformers) and
writes `oof_macro_f1_{fp32,int8}` of the full pipeline (run_cv) into reports/encoder_export.json (P2.6).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression, RidgeClassifier

from campuspulse_ai.adapters.models.encoder import CachingEncoder, OnnxEncoder
from campuspulse_ai.adapters.models.probs import balanced_sample_weight
from campuspulse_ai.adapters.models.prototype import category_scores, learned_prototypes
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.cv import group_folds
from campuspulse_ai.adapters.training.metrics import macro_f1
from campuspulse_ai.adapters.training.oof import PipelineToggles, run_cv
from campuspulse_ai.adapters.training.pool import FOLDS_CSV, OFFICIAL_CSV, Pool, default_pool_paths, load_pool
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.composition.training import make_kit
from campuspulse_ai.config.paths import LEXICONS, MODELS_FROZEN, REPORTS
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS

ROOT = Path(__file__).resolve().parent.parent
HEADS = ("lr", "ridge", "proto")
RIDGE_ALPHA = 1.0
LR_MAX_ITER = 3000
CI_LOW, CI_HIGH = 5.0, 95.0
RULE = {"min_gain": 0.05, "max_slice_drop": 0.03, "min_heads": 2}
SEED = 42


@dataclasses.dataclass(frozen=True)
class Condition:
    name: str
    paths: tuple[Path, ...]
    folds: Path
    unreviewed: bool


def unit(x: NDArray[np.float64]) -> NDArray[np.float64]:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    out: NDArray[np.float64] = x / np.where(n == 0, 1.0, n)
    return out


def centre(
    xtr: NDArray[np.float64], ltr: Sequence[str], xte: NDArray[np.float64], lte: Sequence[str]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Language-mean centring (debater B): subtract each language's train-fold mean (label-free)."""
    xtr, xte = xtr.copy(), xte.copy()
    ltr_a, lte_a = np.asarray(ltr), np.asarray(lte)
    for lang in np.unique(ltr_a):
        mu = xtr[ltr_a == lang].mean(axis=0)
        xtr[ltr_a == lang] -= mu
        xte[lte_a == lang] -= mu
    return unit(xtr), unit(xte)


def head_predict(
    head: str,
    xtr: NDArray[np.float64],
    ytr: Sequence[str],
    scen: Sequence[str],
    xte: NDArray[np.float64],
    lr_c: float,
) -> list[str]:
    w = balanced_sample_weight(ytr, None, CATEGORY_LABELS)
    if head == "lr":
        lr = LogisticRegression(C=lr_c, max_iter=LR_MAX_ITER, random_state=SEED)
        lr.fit(xtr, list(ytr), sample_weight=w)
        return [str(v) for v in lr.predict(xte)]
    if head == "ridge":
        rc = RidgeClassifier(alpha=RIDGE_ALPHA)
        rc.fit(xtr, list(ytr), sample_weight=w)
        return [str(v) for v in rc.predict(xte)]
    if head == "proto":
        protos = learned_prototypes(xtr.astype(np.float32), list(ytr), list(scen))
        scores = category_scores(xte.astype(np.float32), protos, mix=1.0)
        return [CATEGORY_LABELS[int(j)] for j in np.argmax(scores, axis=1)]
    raise ValueError(head)


def head_oof(
    pool: Pool, emb: NDArray[np.float64], head: str, centred: bool, lr_c: float, k: int
) -> list[str]:
    """OOF category predictions for every pool row (only official rows are scored)."""
    pred = [""] * len(pool)
    langs = [str(x) for x in pool.lang]
    for train_idx, test_idx in group_folds(pool, k):
        tr, te = train_idx.tolist(), test_idx.tolist()
        xtr, xte = emb[tr], emb[te]
        if centred:
            xtr, xte = centre(xtr, [langs[i] for i in tr], xte, [langs[i] for i in te])
        out = head_predict(
            head, xtr, [pool.category[i] for i in tr], [pool.scenario_id[i] for i in tr], xte, lr_c
        )
        for i, p in zip(te, out, strict=True):
            pred[i] = p
    return pred


class Scorer:
    """Official-row macro-F1, language slices and the paired group bootstrap."""

    def __init__(
        self, pool: Pool, boot: int, labels: Sequence[str] = CATEGORY_LABELS, target: str = "category"
    ) -> None:
        self.idx = np.array([i for i, o in enumerate(pool.is_official) if o], dtype=np.int64)
        gold = pool.category if target == "category" else pool.priority
        self.y = [gold[i] for i in self.idx]
        self.labels = labels
        self.lang = [pool.lang_script[i] for i in self.idx]
        groups = [pool.cv_group[i] for i in self.idx]
        names = sorted(set(groups))
        self.by_group = [np.array([j for j, g in enumerate(groups) if g == n], dtype=np.int64) for n in names]
        rng = np.random.default_rng(SEED)
        self.samples = [rng.integers(0, len(names), len(names)) for _ in range(boot)]

    def f1(self, pred: Sequence[str], rows: NDArray[np.int64] | None = None) -> float:
        p = [pred[i] for i in self.idx]
        if rows is None:
            return macro_f1(self.y, p, self.labels)
        return macro_f1([self.y[j] for j in rows], [p[j] for j in rows], self.labels)

    def slices(self, pred: Sequence[str]) -> dict[str, float]:
        out = {}
        for lang in sorted(set(self.lang)):
            rows = np.array([j for j, la in enumerate(self.lang) if la == lang], dtype=np.int64)
            out[lang] = round(self.f1(pred, rows), 4)
        return out

    def paired(self, base: Sequence[str], cand: Sequence[str]) -> dict[str, float]:
        diffs = []
        for s in self.samples:
            rows = np.concatenate([self.by_group[g] for g in s])
            diffs.append(self.f1(cand, rows) - self.f1(base, rows))
        d = np.asarray(diffs)
        return {
            "delta": round(self.f1(cand) - self.f1(base), 4),
            "ci90_low": round(float(np.percentile(d, CI_LOW)), 4),
            "ci90_high": round(float(np.percentile(d, CI_HIGH)), 4),
            "p_better": round(float((d > 0).mean()), 3),
        }


def rule_passes(
    comp: Mapping[str, float], base_slices: Mapping[str, float], cand_slices: Mapping[str, float]
) -> bool:
    worst = min(cand_slices[k] - base_slices[k] for k in base_slices)
    return comp["delta"] >= RULE["min_gain"] and comp["ci90_low"] > 0 and worst >= -RULE["max_slice_drop"]


class Fp32Encoder:
    """sentence-transformers fp32 e5-small (training machine only), same prefix and truncation."""

    def __init__(self, model_id: str, revision: str, prefix: str, max_tokens: int) -> None:
        from huggingface_hub.constants import HF_HUB_CACHE
        from sentence_transformers import SentenceTransformer

        # the pinned snapshot already in the local cache (the export downloaded it); no network here
        path = str(Path(HF_HUB_CACHE) / f"models--{model_id.replace('/', '--')}" / "snapshots" / revision)
        self._st = SentenceTransformer(path, device="cpu")
        self._st.max_seq_length = max_tokens
        self._prefix = prefix
        self.dim = int(self._st.get_sentence_embedding_dimension() or 0)
        self.model_id, self.revision, self.query_prefix, self.max_tokens = (
            model_id,
            revision,
            prefix,
            max_tokens,
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        e = self._st.encode([self._prefix + t for t in texts], batch_size=1, normalize_embeddings=True)
        return [[float(v) for v in row] for row in e]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--minilm-dir", type=Path, default=ROOT / ".tmp" / "enc_minilm")
    ap.add_argument("--translations", type=Path, default=ROOT / ".tmp" / "translations_full.csv")
    ap.add_argument("--aug-folds", type=Path, default=ROOT / ".tmp" / "cv_folds_aug.csv")
    ap.add_argument("--fp32", action="store_true", help="also run the e5-small fp32 OOF parity (P2.6)")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=REPORTS / "encoder_bakeoff.json")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg = TrainCfg.load()
    lr_c = cfg.fixed_C[1]
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, int(cfg.section("guards")["max_tokens"]))
    encoders: dict[str, Callable[[], Any]] = {
        "e5-small": lambda: OnnxEncoder(MODELS_FROZEN / "v1" / "encoder"),
        "minilm-l12": lambda: OnnxEncoder(args.minilm_dir),
    }
    conditions = [Condition("official", (OFFICIAL_CSV,), FOLDS_CSV, False)]
    if args.translations.is_file():
        conditions.append(Condition("translate_train", (OFFICIAL_CSV, args.translations), FOLDS_CSV, True))
    if args.aug_folds.is_file():
        conditions.append(
            Condition("unreviewed_augmentation", tuple(default_pool_paths()), args.aug_folds, True)
        )
    pools = {
        c.name: load_pool(c.paths, normalizer, folds_csv=c.folds, include_unreviewed=c.unreviewed)
        for c in conditions
    }
    texts = sorted({t for p in pools.values() for t in p.model_text})
    report: dict[str, Any] = {
        "protocol": "scenario-held-out OOF on the official rows (432), frozen cv_fold folds; paired "
        "bootstrap "
        f"over official cv_groups, B={args.boot}, 90% interval; heads fixed (LR C={lr_c}, ridge "
        f"alpha={RIDGE_ALPHA}, learned prototypes); augmented conditions train on unreviewed drafts",
        "rule": RULE,
        "conditions": {},
        "encoders": {},
        "decisions": {},
    }
    preds: dict[tuple[str, str, str, bool], list[str]] = {}
    for enc_name, factory in encoders.items():
        base_enc = factory()
        enc = CachingEncoder(base_enc)
        t0 = time.perf_counter()
        vec = dict(zip(texts, np.asarray(enc.encode(texts), dtype=np.float64), strict=True))
        report["encoders"][enc_name] = {
            "model_id": base_enc.model_id,
            "revision": base_enc.revision,
            "ms_per_text_embed": round(1000 * (time.perf_counter() - t0) / len(texts), 1),
        }
        for cond in conditions:
            pool = pools[cond.name]
            emb = np.stack([vec[t] for t in pool.model_text])
            for head in HEADS:
                for centred in (False, True):
                    preds[(enc_name, cond.name, head, centred)] = head_oof(
                        pool, emb, head, centred, lr_c, cfg.k
                    )
            print(f"{enc_name} {cond.name}: done", flush=True)
    rows = []
    for cond in conditions:
        sc = Scorer(pools[cond.name], args.boot)
        report["conditions"][cond.name] = {
            "rows": len(pools[cond.name]),
            "official_rows": len(sc.idx),
            "unreviewed_training_rows": cond.unreviewed,
        }
        base = preds[("e5-small", "official", "lr", False)] if cond.name == "official" else None
        for (enc_name, cname, head, centred), p in preds.items():
            if cname != cond.name:
                continue
            row = {
                "encoder": enc_name,
                "data": cname,
                "head": head,
                "centred": centred,
                "cat_f1": round(sc.f1(p), 4),
                "slices": sc.slices(p),
            }
            if base is not None:
                row["vs_e5_lr_official"] = sc.paired(base, p)
            rows.append(row)
    report["grid"] = rows
    # decisions (each comparison on the same rows: the official rows of that condition)
    decisions: dict[str, Any] = {}
    for cond in conditions:
        sc = Scorer(pools[cond.name], args.boot)
        for centred in (False, True):
            per_head = {}
            for head in HEADS:
                a = preds[("e5-small", cond.name, head, centred)]
                b = preds[("minilm-l12", cond.name, head, centred)]
                comp = sc.paired(a, b)
                per_head[head] = {**comp, "passes": rule_passes(comp, sc.slices(a), sc.slices(b))}
            n_pass = sum(v["passes"] for v in per_head.values())
            decisions[f"minilm_vs_e5/{cond.name}/{'centred' if centred else 'raw'}"] = {
                "per_head": per_head,
                "heads_passing": n_pass,
                "adopt": n_pass >= RULE["min_heads"],
            }
        for enc_name in encoders:
            per_head = {}
            for head in HEADS:
                a = preds[(enc_name, cond.name, head, False)]
                b = preds[(enc_name, cond.name, head, True)]
                comp = sc.paired(a, b)
                per_head[head] = {**comp, "passes": rule_passes(comp, sc.slices(a), sc.slices(b))}
            n_pass = sum(v["passes"] for v in per_head.values())
            decisions[f"centring/{enc_name}/{cond.name}"] = {
                "per_head": per_head,
                "heads_passing": n_pass,
                "adopt": n_pass >= RULE["min_heads"],
            }
    if len(conditions) > 1:  # translate-train vs official on the same official rows
        sc = Scorer(pools["official"], args.boot)
        for enc_name in encoders:
            for cname in [c.name for c in conditions[1:]]:
                per_head = {}
                for head in HEADS:
                    a = preds[(enc_name, "official", head, False)]
                    b = preds[(enc_name, cname, head, False)]
                    comp = sc.paired(a, b)
                    per_head[head] = {**comp, "passes": rule_passes(comp, sc.slices(a), sc.slices(b))}
                n_pass = sum(v["passes"] for v in per_head.values())
                decisions[f"data/{enc_name}/{cname}_vs_official"] = {
                    "per_head": per_head,
                    "heads_passing": n_pass,
                    "adopt": n_pass >= RULE["min_heads"],
                }
    report["decisions"] = decisions
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.fp32:
        report["oof_parity"] = oof_parity(cfg, normalizer)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for key, d in decisions.items():
        print(f"{key}: heads passing {d['heads_passing']}/3 -> adopt={d['adopt']}")
    print(f"wrote {args.out}")
    return 0


def oof_parity(cfg: TrainCfg, normalizer: DefaultNormalizer) -> dict[str, Any]:
    """P2.6: full pipeline (run_cv, fixed stage B) with the fp32 vs the shipped int8 e5-small encoder."""
    enc_cfg = cfg.section("encoder")
    pool = load_pool([OFFICIAL_CSV], normalizer)
    out: dict[str, Any] = {}
    official = np.asarray(pool.is_official, dtype=bool)
    for name, base in (
        ("int8", OnnxEncoder(MODELS_FROZEN / "v1" / "encoder")),
        (
            "fp32",
            Fp32Encoder(
                str(enc_cfg["model_id"]),
                str(enc_cfg["revision"]),
                str(enc_cfg["query_prefix"]),
                int(enc_cfg["max_tokens"]),
            ),
        ),
    ):
        enc = CachingEncoder(base)
        kit = make_kit(cfg, LEXICONS, normalizer, enc)
        oof = run_cv(pool, enc, cfg, PipelineToggles(), kit, nested=False)
        scores = {}
        for target, key, labels, gold in (
            ("category", "ensemble.category", CATEGORY_LABELS, pool.category),
            ("priority", "final.priority", PRIORITY_LABELS, pool.priority),
        ):
            pred = [labels[int(j)] for j in np.argmax(oof.probs[key], axis=1)]
            scores[target] = round(
                macro_f1(
                    [g for g, o in zip(gold, official, strict=True) if o],
                    [p for p, o in zip(pred, official, strict=True) if o],
                    labels,
                ),
                4,
            )
        out[f"oof_macro_f1_{name}"] = scores
        print(f"oof parity {name}: {scores}", flush=True)
    return out


if __name__ == "__main__":
    sys.exit(main())
