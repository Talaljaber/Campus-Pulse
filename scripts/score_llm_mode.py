#!/usr/bin/env python3
"""Score the default predict.py mode (with the LLM, "G") on our test sets and the official validation file.

    python services/ai/predict.py --input data/our_test/our_test.csv \
        --output reports/llm_mode/predictions_our_test.csv
    python services/ai/predict.py --input data/raw/validation.csv \
        --output reports/llm_mode/predictions_validation.csv
    python scripts/score_llm_mode.py        # -> reports/llm_mode.json

`evaluate.py` scores the offline model only (no key, no network, reproducible). This script adds the default
mode next to it so the notebooks can show both. It reads only saved prediction files and gold labels; it never
calls a model. Macro-F1 with a 95% bootstrap interval (1000 resamples, seed 0), per dataset and per language.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parent.parent
PRED_DIR = ROOT / "reports" / "llm_mode"
OUT = ROOT / "reports" / "llm_mode.json"
CATEGORIES = ["Registration", "IT Support", "Finance", "Transportation", "Facilities", "Academic Support"]
PRIORITIES = ["low", "medium", "high"]
LANGS = ("en", "ar", "arabizi")
N_BOOT = 1000


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def _model_id() -> str:
    text = (ROOT / "config" / "llm_frontend.yaml").read_text(encoding="utf-8")
    m = re.search(r"^model:\s*(\S+)", text, re.M)
    return m.group(1) if m else "unknown"


def _f1(gold: np.ndarray, pred: np.ndarray, labels: list[str]) -> float:
    # Macro over the labels that occur in this slice (gold or predicted), like sklearn's default; a language
    # slice that has no row of some class would otherwise count that class as F1 = 0.
    present = [lab for lab in labels if lab in set(gold) | set(pred)]
    return float(f1_score(gold, pred, labels=present, average="macro", zero_division=0))


def _score(gold: pd.Series, pred: pd.Series, labels: list[str], rng: np.random.Generator) -> dict[str, float]:
    g, p = gold.to_numpy(), pred.to_numpy()
    n = len(g)
    boots = [_f1(g[idx], p[idx], labels) for idx in (rng.integers(0, n, n) for _ in range(N_BOOT))]
    return {
        "macro_f1": round(_f1(g, p, labels), 4),
        "accuracy": round(float(accuracy_score(g, p)), 4),
        "ci_low": round(float(np.percentile(boots, 2.5)), 4),
        "ci_high": round(float(np.percentile(boots, 97.5)), 4),
        "n_rows": n,
    }


def _confusion(gold: pd.Series, pred: pd.Series, labels: list[str]) -> dict[str, object]:
    return {"labels": labels, "matrix": confusion_matrix(gold, pred, labels=labels).tolist()}


def _join(gold: pd.DataFrame, pred_path: Path) -> pd.DataFrame:
    pred = _read(pred_path)[["request_id", "category", "priority"]]
    df = gold.merge(pred, on="request_id", how="left", suffixes=("", "_pred"))
    missing = df["category_pred"].eq("") | df["category_pred"].isna()
    if missing.any():
        sys.exit(f"{pred_path.name}: {int(missing.sum())} labelled rows have no prediction")
    return df


def main() -> int:
    rng = np.random.default_rng(0)
    gold = _read(ROOT / "data" / "our_test" / "our_test.csv")
    our_test = _join(gold, PRED_DIR / "predictions_our_test.csv")
    validation = _read(ROOT / "data" / "raw" / "validation.csv")
    validation["lang"] = ""
    validation["test_set"] = ""
    validation = _join(validation, PRED_DIR / "predictions_validation.csv")

    slices: list[tuple[str, pd.DataFrame]] = [("our_test", our_test)]
    for test_set in sorted(our_test.test_set.unique()):
        slices.append((f"our_test_{test_set}", our_test[our_test.test_set == test_set]))
    slices.append(("validation", validation))

    rows: list[dict[str, object]] = []
    confusions: dict[str, dict[str, object]] = {}
    for name, df in slices:
        for target, labels in (("category", CATEGORIES), ("priority", PRIORITIES)):
            rows.append({"dataset": name, "lang": "all", "target": target,
                         **_score(df[target], df[f"{target}_pred"], labels, rng)})
            if name.startswith("our_test"):
                confusions[f"{target}_{name}"] = _confusion(df[target], df[f"{target}_pred"], labels)
                for lang in LANGS:
                    part = df[df.lang == lang]
                    if len(part):
                        rows.append({"dataset": name, "lang": lang, "target": target,
                                     **_score(part[target], part[f"{target}_pred"], labels, rng)})

    report = {
        "mode": "default predict.py run with OPENROUTER_API_KEY (LLM front end + tie-breaker)",
        "llm_model": _model_id(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "bootstrap": {"resamples": N_BOOT, "seed": 0, "interval": 0.95},
        "scores": rows,
        "confusions": confusions,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    pooled = {r["target"]: r["macro_f1"] for r in rows if r["dataset"] == "our_test" and r["lang"] == "all"}
    print(f"wrote {OUT.relative_to(ROOT)} (our_test category {pooled['category']}, "
          f"priority {pooled['priority']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
