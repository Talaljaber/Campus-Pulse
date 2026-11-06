"""First results report for the frozen v1 (a preview of P2.8 `evaluate.py`; ML batch 3).

    python scripts/results_v1.py [--model-dir models/frozen] [--out reports]

Writes `reports/results_v1.json`, `reports/results_v1.md` (human-readable) and `reports/model_lab.json`
(the offline part of `MetricsResponse` for `GET /v1/metrics`, validated against the DTOs).

Protocol (CLAUDE.md, LD-31): only
  1. **OOF** from the frozen model dir's `oof.npz` (stage A of `train.py`: scenario-held-out over the frozen
     `cv_fold` folds; every prediction comes from members, index and head that never saw the row's cv_group);
  2. the frozen v1 on **our own test set** `data/our_test/our_test.csv`, per `test_set` and pooled. This file
     is read here only to score; nothing is trained or tuned on it.
No random split exists anywhere. Metrics use the official hard labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai"))

from campuspulse_ai.adapters.training.metrics import accuracy, confusion, coverage, macro_f1  # noqa: E402
from campuspulse_ai.application import dto  # noqa: E402
from campuspulse_ai.composition.offline import build_offline, resolve_model_dir  # noqa: E402
from campuspulse_ai.config.paths import MODELS_FROZEN, OUR_TEST, REPORTS  # noqa: E402
from campuspulse_ai.domain.errors import InvalidInput  # noqa: E402
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS  # noqa: E402
from campuspulse_ai.domain.values import PredictionSet  # noqa: E402

LABELS = {"category": CATEGORY_LABELS, "priority": PRIORITY_LABELS}
MEMBER_NAMES = {
    "m1": "M1 (TF-IDF LR)",
    "m2lr": "M2-LR (e5 + LR)",
    "m2knn": "M2-kNN",
    "ensemble": "Ensemble (tier 0)",
}
LAB_NAMES = {"m1": "M1", "m2lr": "M2-LR", "m2knn": "M2-kNN", "ensemble": "Ensemble (tier 0)"}
ROUND = 4


def _r(x: float) -> float:
    return round(float(x), ROUND)


def scores(y: Sequence[str], yhat: Sequence[str], target: str) -> dict[str, float]:
    return {"macro_f1": _r(macro_f1(y, yhat, LABELS[target])), "accuracy": _r(accuracy(y, yhat))}


def block(rows: Sequence[Mapping[str, Any]], group_key: str) -> dict[str, Any]:
    """Category/priority/joint metrics plus counts for a list of rows with gold and predicted labels."""
    if not rows:
        return {"rows": 0, "groups": 0}
    y_c, p_c = [r["category"] for r in rows], [r["pred_category"] for r in rows]
    y_p, p_p = [r["priority"] for r in rows], [r["pred_priority"] for r in rows]
    joint = sum(a == b and c == d for a, b, c, d in zip(y_c, p_c, y_p, p_p, strict=True)) / len(rows)
    return {
        "rows": len(rows),
        "groups": len({r[group_key] for r in rows}),
        "category": scores(y_c, p_c, "category"),
        "priority": scores(y_p, p_p, "priority"),
        "joint_accuracy": _r(joint),
    }


def set_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Conformal coverage, mean set size, singleton rate per target and the ASK-proxy rate (|S| = 2)."""
    out: dict[str, Any] = {}
    for target in ("category", "priority"):
        stats = coverage([r[f"set_{target}"] for r in rows], [r[target] for r in rows])
        out[target] = {
            "coverage": _r(stats.coverage),
            "mean_set_size": _r(stats.mean_size),
            "singleton_rate": _r(stats.singleton_rate),
            "n": stats.n,
        }
    ask = sum(r["set_category"].size == 2 or r["set_priority"].size == 2 for r in rows) / len(rows)
    out["ask_proxy_rate"] = _r(ask)
    return out


# --- OOF ---------------------------------------------------------------------------------------------


def oof_section(model_dir: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    z = np.load(model_dir / "oof.npz", allow_pickle=False)
    n = len(z["request_id"])
    members = [m for m in ("m1", "m2lr", "m2knn") if f"{m}__category" in z.files]

    def argmax(key: str, target: str) -> list[str]:
        return [LABELS[target][int(j)] for j in np.argmax(z[key], axis=1)]

    base = [
        {
            "request_id": str(z["request_id"][i]),
            "category": str(z["category"][i]),
            "priority": str(z["priority"][i]),
            "group": str(z["cv_group"][i]),
            "lang": str(z["lang_script"][i]),
            "official": bool(z["is_official"][i]),
        }
        for i in range(n)
    ]
    preds = {"ensemble": (argmax("ensemble__category", "category"), argmax("final__priority", "priority"))}
    for m in members:
        preds[m] = (argmax(f"{m}__category", "category"), argmax(f"{m}__priority", "priority"))
    per_model: dict[str, list[dict[str, Any]]] = {
        name: [
            {**b, "pred_category": c, "pred_priority": p} for b, c, p in zip(base, cats, pris, strict=True)
        ]
        for name, (cats, pris) in preds.items()
    }
    rows = per_model["ensemble"]
    official = [r for r in rows if r["official"]]
    section: dict[str, Any] = {
        "protocol": "scenario-held-out OOF over the frozen cv_fold folds (LD-31), stage A of train.py",
        "official": block(official, "group"),
        "all_rows": block(rows, "group"),
        "by_lang_script_official": {
            lang: block([r for r in official if r["lang"] == lang], "group")
            for lang in sorted({r["lang"] for r in official})
        },
        "per_model_official": {
            name: block([r for r in rs if r["official"]], "group") for name, rs in per_model.items()
        },
        "priority_stages_official": {
            stage: scores(
                [r["priority"] for r in official],
                [p for p, r in zip(argmax(key, "priority"), rows, strict=True) if r["official"]],
                "priority",
            )
            for stage, key in (
                ("members_average", "ensemble__priority"),
                ("head", "head__priority"),
                ("head_plus_safety_floor", "final__priority"),
            )
        },
    }
    return section, per_model


# --- our own test set --------------------------------------------------------------------------------


def our_test_section(model_dir: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], Any]:
    container = build_offline(model_dir)
    with (OUR_TEST / "our_test.csv").open(encoding="utf-8-sig", newline="") as fh:
        gold = list(csv.DictReader(fh))
    results = container.core.classify_many([g["text"] for g in gold], memory=False)
    per_model: dict[str, list[dict[str, Any]]] = {
        k: [] for k in ("ensemble", *container.core.ensemble.members)
    }
    for g, res in zip(gold, results, strict=True):
        base = {
            k: g[k]
            for k in ("request_id", "text", "lang", "category", "priority", "test_set", "scenario_family")
        }
        base["group"] = g["scenario_family"]
        if isinstance(res, InvalidInput):  # empty text: the priors label it (LD-17)
            p_cat, p_pri = container.core.priors
            per_model["ensemble"].append(
                {
                    **base,
                    "pred_category": p_cat.argmax(),
                    "pred_priority": p_pri.argmax(),
                    "set_category": PredictionSet(frozenset(CATEGORY_LABELS)),
                    "set_priority": PredictionSet(frozenset(PRIORITY_LABELS)),
                    "flags": [],
                }
            )
            continue
        req, core = res
        per_model["ensemble"].append(
            {
                **base,
                "pred_category": core.p_cat.argmax(),
                "pred_priority": core.p_pri.argmax(),
                "set_category": core.set_cat,
                "set_priority": core.set_pri,
                "flags": sorted(core.flags),
                "p_category_max": _r(max(core.p_cat.values)),
                "p_priority_max": _r(max(core.p_pri.values)),
                "detected_lang": str(req.lang),
                "ood_score": _r(core.ood_score),
            }
        )
        for m in container.core.ensemble.members:
            pc, pp = core.per_model.get(f"{m}.category"), core.per_model.get(f"{m}.priority")
            if pc is not None and pp is not None:
                per_model[m].append({**base, "pred_category": pc.argmax(), "pred_priority": pp.argmax()})
    rows = per_model["ensemble"]
    sets = sorted({r["test_set"] for r in rows})
    section: dict[str, Any] = {"protocol": "frozen v1 on data/our_test/our_test.csv (read only to score)"}
    for name, subset in [*((s, [r for r in rows if r["test_set"] == s]) for s in sets), ("pooled", rows)]:
        section[name] = {
            **block(subset, "group"),
            "conformal": set_block(subset),
            "by_lang": {
                lang: {
                    **block([r for r in subset if r["lang"] == lang], "group"),
                    "conformal": set_block([r for r in subset if r["lang"] == lang]),
                }
                for lang in ("en", "ar", "arabizi")
                if any(r["lang"] == lang for r in subset)
            },
        }
    section["per_model_pooled"] = {name: block(rs, "group") for name, rs in per_model.items()}
    section["per_model_by_set"] = {
        name: {s: block([r for r in rs if r["test_set"] == s], "group") for s in sets}
        for name, rs in per_model.items()
    }
    section["langid_confusions"] = sum(r.get("detected_lang", r["lang"]) != r["lang"] for r in rows)
    section["errors"] = [
        {
            "request_id": r["request_id"],
            "test_set": r["test_set"],
            "lang": r["lang"],
            "text": r["text"],
            "gold": f"{r['category']} / {r['priority']}",
            "pred": f"{r['pred_category']} / {r['pred_priority']}",
            "wrong": [t for t in ("category", "priority") if r[t] != r[f"pred_{t}"]],
            "set_category": sorted(r["set_category"].labels),
            "set_priority": sorted(r["set_priority"].labels),
            "flags": r["flags"],
        }
        for r in rows
        if r["category"] != r["pred_category"] or r["priority"] != r["pred_priority"]
    ]
    return section, per_model, container


# --- model lab (MetricsResponse offline part) ---------------------------------------------------------


def model_lab(
    oof_models: Mapping[str, list[dict[str, Any]]],
    test_models: Mapping[str, list[dict[str, Any]]],
    generated_at: str,
    ask_rate: float,
) -> dict[str, Any]:
    benchmark, fairness, confusions, cov = [], [], [], []
    datasets: list[tuple[str, Mapping[str, list[dict[str, Any]]], Callable[[dict[str, Any]], bool]]] = [
        ("oof_official", oof_models, lambda r: bool(r["official"])),
        ("oof_all", oof_models, lambda r: True),
        ("our_test", test_models, lambda r: True),
    ]
    for dataset, models, keep in datasets:
        for name, rows_all in models.items():
            rows = [r for r in rows_all if keep(r)]
            for target in ("category", "priority"):
                y, yhat = [r[target] for r in rows], [r[f"pred_{target}"] for r in rows]
                benchmark.append(
                    {
                        "model": LAB_NAMES[name],
                        "target": target,
                        "dataset": dataset,
                        "macro_f1": _r(macro_f1(y, yhat, LABELS[target])),
                        "accuracy": _r(accuracy(y, yhat)),
                        "n_rows": len(rows),
                        "n_groups": len({r["group"] for r in rows}),
                        "status": "ok",
                    }
                )
                if name == "ensemble" and dataset != "oof_all":
                    table = confusion(y, yhat, LABELS[target])
                    confusions.append(
                        {
                            "model": LAB_NAMES[name],
                            "target": target,
                            "dataset": dataset,
                            "labels": list(LABELS[target]),
                            "matrix": [[table[a][b] for b in LABELS[target]] for a in LABELS[target]],
                        }
                    )
                    lang_key = "lang"
                    for lang in ("en", "ar", "arabizi"):
                        sub = [r for r in rows if r[lang_key] == lang]
                        if sub:
                            ys, ps = [r[target] for r in sub], [r[f"pred_{target}"] for r in sub]
                            fairness.append(
                                {
                                    "slice": lang,
                                    "target": target,
                                    "dataset": dataset,
                                    "macro_f1": _r(macro_f1(ys, ps, LABELS[target])),
                                    "n_rows": len(sub),
                                    "n_groups": len({r["group"] for r in sub}),
                                }
                            )
        for target in ("category", "priority"):
            benchmark.append(
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
    test_rows = test_models["ensemble"]
    for target in ("category", "priority"):
        for lang in ("all", "en", "ar", "arabizi"):
            sub = [r for r in test_rows if lang == "all" or r["lang"] == lang]
            stats = coverage([r[f"set_{target}"] for r in sub], [r[target] for r in sub])
            cov.append(
                {
                    "target": target,
                    "dataset": "our_test",
                    "lang": lang,
                    "coverage": _r(stats.coverage),
                    "mean_set_size": _r(stats.mean_size),
                    "singleton_rate": _r(stats.singleton_rate),
                    "n_rows": stats.n,
                    "n_groups": len({r["group"] for r in sub}),
                }
            )
    lab = {
        "generated_at": generated_at,
        "ask_rate": ask_rate,
        "ask_rate_is_proxy": True,
        "benchmark": benchmark,
        "coverage": cov,
        "calibration": [],
        "fairness": fairness,
        "ablations": [],
        "confusions": confusions,
    }
    for key, model in (
        ("benchmark", dto.BenchmarkRowOut),
        ("coverage", dto.CoverageRowOut),
        ("fairness", dto.FairnessSliceOut),
        ("confusions", dto.ConfusionOut),
    ):
        for row in lab[key]:
            model.model_validate(row)  # the admin model lab must accept every row
    return lab


# --- markdown ----------------------------------------------------------------------------------------


def _row(name: str, b: Mapping[str, Any]) -> str:
    c, p = b["category"], b["priority"]
    return (
        f"| {name} | {b['rows']} | {b['groups']} | {c['macro_f1']:.3f} | {c['accuracy']:.3f} | "
        f"{p['macro_f1']:.3f} | {p['accuracy']:.3f} | {b['joint_accuracy']:.3f} |"
    )


HEAD = [
    "| slice | rows | groups | cat macro-F1 | cat acc | pri macro-F1 | pri acc | joint acc |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
]


def markdown(res: Mapping[str, Any]) -> str:
    oof, test = res["oof"], res["our_test"]
    sets = [s for s in ("set1", "set2", "set3") if s in test]
    lines = [
        "# CampusPulse v1: first results (ML batch 3)",
        "",
        f"Artifact `{res['artifact_version']}` sha `{res['sha'][:12]}`, generated {res['generated_at']} by "
        "`python scripts/results_v1.py`. This previews P2.8 (`evaluate.py`). Stage B is still provisional "
        "(equal ensemble weights, C at the grid midpoint). Encoder: int8 e5-small, vocabulary-pruned "
        "(identical embeddings).",
        "",
        "**Protocol.** Only two kinds of numbers appear here: scenario-held-out OOF over the frozen "
        "`cv_fold` folds (LD-31), and the frozen model on our own test set. "
        "No random split is used anywhere. "
        "Groups are `cv_group` for OOF and `scenario_family` for our_test.",
        "",
        "## Headline",
        "",
        *HEAD,
        _row("OOF, official rows", oof["official"]),
        *(_row(f"our_test {s}", test[s]) for s in sets),
        _row("our_test pooled", test["pooled"]),
        "",
        "Conformal sets on our_test (target coverage 90 %, α = 0.10 per target):",
        "",
        "| set | cat coverage | cat mean size | pri coverage | pri mean size | ASK proxy (a set of size 2) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in [*sets, "pooled"]:
        cf = test[s]["conformal"]
        lines.append(
            f"| {s} | {cf['category']['coverage']:.3f} | {cf['category']['mean_set_size']:.2f} | "
            f"{cf['priority']['coverage']:.3f} | {cf['priority']['mean_set_size']:.2f} | "
            f"{cf['ask_proxy_rate']:.3f} |"
        )
    stages = "; ".join(
        f"{k}: macro-F1 {v['macro_f1']:.3f}, acc {v['accuracy']:.3f}"
        for k, v in oof["priority_stages_official"].items()
    )
    lines += [
        "",
        "## OOF (scenario-held-out) by language",
        "",
        "Official rows; `lang` is script-only (there is no Arabizi in the official data).",
        "",
        *HEAD,
        *(_row(lang, b) for lang, b in oof["by_lang_script_official"].items()),
        _row("all pool rows", oof["all_rows"]),
        "",
        "## Per model",
        "",
        "OOF, official rows:",
        "",
        *HEAD,
        *(_row(MEMBER_NAMES[m], b) for m, b in oof["per_model_official"].items()),
        "",
        f"Priority stages (OOF, official rows): {stages}.",
        "",
        "our_test pooled (member argmax; a member's priority is before the head and floors):",
        "",
        *HEAD,
        *(_row(MEMBER_NAMES[m], b) for m, b in test["per_model_pooled"].items()),
        "",
        "## our_test by language (pooled)",
        "",
        *HEAD,
        *(_row(lang, b) for lang, b in test["pooled"]["by_lang"].items()),
        "",
        f"## Errors on our_test ({len(test['errors'])} of {test['pooled']['rows']} rows)",
        "",
        "| id | set | lang | text | gold | pred | wrong | size S_cat | size S_pri |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for e in test["errors"]:
        text = e["text"].replace("|", "/")
        lines.append(
            f"| {e['request_id']} | {e['test_set']} | {e['lang']} | {text} | {e['gold']} | "
            f"{e['pred']} | {', '.join(e['wrong'])} | {len(e['set_category'])} | "
            f"{len(e['set_priority'])} |"
        )
    head_end = lines.index("## OOF (scenario-held-out) by language")
    lines[head_end:head_end] = findings(res)
    lines += ["", CAVEATS]
    return "\n".join(lines)


def findings(res: Mapping[str, Any]) -> list[str]:
    """Data-driven observations (every number below is computed from `res`)."""
    from collections import Counter

    test, oof = res["our_test"], res["oof"]
    errors = test["errors"]
    cat_err = [e for e in errors if "category" in e["wrong"]]
    pri_err = [e for e in errors if "priority" in e["wrong"]]
    cat_in_set = sum(e["gold"].split(" / ")[0] in e["set_category"] for e in cat_err)
    pri_in_set = sum(e["gold"].split(" / ")[1] in e["set_priority"] for e in pri_err)
    cat_pairs = Counter((e["gold"].split(" / ")[0], e["pred"].split(" / ")[0]) for e in cat_err).most_common(
        3
    )
    pri_pairs = Counter((e["gold"].split(" / ")[1], e["pred"].split(" / ")[1]) for e in pri_err).most_common(
        3
    )
    pm = oof["per_model_official"]
    pooled = test["pooled"]
    by_lang = pooled["by_lang"]
    fmt = ", ".join
    return [
        "## Findings",
        "",
        "- **Category is the weak target.** OOF category macro-F1 is "
        f"{oof['official']['category']['macro_f1']:.3f}"
        f" (M2-LR alone {pm['m2lr']['category']['macro_f1']:.3f}, M1 {pm['m1']['category']['macro_f1']:.3f}, "
        f"kNN {pm['m2knn']['category']['macro_f1']:.3f}). With one group per category held out, each fold "
        "learns a category from about 4 scenarios, and TF-IDF does not transfer to unseen scenarios at all. "
        "More scenarios (P2 augmentation) are the main lever; tuned weights (P2.7) are the second.",
        f"- **Arabic lags English.** OOF category macro-F1: ar "
        f"{oof['by_lang_script_official']['ar']['category']['macro_f1']:.3f} vs en "
        f"{oof['by_lang_script_official']['en']['category']['macro_f1']:.3f}; our_test: ar "
        f"{by_lang['ar']['category']['macro_f1']:.3f} vs en {by_lang['en']['category']['macro_f1']:.3f}. "
        "A held-out Arabic scenario is usually held out with its English translation (same cv_group), "
        "so the Arabic side has the fewest same-language examples.",
        f"- **Category errors cluster on one label.** Top confusions (gold → predicted): "
        f"{fmt(f'{a} → {b} ({n})' for (a, b), n in cat_pairs)}. "
        f"{cat_in_set} of {len(cat_err)} category errors still have the gold label inside the conformal set, "
        "so the ask/LLM path (P3) has the right candidates.",
        f"- **Priority sets never widen.** Mean priority set size on our_test is "
        f"{pooled['conformal']['priority']['mean_set_size']:.2f} and coverage "
        f"{pooled['conformal']['priority']['coverage']:.3f} (target 0.90); {pri_in_set} of {len(pri_err)} "
        "priority errors have the gold label in the set. "
        "The head is calibrated on OOF data where the lexicon "
        "features separate priority almost perfectly, so it is over-confident on new phrasing. "
        f"Top confusions: {fmt(f'{a} → {b} ({n})' for (a, b), n in pri_pairs)}. P2 recalibration must fix "
        "this (e.g. calibrate on augmented scenarios, or `alpha_priority_fallback`).",
        f"- **Arabizi priority is weak** (macro-F1 {by_lang['arabizi']['priority']['macro_f1']:.3f} on "
        f"{by_lang['arabizi']['rows']} rows): no Arabizi was trained on yet "
        "(the P1.9 rows await the human check).",
        f"- **The head is what makes priority work:** OOF priority macro-F1 "
        f"{oof['priority_stages_official']['members_average']['macro_f1']:.3f} for the members' average, "
        f"{oof['priority_stages_official']['head']['macro_f1']:.3f} after the head, "
        f"{oof['priority_stages_official']['head_plus_safety_floor']['macro_f1']:.3f} with the safety floor.",
        "",
    ]


CAVEATS = """## Caveats (read before quoting any number)

- **Thin data, wide error bars (LD-32).** The 432 official rows are 42 distinct texts in 30 scenario groups
  (9 to 11 wrapper variants each). Each OOF fold holds out one group per category, so each category is learned
  from about 4 groups. The effective sample size is about 30 groups, not 432 rows: read every OOF number as
  roughly plus or minus 0.1, and treat no difference between models here as significant.
- **Conformal coverage is approximate.** The quantiles are calibrated on the OOF scores of those same 30
  groups, so the 90 % guarantee holds only loosely, and OOF coverage is in-sample for the quantile.
- **Our test sets were written by an LLM (D-010).** Their scenarios are unseen, but their phrasing and labels
  follow `docs/reference/label_decisions.md` as an LLM read it, not the organizers' labeller.
- **The "today" shortcut (LD-34).** In the official data every row with "today"/"اليوم" is high and no other
  row is. The `deadline_today` feature and the head learn that, so priority scores on data with the same cue
  are optimistic. The P2.5 probes break the shortcut and P2.9 masks it.
- **The priority lexicons were written after reading every official row.** The evidence patterns
  (`urgency.yaml`) and the danger lexicon (`safety.yaml`) were seeded from the official cores of all folds,
  so OOF priority is not fully held out from the lexicons. The our_test sets are the cleaner check.
- **Provisional configuration.** Equal ensemble weights and mid-grid C; P2.7 tunes both on OOF only. With
  equal weights the weak M1 member pulls the ensemble's category score below M2-LR alone.
- **No augmentation yet.** The 30 Arabizi rule rows await the human check (P1.9), so no Arabizi was trained
  on; Arabizi results rely on the transliteration and the Arabizi lexicon patterns.
"""


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model-dir", type=Path, default=MODELS_FROZEN)
    ap.add_argument("--out", type=Path, default=REPORTS)
    args = ap.parse_args(argv)
    model_dir = resolve_model_dir(args.model_dir)
    oof, oof_models = oof_section(model_dir)
    test, test_models, container = our_test_section(model_dir)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    res = {
        "artifact_version": container.config.artifact_version,
        "sha": container.manifest.sha,
        "generated_at": generated_at,
        "oof": oof,
        "our_test": test,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        res, indent=2, ensure_ascii=False, sort_keys=True, default=lambda o: sorted(o.labels)
    )
    (args.out / "results_v1.json").write_text(payload + "\n", encoding="utf-8", newline="\n")
    (args.out / "results_v1.md").write_text(markdown(res), encoding="utf-8", newline="\n")
    lab = model_lab(oof_models, test_models, generated_at, test["pooled"]["conformal"]["ask_proxy_rate"])
    (args.out / "model_lab.json").write_text(
        json.dumps(lab, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    pooled = test["pooled"]
    print(
        f"OOF official cat macroF1={oof['official']['category']['macro_f1']:.3f} "
        f"pri macroF1={oof['official']['priority']['macro_f1']:.3f}; our_test pooled cat macroF1="
        f"{pooled['category']['macro_f1']:.3f} pri macroF1={pooled['priority']['macro_f1']:.3f}; "
        f"wrote {args.out / 'results_v1.md'}, results_v1.json, model_lab.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
