"""`run_evaluation`: the composition root of `evaluate.py`'s report modes (P2.8, P2.9; ARCHITECTURE §6.2).

One protocol for every number (CLAUDE.md, LD-31):
  1. **OOF**: the frozen model dir's `oof.npz` (stage A + B of `train.py`, scenario-held-out over the frozen
     `cv_fold` folds), on the official rows (`oof_official`) and on every pool row (`oof_all`);
  2. **our own test set** `data/our_test/our_test.csv`, scored by the frozen model (`build_offline`), pooled
     (`our_test`) and per set (`our_test_set1..3`);
  3. **probes** `data/robustness/probes.csv` when it exists (P2.5), else skipped with a note.
Nothing is tuned here, and no random split exists anywhere. This module (with the validators and
`scripts/check_leakage.py`) is the only reader of `data/our_test` and `data/robustness`.

Outputs in `reports/`: `metrics.json` (everything), `benchmark.md`, `coverage.json`, `fairness.json`,
`ablations.json`, `errors.json`, `eda.json`, `confusions/<model>_<target>_<dataset>.json`,
`conformal_scores.npz`, and `model_lab.json` (the offline part of `MetricsResponse`, DTO-validated). Every
JSON carries `artifact_version`, `sha`, `generated_at`, `protocol` and the counts of each cell.
`reports/redteam/` (Backend, P4.11) is never touched.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.models.encoder import CachingEncoder
from campuspulse_ai.adapters.models.evidence import LexiconEvidenceExtractor
from campuspulse_ai.adapters.training.metrics import (
    accuracy,
    confusion,
    coverage,
    ece,
    macro_f1,
    paired_group_bootstrap,
)
from campuspulse_ai.adapters.training.oof import PipelineToggles, run_cv
from campuspulse_ai.adapters.training.pool import FOLDS_CSV, OFFICIAL_CSV
from campuspulse_ai.adapters.training.stages import EncoderInfo, freeze, stage_b
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.composition.offline import build_offline, conformal_predictor, resolve_model_dir
from campuspulse_ai.composition.training import TrainOptions, make_kit, make_pool
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.config.paths import DATA_AUGMENTED, LEXICONS, OUR_TEST, REPO_ROOT, ROBUSTNESS
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.values import PredictionSet, ProbVector

LABELS: Mapping[str, tuple[str, ...]] = {"category": CATEGORY_LABELS, "priority": PRIORITY_LABELS}
TARGETS: tuple[str, str] = ("category", "priority")
LANGS: tuple[str, str, str] = ("en", "ar", "arabizi")
ROUND = 4
ENSEMBLE = "Ensemble (tier 0)"
MEMBER_NAMES: Mapping[str, str] = {"m1": "M1", "m2lr": "M2-LR", "m2knn": "M2-kNN", "m2proto": "M2-proto"}
CATEGORY_ONLY = frozenset({"m2proto"})
PROTOCOL = (
    "scenario-held-out OOF over the frozen cv_fold folds (oof.npz from train.py; LD-31) + the frozen model "
    "on our own test set (pooled and per set) and the probes; nothing tuned on the test data"
)
OUR_TEST_CSV = OUR_TEST / "our_test.csv"
PROBES_CSV = ROBUSTNESS / "probes.csv"
REPORT_FILES = (
    "metrics.json",
    "benchmark.md",
    "coverage.json",
    "fairness.json",
    "ablations.json",
    "errors.json",
    "eda.json",
)
NEUTRAL = " "  # mask_deadline: deadline_today spans are deleted from the evaluation rows


@dataclass(frozen=True)
class EvalOptions:
    model_dir: Path
    reports: Path
    eval_cfg: Mapping[str, Any]
    modes: frozenset[str]
    use_llm: bool = False
    now: datetime | None = None


@dataclass
class Row:
    """One scored row: gold labels, the ensemble's labels and sets, each member's argmax."""

    request_id: str
    dataset: str  # oof | our_test | probes
    subset: str  # official/augmented for oof, set1..3 for our_test, style for probes
    lang: str  # en | ar | arabizi (slice key)
    group: str
    text: str
    category: str
    priority: str
    pred: dict[str, tuple[str | None, str | None]]  # model -> (category, priority); None = no opinion
    set_cat: PredictionSet
    set_pri: PredictionSet
    conf_cat: float
    conf_pri: float
    flags: tuple[str, ...] = ()
    neighbors: tuple[dict[str, Any], ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


def _r(x: float) -> float:
    return round(float(x), ROUND)


# --- predictions -----------------------------------------------------------------------------------------


def oof_rows(model_dir: Path, config: FrozenConfig) -> list[Row]:
    """Rows from `oof.npz`: the ensemble (category: ensemble, priority: head + safety floor) and members."""
    z = np.load(model_dir / "oof.npz", allow_pickle=False)
    members = list(config.ensemble.members)
    lac_cat = conformal_predictor(config, "category")
    lac_pri = conformal_predictor(config, "priority")
    text_of = _official_texts()
    rows = []
    for i in range(len(z["request_id"])):
        p_cat = ProbVector(tuple(float(v) for v in _renorm(z["ensemble__category"][i])), CATEGORY_LABELS)
        p_pri = ProbVector(tuple(float(v) for v in _renorm(z["final__priority"][i])), PRIORITY_LABELS)
        pred: dict[str, tuple[str | None, str | None]] = {ENSEMBLE: (p_cat.argmax(), p_pri.argmax())}
        for m in members:
            c = CATEGORY_LABELS[int(np.argmax(z[f"{m}__category"][i]))]
            p = None if m in CATEGORY_ONLY else PRIORITY_LABELS[int(np.argmax(z[f"{m}__priority"][i]))]
            pred[MEMBER_NAMES[m]] = (c, p)
        lang = "arabizi" if str(z["lang"][i]) == "arabizi" else str(z["lang_script"][i])
        rid = str(z["request_id"][i])
        rows.append(
            Row(
                rid,
                "oof",
                "official" if bool(z["is_official"][i]) else "augmented",
                lang,
                str(z["cv_group"][i]),
                text_of.get(rid, ""),
                str(z["category"][i]),
                str(z["priority"][i]),
                pred,
                _set_for(lac_cat, p_cat, lang),
                _set_for(lac_pri, p_pri, lang),
                max(p_cat.values),
                max(p_pri.values),
            )
        )
    return rows


def _set_for(predictor: Any, p: ProbVector, lang: str) -> PredictionSet:
    """The set as `TriageCore` builds it: per language for a MondrianByLang, else the global quantile."""
    by_lang = getattr(predictor, "predict_set_for", None)
    return by_lang(p, lang) if callable(by_lang) else predictor.predict_set(p)  # type: ignore[no-any-return]


def _renorm(v: NDArray[np.float64]) -> NDArray[np.float64]:
    out: NDArray[np.float64] = np.clip(np.asarray(v, dtype=np.float64), 0.0, None)
    total = float(out.sum())
    result: NDArray[np.float64] = out / total
    return result


def _official_texts() -> dict[str, str]:
    with OFFICIAL_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {r["request_id"]: r["text"] for r in csv.DictReader(fh)}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def core_rows(
    container: Any,
    items: Sequence[Mapping[str, str]],
    dataset: str,
    *,
    subset_key: str,
    group_key: str,
    cat_key: str,
    pri_key: str,
    text_key: str = "text",
) -> list[Row]:
    """Score items with a built offline container (the frozen model, or an ablation arm's)."""
    core = container.core
    results = core.classify_many([it[text_key] for it in items], memory=False)
    members = list(core.ensemble.members)
    rows = []
    for it, res in zip(items, results, strict=True):
        if isinstance(res, InvalidInput):  # empty text: the priors label it (LD-17)
            p_cat, p_pri = core.priors
            pred: dict[str, tuple[str | None, str | None]] = {ENSEMBLE: (p_cat.argmax(), p_pri.argmax())}
            full = (PredictionSet(frozenset(CATEGORY_LABELS)), PredictionSet(frozenset(PRIORITY_LABELS)))
            rows.append(
                Row(
                    it["request_id"],
                    dataset,
                    it[subset_key],
                    it["lang"],
                    it[group_key],
                    it[text_key],
                    it[cat_key],
                    it[pri_key],
                    pred,
                    full[0],
                    full[1],
                    0.0,
                    0.0,
                    ("empty_input",),
                )
            )
            continue
        req, out = res
        pred = {ENSEMBLE: (out.p_cat.argmax(), out.p_pri.argmax())}
        for m in members:
            pc, pp = out.per_model.get(f"{m}.category"), out.per_model.get(f"{m}.priority")
            pred[MEMBER_NAMES[m]] = (
                pc.argmax() if pc else None,
                None if m in CATEGORY_ONLY or pp is None else pp.argmax(),
            )
        neigh = tuple(
            {"text": n.text, "category": str(n.category), "priority": str(n.priority), "sim": _r(n.sim)}
            for n in out.neighbors[:3]
        )
        rows.append(
            Row(
                it["request_id"],
                dataset,
                it[subset_key],
                it["lang"],
                it[group_key],
                it[text_key],
                it[cat_key],
                it[pri_key],
                pred,
                out.set_cat,
                out.set_pri,
                max(out.p_cat.values),
                max(out.p_pri.values),
                tuple(sorted(out.flags)),
                neigh,
                {"detected_lang": str(req.lang), "ood_score": _r(out.ood_score)},
            )
        )
    return rows


def our_test_rows(container: Any) -> list[Row]:
    items = _read(OUR_TEST_CSV)
    return core_rows(
        container,
        items,
        "our_test",
        subset_key="test_set",
        group_key="scenario_family",
        cat_key="category",
        pri_key="priority",
    )


def probe_rows(container: Any) -> list[Row]:
    if not PROBES_CSV.is_file():
        return []
    items = _read(PROBES_CSV)
    for it in items:
        it["group"] = it.get("base_request_id") or it["request_id"]
    rows = core_rows(
        container,
        items,
        "probes",
        subset_key="style",
        group_key="group",
        cat_key="intended_category",
        pri_key="intended_priority",
    )
    for row, it in zip(rows, items, strict=True):
        row.extra["expected_flags"] = [f for f in it.get("expected_flags", "").split(";") if f.strip()]
        row.extra["base"] = it.get("base_request_id", "")
    return rows


# --- tables ----------------------------------------------------------------------------------------------


def _views(oof: Sequence[Row], test: Sequence[Row], probes: Sequence[Row]) -> list[tuple[str, list[Row]]]:
    """(dataset name, rows) in report order; the names are the `MetricsResponse` EvalDataset values."""
    views: list[tuple[str, list[Row]]] = [
        ("oof_official", [r for r in oof if r.subset == "official"]),
        ("oof_all", list(oof)),
        ("our_test", list(test)),
    ]
    for s in sorted({r.subset for r in test}):
        views.append((f"our_test_{s}", [r for r in test if r.subset == s]))
    if probes:
        views.append(("probes", list(probes)))
    return views


def _score(rows: Sequence[Row], model: str, target: str) -> tuple[float | None, float | None, int]:
    t = 0 if target == "category" else 1
    pairs = [(getattr(r, target), r.pred[model][t]) for r in rows if model in r.pred and r.pred[model][t]]
    if not pairs:
        return None, None, 0
    y, p = [a for a, _ in pairs], [str(b) for _, b in pairs]
    return _r(macro_f1(y, p, LABELS[target])), _r(accuracy(y, p)), len(pairs)


def benchmark(
    views: Sequence[tuple[str, list[Row]]], members: Sequence[str], use_llm: bool
) -> list[dict[str, Any]]:
    out = []
    names = [ENSEMBLE, *(MEMBER_NAMES[m] for m in members)]
    for dataset, rows in views:
        groups = len({r.group for r in rows})
        for target in TARGETS:
            for name in names:
                f1, acc, n = _score(rows, name, target)
                status = "ok" if f1 is not None else "n/a"
                out.append(
                    {
                        "model": name,
                        "target": target,
                        "dataset": dataset,
                        "macro_f1": f1,
                        "accuracy": acc,
                        "n_rows": n,
                        "n_groups": groups if f1 is not None else None,
                        "status": status,
                    }
                )
            out.append(
                {
                    "model": "M3",
                    "target": target,
                    "dataset": dataset,
                    "macro_f1": None,
                    "accuracy": None,
                    "n_rows": 0,
                    "n_groups": None,
                    "status": "cut",
                }
            )
            for name in ("Ensemble + router", "LLM zero-shot (M4)"):
                out.append(
                    {
                        "model": name,
                        "target": target,
                        "dataset": dataset,
                        "macro_f1": None,
                        "accuracy": None,
                        "n_rows": 0,
                        "n_groups": None,
                        "status": "n/a",
                    }
                )  # P3's OpenRouterOracle; `--use-llm` keeps n/a offline
    return out


def coverage_rows(views: Sequence[tuple[str, list[Row]]]) -> list[dict[str, Any]]:
    out = []
    for dataset, rows in views:
        if dataset == "probes":
            continue
        for target in TARGETS:
            for lang in ("all", *LANGS):
                sub = [r for r in rows if lang == "all" or r.lang == lang]
                if not sub:
                    continue
                sets = [r.set_cat if target == "category" else r.set_pri for r in sub]
                st = coverage(sets, [getattr(r, target) for r in sub])
                out.append(
                    {
                        "target": target,
                        "dataset": dataset,
                        "lang": lang,
                        "coverage": _r(st.coverage),
                        "mean_set_size": _r(st.mean_size),
                        "singleton_rate": _r(st.singleton_rate),
                        "n_rows": st.n,
                        "n_groups": len({r.group for r in sub}),
                    }
                )
    return out


def ask_proxy(rows: Sequence[Row]) -> float:
    """Share of rows with a 2-label category or priority set (LD-24: a proxy until P3's DecisionPolicy)."""
    return _r(sum(r.set_cat.size == 2 or r.set_pri.size == 2 for r in rows) / len(rows)) if rows else 0.0


def calibration(rows: Sequence[Row], bins: int) -> list[dict[str, Any]]:
    out = []
    for target in TARGETS:
        conf = [r.conf_cat if target == "category" else r.conf_pri for r in rows]
        ok = [r.pred[ENSEMBLE][0 if target == "category" else 1] == getattr(r, target) for r in rows]
        value, rel = ece(conf, ok, bins)
        out.append(
            {
                "target": target,
                "ece": _r(value),
                "bins": [
                    {
                        "lower": _r(b.lower),
                        "upper": _r(b.upper),
                        "confidence": _r(b.confidence),
                        "accuracy": _r(b.accuracy),
                        "count": b.count,
                    }
                    for b in rel
                ],
            }
        )
    return out


def fairness(views: Sequence[tuple[str, list[Row]]]) -> list[dict[str, Any]]:
    out = []
    for dataset, rows in views:
        for target in TARGETS:
            for lang in LANGS:
                sub = [r for r in rows if r.lang == lang]
                if not sub:
                    continue
                f1, _, n = _score(sub, ENSEMBLE, target)
                out.append(
                    {
                        "slice": lang,
                        "target": target,
                        "dataset": dataset,
                        "macro_f1": f1,
                        "n_rows": n,
                        "n_groups": len({r.group for r in sub}),
                    }
                )
    return out


def confusions(views: Sequence[tuple[str, list[Row]]], members: Sequence[str]) -> list[dict[str, Any]]:
    out = []
    for dataset, rows in views:
        for name in [ENSEMBLE, *(MEMBER_NAMES[m] for m in members)]:
            for target in TARGETS:
                t = 0 if target == "category" else 1
                pairs = [
                    (getattr(r, target), r.pred[name][t]) for r in rows if name in r.pred and r.pred[name][t]
                ]
                if not pairs:
                    continue
                table = confusion([a for a, _ in pairs], [str(b) for _, b in pairs], LABELS[target])
                labels = list(LABELS[target])
                out.append(
                    {
                        "model": name,
                        "target": target,
                        "dataset": dataset,
                        "labels": labels,
                        "matrix": [[table[a][b] for b in labels] for a in labels],
                    }
                )
    return out


def errors(oof: Sequence[Row], test: Sequence[Row]) -> dict[str, Any]:
    wrong_test = [
        {
            "request_id": r.request_id,
            "test_set": r.subset,
            "lang": r.lang,
            "text": r.text,
            "gold": f"{r.category} / {r.priority}",
            "pred": f"{r.pred[ENSEMBLE][0]} / {r.pred[ENSEMBLE][1]}",
            "wrong": [
                t for t, k in (("category", 0), ("priority", 1)) if getattr(r, t) != r.pred[ENSEMBLE][k]
            ],
            "set_category": sorted(r.set_cat.labels),
            "set_priority": sorted(r.set_pri.labels),
            "flags": list(r.flags),
            "neighbors": list(r.neighbors),
            **r.extra,
        }
        for r in test
        if (r.category, r.priority) != r.pred[ENSEMBLE]
    ]
    by_group: dict[str, list[Row]] = {}
    for r in oof:
        if r.subset == "official" and (r.category, r.priority) != r.pred[ENSEMBLE]:
            by_group.setdefault(r.group, []).append(r)
    wrong_oof = []
    for g, rs in sorted(by_group.items()):
        first = rs[0]
        wrong_oof.append(
            {
                "cv_group": g,
                "rows": len(rs),
                "lang": sorted({r.lang for r in rs}),
                "example": first.text,
                "gold": f"{first.category} / {first.priority}",
                "pred": dict(Counter(f"{r.pred[ENSEMBLE][0]} / {r.pred[ENSEMBLE][1]}" for r in rs)),
                "set_category_sizes": dict(Counter(r.set_cat.size for r in rs)),
                "set_priority_sizes": dict(Counter(r.set_pri.size for r in rs)),
            }
        )
    return {
        "our_test": wrong_test,
        "oof_official_groups": wrong_oof,
        "note": "OOF neighbours are not stored (each fold has its own index); our_test rows show the top-3 "
        "neighbours of the frozen index",
    }


def robustness(probes: Sequence[Row], test_by_id: Mapping[str, Row]) -> dict[str, Any]:
    if not probes:
        return {
            "status": "skipped",
            "note": "data/robustness/probes.csv does not exist yet (P2.5 is a human "
            "task); per-style scores appear once it is written",
        }
    styles: dict[str, Any] = {}
    for style in sorted({r.subset for r in probes}):
        rs = [r for r in probes if r.subset == style]
        cat_ok = sum(r.pred[ENSEMBLE][0] == r.category for r in rs)
        pri_ok = sum(r.pred[ENSEMBLE][1] == r.priority for r in rs)
        expected = [r for r in rs if r.extra.get("expected_flags")]
        flags_ok = sum(set(r.extra["expected_flags"]) <= set(r.flags) for r in expected)
        raised = [
            r
            for r in rs
            if r.extra.get("base") in test_by_id
            and _rank(r.pred[ENSEMBLE][1]) > _rank(test_by_id[r.extra["base"]].pred[ENSEMBLE][1])
        ]
        styles[style] = {
            "n": len(rs),
            "category_accuracy": _r(cat_ok / len(rs)),
            "priority_accuracy": _r(pri_ok / len(rs)),
            "flags_ok": f"{flags_ok}/{len(expected)}",
            "priority_raised_vs_base": len(raised),
        }
    return {"status": "ok", "by_style": styles}


def _rank(priority: str | None) -> int:
    return PRIORITY_LABELS.index(priority) if priority in PRIORITY_LABELS else -1


def eda() -> dict[str, Any]:
    official = _read(OFFICIAL_CSV)
    out: dict[str, Any] = {
        "official": {
            "rows": len(official),
            "distinct_texts": len({r["text_norm"] for r in official}),
            "scenarios": len({r["scenario_id"] for r in official}),
            "groups": len({r["cv_group"] for r in official}),
            "by_split": dict(Counter(r["split"] for r in official)),
            "by_lang": dict(Counter(r["lang"] for r in official)),
            "by_category": dict(Counter(r["category"] for r in official)),
            "by_priority": dict(Counter(r["priority"] for r in official)),
            "by_cell": dict(Counter(f"{r['category']} x {r['priority']}" for r in official)),
            "wrappers": {
                "with_prefix": sum(bool(r["prefix"]) for r in official),
                "with_suffix": sum(bool(r["suffix"]) for r in official),
                "distinct_prefixes": len({r["prefix"] for r in official if r["prefix"]}),
                "distinct_suffixes": len({r["suffix"] for r in official if r["suffix"]}),
            },
        },
        "augmented": {},
        "our_test": {},
    }
    for path in sorted(DATA_AUGMENTED.glob("*.csv")):
        rows = _read(path)
        out["augmented"][path.name] = {
            "rows": len(rows),
            "groups": len({r["cv_group"] for r in rows}),
            "reviewed": sum(r["needs_human_check"].strip().lower() == "false" for r in rows),
            "by_source": dict(Counter(r["source"] for r in rows)),
            "by_lang": dict(Counter(r["lang"] for r in rows)),
            "by_category": dict(Counter(r["category"] for r in rows)),
            "by_priority": dict(Counter(r["priority"] for r in rows)),
        }
    test = _read(OUR_TEST_CSV)
    out["our_test"] = {
        "rows": len(test),
        "by_set": dict(Counter(r["test_set"] for r in test)),
        "by_lang": dict(Counter(r["lang"] for r in test)),
        "by_cell": dict(Counter(f"{r['category']} x {r['priority']}" for r in test)),
        "families": len({r["scenario_family"] for r in test}),
    }
    out["probes"] = (
        {"rows": len(_read(PROBES_CSV))}
        if PROBES_CSV.is_file()
        else {"rows": 0, "note": "P2.5 probes not written yet"}
    )
    return out


# --- ablations (P2.9) --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Arm:
    name: str
    toggles: PipelineToggles = field(default_factory=PipelineToggles)
    cfg_change: Callable[[TrainCfg], TrainCfg] | None = None
    folds_csv: Path | None = None
    note: str = ""
    unreviewed: bool = False


def default_arms(cfg: TrainCfg, aug_folds: Path | None) -> list[Arm]:
    members = cfg.members

    def without(m: str) -> PipelineToggles:
        return PipelineToggles(members=tuple(x for x in members if x != m))

    def weights(cat: Mapping[str, float]) -> Callable[[TrainCfg], TrainCfg]:
        return lambda c: dataclasses.replace(c, fixed_weights_category=dict(cat))

    arms = [
        Arm("full"),
        Arm("-wrapper_stripping", PipelineToggles(strip_wrappers=False)),
        Arm(
            "-augmentation",
            PipelineToggles(use_augmentation=False),
            note="no reviewed augmentation exists yet (P2.4 pending), so this equals full",
        ),
        Arm("-urgency_features", PipelineToggles(use_evidence=False)),
        Arm("-m1", without("m1"), note="M1 has category weight 0 (D-016); this measures its priority role"),
        Arm("-m2lr", without("m2lr")),
        Arm("-m2knn", without("m2knn")),
        Arm("-m2proto", without("m2proto"), note="category falls back to M2-LR alone"),
        Arm("hard_targets", PipelineToggles(soft_targets=False)),
        Arm("proto_learned_only", PipelineToggles(proto_parts=("learned",)), note="D-014 part (a) only"),
        Arm("proto_office_only", PipelineToggles(proto_parts=("office",)), note="D-014 part (b) only"),
        Arm(
            "+knn_in_category",
            cfg_change=weights({"m2lr": 1 / 3, "m2proto": 1 / 3, "m2knn": 1 / 3}),
            note="D-016: kNN joins the category vote only if this arm passes the rule",
        ),
        Arm(
            "+m1_in_category",
            cfg_change=weights({"m2lr": 1 / 3, "m2proto": 1 / 3, "m1": 1 / 3}),
            note="D-016 dropped M1 from the category vote; this arm checks that call",
        ),
        Arm(
            "tuned_stage_b",
            cfg_change=lambda c: dataclasses.replace(c, stage_b_mode="tuned"),
            note="the P2.7 OOF search (C grids, simplex weights); in-sample selection, see the nested "
            "estimate",
        ),
    ]
    if aug_folds is not None and aug_folds.is_file():
        arms.append(
            Arm(
                "+unreviewed_augmentation",
                PipelineToggles(include_unreviewed=True),
                folds_csv=aug_folds,
                note="UNREVIEWED drafts (needs_human_check=True) in training: a measurement only, "
                "never frozen",
                unreviewed=True,
            )
        )
    return arms


def run_ablations(
    model_dir: Path,
    eval_cfg: Mapping[str, Any],
    encoder: Any,
    settings: Settings,
    aug_folds: Path | None,
    mask_rows: Callable[[Any], list[Row]] | None = None,
) -> dict[str, Any]:
    """Every arm: run_cv on the frozen folds (OOF official) + a full fit scored on our_test, Δ vs full with a
    paired group bootstrap (OOF) and the same rows for every arm."""
    cfg = TrainCfg.load()
    arms = default_arms(cfg, aug_folds)
    boot = eval_cfg["bootstrap"]
    results: dict[str, Any] = {}
    preds: dict[str, dict[str, Any]] = {}
    for arm in arms:
        acfg = arm.cfg_change(cfg) if arm.cfg_change else cfg
        opts = TrainOptions(cv_only=True, toggles=arm.toggles, folds_csv=arm.folds_csv or FOLDS_CSV)
        pool, normalizer = make_pool(opts, acfg)
        kit = make_kit(acfg, LEXICONS, normalizer, encoder)
        oof = run_cv(pool, encoder, acfg, arm.toggles, kit, nested=False)
        official = [i for i, o in enumerate(pool.is_official) if o]
        cat = [CATEGORY_LABELS[int(j)] for j in np.argmax(oof.probs["ensemble.category"], axis=1)]
        pri = [PRIORITY_LABELS[int(j)] for j in np.argmax(oof.probs["final.priority"], axis=1)]
        tuned = stage_b(oof, acfg, encoder, LEXICONS)
        with tempfile.TemporaryDirectory(prefix="cp_arm_") as tmp:
            out = Path(tmp) / "v1"
            info = EncoderInfo(
                getattr(encoder, "model_id", "encoder"), getattr(encoder, "revision", "none"), "onnx_int8", ()
            )
            freeze(out, oof, tuned, acfg, kit, encoder, info, LEXICONS)
            container = build_offline(out, encoder_override=encoder, settings=settings)
            test = our_test_rows(container)
            masked = mask_rows(container) if (mask_rows is not None and arm.name == "full") else None
        preds[arm.name] = {
            "oof_cat": {pool.request_id[i]: cat[i] for i in official},
            "oof_pri": {pool.request_id[i]: pri[i] for i in official},
            "groups": {pool.request_id[i]: pool.cv_group[i] for i in official},
            "gold": {pool.request_id[i]: (pool.category[i], pool.priority[i]) for i in official},
            "test": test,
        }
        if masked is not None:
            preds["mask_deadline"] = {**preds["full"], "test": masked, "masked_only": True}
        results[arm.name] = {
            "note": arm.note,
            "unreviewed_training_rows": arm.unreviewed,
            "members": list(oof.members),
            "pool_rows": len(pool),
        }
        print(f"ablation {arm.name}: done", flush=True)
    full = preds["full"]
    ids = sorted(full["oof_cat"])
    rows: list[dict[str, Any]] = []
    for name, p in preds.items():
        entry = results.setdefault(name, {})
        for target, key in (("category", "oof_cat"), ("priority", "oof_pri")):
            y = [full["gold"][i][0 if target == "category" else 1] for i in ids]
            base = [full[key][i] for i in ids]
            cand = [p[key][i] for i in ids]
            f1 = macro_f1(y, cand, LABELS[target])
            comp = paired_group_bootstrap(
                y,
                base,
                cand,
                [full["groups"][i] for i in ids],
                LABELS[target],
                resamples=int(boot["resamples"]),
                seed=int(boot["seed"]),
                low_pct=float(boot["low_pct"]),
                high_pct=float(boot["high_pct"]),
            )
            entry.setdefault("oof_official", {})[target] = {
                "macro_f1": _r(f1),
                "delta": _r(comp["delta"]),
                "ci90": [_r(comp["ci_low"]), _r(comp["ci_high"])],
                "p_better": _r(comp["p_better"]),
                "n_rows": len(ids),
                "n_groups": len(set(full["groups"].values())),
            }
            rows.append(
                {
                    "arm": name,
                    "target": target,
                    "dataset": "oof_official",
                    "macro_f1": _r(f1),
                    "delta": _r(comp["delta"]),
                }
            )
            views: list[tuple[str, Callable[[Row], bool]]] = [("our_test", _any_row)]
            views += [(f"our_test_{s}", _subset_is(s)) for s in ("set1", "set2", "set3")]
            for dataset, keep in views:
                trows = [r for r in p["test"] if keep(r)]
                frows = [r for r in full["test"] if keep(r)]
                t = 0 if target == "category" else 1
                f_arm = macro_f1(
                    [getattr(r, target) for r in trows],
                    [str(r.pred[ENSEMBLE][t]) for r in trows],
                    LABELS[target],
                )
                f_full = macro_f1(
                    [getattr(r, target) for r in frows],
                    [str(r.pred[ENSEMBLE][t]) for r in frows],
                    LABELS[target],
                )
                entry.setdefault(dataset, {})[target] = {
                    "macro_f1": _r(f_arm),
                    "delta": _r(f_arm - f_full),
                    "n_rows": len(trows),
                }
                rows.append(
                    {
                        "arm": name,
                        "target": target,
                        "dataset": dataset,
                        "macro_f1": _r(f_arm),
                        "delta": _r(f_arm - f_full),
                    }
                )
        entry["decision_rule"] = _rule(entry, eval_cfg["decision_rule"])
    if "mask_deadline" in results:
        results["mask_deadline"]["note"] = (
            "the full model scoring our_test with every deadline_today lexicon span deleted from the input "
            "(LD-34); its OOF numbers are the full model's (the frozen folds are not re-scored masked)"
        )
    return {"arms": results, "rows": rows}


def _any_row(row: Row) -> bool:
    return True


def _subset_is(subset: str) -> Callable[[Row], bool]:
    return lambda r: r.subset == subset


def _rule(entry: Mapping[str, Any], rule: Mapping[str, Any]) -> dict[str, Any]:
    """The D-016 rule on the OOF category comparison (slices are checked in the bake-off, not here)."""
    cat = entry.get("oof_official", {}).get("category")
    if not cat:
        return {}
    return {
        "passes": bool(cat["delta"] >= float(rule["min_gain"]) and cat["ci90"][0] > 0),
        "min_gain": rule["min_gain"],
        "note": "positive arms must also hold per language (bake-off)",
    }


def masked_rows_factory() -> Callable[[Any], list[Row]]:
    """mask_deadline (P2.9 #11): our_test with every deadline_today lexicon span deleted."""
    extractor = LexiconEvidenceExtractor.from_yaml(LEXICONS / "urgency.yaml", ("deadline_today",))

    def run(container: Any) -> list[Row]:
        items = []
        for it in _read(OUR_TEST_CSV):
            req = container.core.normalizer.normalize(it["text"])
            text = req.text_norm  # spans are found on the normalized text, so mask there
            for ev in extractor.extract(req).spans:
                text = text.replace(ev.span, NEUTRAL)
            items.append({**it, "text": " ".join(text.split()) or req.text_norm})
        return core_rows(
            container,
            items,
            "our_test",
            subset_key="test_set",
            group_key="scenario_family",
            cat_key="category",
            pri_key="priority",
        )

    return run


# --- writing ---------------------------------------------------------------------------------------------


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def benchmark_md(bench: Sequence[Mapping[str, Any]], header: Mapping[str, Any]) -> str:
    datasets = list(dict.fromkeys(r["dataset"] for r in bench))
    models = list(dict.fromkeys(r["model"] for r in bench))
    lines = [
        f"# Benchmark (artifact {header['artifact_version']} sha {header['sha']})",
        "",
        f"Protocol: {PROTOCOL}. Macro-F1 (accuracy); n/a = not available offline; cut = not built (UD-4).",
        "",
    ]
    for target in TARGETS:
        lines += [
            f"## {target}",
            "",
            "| model | " + " | ".join(datasets) + " |",
            "| --- |" + " ---: |" * len(datasets),
        ]
        for m in models:
            cells = []
            for d in datasets:
                r = next(x for x in bench if x["model"] == m and x["dataset"] == d and x["target"] == target)
                cells.append(
                    f"{r['macro_f1']:.3f} ({r['accuracy']:.3f})" if r["macro_f1"] is not None else r["status"]
                )
            lines.append(f"| {m} | " + " | ".join(cells) + " |")
        lines.append("")
    counts = {r["dataset"]: (r["n_rows"], r["n_groups"]) for r in bench if r["model"] == ENSEMBLE}
    lines.append("Rows / groups: " + "; ".join(f"{d} {n}/{g}" for d, (n, g) in counts.items()))
    return "\n".join(lines) + "\n"


def run_evaluation(opts: EvalOptions, *, settings: Settings | None = None) -> str:
    """Run the chosen modes and write the reports; returns the summary line."""
    settings = settings or Settings()
    model_dir = resolve_model_dir(opts.model_dir)
    container = build_offline(model_dir, settings=settings)
    config = container.config
    sha = container.manifest.sha[:12]
    now = (opts.now or datetime.now(UTC)).isoformat(timespec="seconds")
    header = {
        "artifact_version": config.artifact_version,
        "sha": sha,
        "generated_at": now,
        "protocol": PROTOCOL,
    }
    reports = opts.reports
    members = list(config.ensemble.members)
    oof = oof_rows(model_dir, config)
    test = our_test_rows(container)
    probes = probe_rows(container)
    views = _views(oof, test, probes)
    bins = int(opts.eval_cfg["ece_bins"])
    previous = reports / "metrics.json"
    metrics: dict[str, Any] = {}
    if "all" not in opts.modes and previous.is_file():  # a single-mode run updates its own sections only
        metrics = json.loads(previous.read_text(encoding="utf-8"))
    metrics.update({**header, "members": members, "counts": {d: len(r) for d, r in views}})
    written: list[str] = []
    bench = benchmark(views, members, opts.use_llm)
    cov = coverage_rows(views)
    cal = calibration(test, bins)
    fair = fairness(views)
    conf = confusions(views, members)
    ask = ask_proxy(test)
    if {"benchmark", "all"} & opts.modes:
        metrics["benchmark"] = bench
        (reports / "benchmark.md").write_text(benchmark_md(bench, header), encoding="utf-8", newline="\n")
        cdir = reports / "confusions"
        if cdir.exists():
            shutil.rmtree(cdir)
        for c in conf:
            name = f"{c['model'].split(' ')[0].lower()}_{c['target']}_{c['dataset']}.json"
            _dump(cdir / name, {**header, **c})
        written += ["benchmark.md", "confusions/"]
    if {"coverage", "all"} & opts.modes:
        cov_doc = {
            **header,
            "rows": cov,
            "calibration_our_test": cal,
            "ask_proxy_rate": ask,
            "ask_proxy_is_proxy": True,
            "config": {
                "alpha_category": config.conformal.alpha_category,
                "alpha_priority": config.conformal.alpha_priority,
                "q_category": config.conformal.q_category,
                "q_priority": config.conformal.q_priority,
                "calibration": config.conformal.calibration,
                "mondrian_by_lang": config.conformal.mondrian_by_lang,
            },
            "calibration_oof_official": calibration([r for r in oof if r.subset == "official"], bins),
            "note": "coverage is approximate: effective n ~ groups (LD-32); counts beside every number",
        }
        _dump(reports / "coverage.json", cov_doc)
        metrics["coverage"] = cov_doc
        _conformal_scores(reports / "conformal_scores.npz", model_dir)
        written.append("coverage.json")
    if {"fairness", "all"} & opts.modes:
        gaps = {}
        for d, _ in views:
            for t in TARGETS:
                vals = [
                    f["macro_f1"]
                    for f in fair
                    if f["dataset"] == d and f["target"] == t and f["macro_f1"] is not None
                ]
                if len(vals) > 1:
                    gaps[f"{d}/{t}"] = _r(max(vals) - min(vals))
        fair_doc = {
            **header,
            "slices": fair,
            "max_gap": gaps,
            "note": "no significance claims: effective n ~ 30 groups (LD-32, LD-33)",
        }
        _dump(reports / "fairness.json", fair_doc)
        metrics["fairness"] = fair_doc
        written.append("fairness.json")
    if {"errors", "all"} & opts.modes:
        _dump(reports / "errors.json", {**header, **errors(oof, test)})
        written.append("errors.json")
    if {"eda", "all"} & opts.modes:
        _dump(reports / "eda.json", {**header, **eda()})
        written.append("eda.json")
    if {"robustness", "all"} & opts.modes:
        metrics["robustness"] = robustness(probes, {r.request_id: r for r in test})
    if {"ablations", "all"} & opts.modes:
        with tempfile.TemporaryDirectory(prefix="cp_folds_") as tmp:
            aug_folds = augmented_folds(Path(tmp) / "cv_folds_aug.csv")
            abl = run_ablations(
                model_dir,
                opts.eval_cfg,
                CachingEncoder(container.encoder),
                settings,
                aug_folds,
                masked_rows_factory(),
            )
        _dump(reports / "ablations.json", {**header, **abl})
        metrics["ablations"] = abl["arms"]
        written.append("ablations.json")
    elif (reports / "ablations.json").is_file():
        metrics["ablations"] = json.loads((reports / "ablations.json").read_text(encoding="utf-8")).get(
            "arms", {}
        )
    metrics["ask_proxy_rate"] = ask
    _dump(reports / "metrics.json", metrics)
    written.insert(0, "metrics.json")
    lab = model_lab(now, ask, bench, cov, cal, fair, conf, reports)
    _dump(reports / "model_lab.json", lab)
    names = ",".join(f for f in (*REPORT_FILES, "confusions/") if f in written)
    try:
        shown = reports.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        shown = reports.as_posix()
    return f"wrote {shown}/{{{names}}} (artifact {config.artifact_version} sha={sha})"


def model_lab(
    now: str,
    ask: float,
    bench: Sequence[Mapping[str, Any]],
    cov: Sequence[Mapping[str, Any]],
    cal: Sequence[Mapping[str, Any]],
    fair: Sequence[Mapping[str, Any]],
    conf: Sequence[Mapping[str, Any]],
    reports: Path,
) -> dict[str, Any]:
    """The offline part of `MetricsResponse` (validated against the DTOs before it is returned)."""
    from campuspulse_ai.application import dto

    abl_rows: list[Mapping[str, Any]] = []
    path = reports / "ablations.json"
    if path.is_file():
        abl_rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    lab = {
        "generated_at": now,
        "ask_rate": ask,
        "ask_rate_is_proxy": True,
        "benchmark": list(bench),
        "coverage": list(cov),
        "calibration": list(cal),
        "fairness": list(fair),
        "ablations": [
            r
            for r in abl_rows
            if r["dataset"] in ("oof_official", "our_test", "our_test_set1", "our_test_set2", "our_test_set3")
        ],
        "confusions": [c for c in conf if c["model"] == ENSEMBLE],
    }
    for key, model in (
        ("benchmark", dto.BenchmarkRowOut),
        ("coverage", dto.CoverageRowOut),
        ("calibration", dto.CalibrationOut),
        ("fairness", dto.FairnessSliceOut),
        ("ablations", dto.AblationRowOut),
        ("confusions", dto.ConfusionOut),
    ):
        for item in lab[key]:  # type: ignore[attr-defined]
            model.model_validate(item)
    return lab


def _conformal_scores(path: Path, model_dir: Path) -> None:
    """OOF nonconformity scores, labels, lang and groups for notebook 03's mapie cross-check."""
    z = np.load(model_dir / "oof.npz", allow_pickle=False)
    arrays: dict[str, Any] = {}
    for target, key, labels in (
        ("category", "ensemble__category", CATEGORY_LABELS),
        ("priority", "final__priority", PRIORITY_LABELS),
    ):
        idx = np.array([labels.index(str(v)) for v in z[target]])
        arrays[f"probs_{target}"] = z[key]
        arrays[f"y_{target}"] = idx
        arrays[f"scores_{target}"] = 1.0 - z[key][np.arange(len(idx)), idx]
    arrays.update(
        {
            "lang": z["lang"],
            "lang_script": z["lang_script"],
            "cv_group": z["cv_group"],
            "is_official": z["is_official"],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def augmented_folds(out: Path) -> Path | None:
    """Folds for every augmented group (`make_folds.py --include-augmented`, official groups unchanged),
    written to `out` for the unreviewed arm only; data/clean/cv_folds.csv is never rewritten here."""
    import subprocess
    import sys

    script = REPO_ROOT / "scripts" / "make_folds.py"
    done = subprocess.run(
        [sys.executable, str(script), "--include-augmented", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    return out if done.returncode == 0 and out.is_file() else None


def load_eval_cfg() -> Mapping[str, Any]:
    import yaml

    raw = yaml.safe_load((REPO_ROOT / "config" / "train.yaml").read_text(encoding="utf-8"))
    return dict(raw["eval"])
