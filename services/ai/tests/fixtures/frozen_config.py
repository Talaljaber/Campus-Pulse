"""A valid `config.json` mapping for tests, assembled the way train.py will: copied sections from
config/train.yaml, hand-tuned thresholds from config/hand_tuned.yaml, and stand-in "learned" values.

The learned numbers below are test data only (not thresholds used by any code path).
"""

from __future__ import annotations

import copy
from typing import Any

import yaml

from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS


def valid_config_dict() -> dict[str, Any]:
    """A fresh, fully valid config mapping (safe to mutate)."""
    train = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
    hand = yaml.safe_load((CONFIG_DIR / "hand_tuned.yaml").read_text(encoding="utf-8"))
    members = list(train["ensemble"]["members"])
    even = {m: 1.0 / len(members) for m in members}
    # category-only members (m2proto, D-014) carry no priority weight
    pri_members = [m for m in members if m != "m2proto"]
    even_pri = {m: (1.0 / len(pri_members) if m in pri_members else 0.0) for m in members}
    config: dict[str, Any] = {
        "schema_version": 1,
        "artifact_version": train["artifact_version"],
        "trained_at": "2026-11-01T10:00:00+00:00",
        "seed": train["seed"],
        "encoder": {**train["encoder"], "revision": "test-revision"},
        "ensemble": {"members": members, "weights_category": even, "weights_priority": even_pri},
        "m1": {**train["m1"], "C": train["grids"]["m1_C"][0]},
        "m2lr": {"C": train["grids"]["m2lr_C"][0]},
        "knn": dict(train["knn"]),
        "priority_head": dict(train["priority_head"]),
        "conformal": {
            **train["conformal"],
            "alpha_category": train["alpha"]["category"],
            "alpha_priority": train["alpha"]["priority"],
            "q_category": 0.7,
            "q_priority": 0.6,
            "n_calib": 432,
        },
        "thresholds": {
            "tau_ood": 0.8,
            "tau_faq": hand["tau_faq"],
            "tau_inc": hand["tau_inc"],
            "tau_injection": 0.9,
            "tau_safety": 0.9,
            "human_review_maxprob": 0.5,
        },
        "guards": dict(train["guards"]),
        "llm": dict(train["llm"]),
        "explain": dict(train["explain"]),
        "priors": {
            "category": {c: 1.0 / len(CATEGORY_LABELS) for c in CATEGORY_LABELS},
            "priority": {"low": 0.25, "medium": 0.5, "high": 0.25},
        },
        "cv": {
            "k": train["cv"]["k"],
            "group_col": train["cv"]["group_col"],
            "fold_col": train["cv"]["fold_col"],
            "folds_file": train["cv"]["folds_file"],
            "oof_macro_f1_category": 0.9,
            "oof_macro_f1_priority": 0.8,
        },
    }
    if "m2proto" in members:
        proto = train["prototype"]
        config["prototype"] = {"parts": list(proto["parts"]), "mix": proto["mix"], "temperature": 0.02}
    assert set(config["priors"]["priority"]) == set(PRIORITY_LABELS)
    return copy.deepcopy(config)
