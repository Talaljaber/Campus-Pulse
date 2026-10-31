"""The leakage gate fires on planted leakage (scripts/check_leakage.py, P0.3e)."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pandas as pd

from campuspulse_ai.config.paths import REPO_ROOT


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_leakage", REPO_ROOT / "scripts" / "check_leakage.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


FRAME = pd.DataFrame(
    {
        "text_norm": [
            "the bus is late",
            "the bus is late",
            "the bus is very late today",
            "how do i reset my password",
        ],
        "cv_group": ["G1", "G2", "G3", "G4"],
    }
)


def test_identical_text_across_groups_is_reported() -> None:
    leak = _load()
    assert leak.exact_cross_group(FRAME) == [("the bus is late", "G1", "G2")]


def test_near_pairs_respect_threshold_and_skip_same_group() -> None:
    leak = _load()
    same_group = FRAME.assign(cv_group=["G1", "G1", "G1", "G4"])
    assert leak.char_near_pairs(same_group, 0.5) == []
    pairs = leak.char_near_pairs(FRAME, 0.5)
    assert pairs and all(p.group_a != p.group_b and p.sim >= 0.5 for p in pairs)
    assert leak.max_cross_group_cosine(FRAME) >= pairs[0].sim


def test_official_data_is_clean() -> None:
    leak = _load()
    assert leak.main(["--official"]) == 0
