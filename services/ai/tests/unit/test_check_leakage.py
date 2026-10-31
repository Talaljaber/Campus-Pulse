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


# --- P2.1: the pool mode (augmentation + holdouts) -----------------------------------------------------


def _pool_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "request_id": ["TR-0001", "TR-0002", "AUG-PA-0001", "AUG-NS-0001"],
            "text_norm": ["the bus is late", "my wifi is down", "the bus is late", "the bus is very late"],
            "model_text": ["the bus is late", "my wifi is down", "the bus is late", "the bus is very late"],
            "cv_group": ["G1", "G2", "NEW-S01", "NEW-S02"],
            "source": ["official", "official", "llm_paraphrase", "new_scenario"],
            "is_official": [True, True, False, False],
        }
    )


def test_exact_duplicate_across_groups_detected() -> None:
    leak = _load()
    frame = _pool_frame()
    assert leak.exact_cross_group(frame) == [("the bus is late", "G1", "NEW-S01")]
    same_group = frame.assign(cv_group=["G1", "G2", "G1", "NEW-S02"])
    assert leak.exact_cross_group(same_group) == []  # a paraphrase in its source's group is fine


def test_near_pairs_listed_with_hashing_encoder() -> None:
    from campuspulse_ai.adapters.models.hashing_encoder import HashingEncoder

    leak = _load()
    frame = _pool_frame()
    encoder = HashingEncoder(dim=384, seed=42)
    emb = leak._embed(encoder, frame["model_text"].tolist())
    pairs = leak.near_pairs(frame, emb, 0.5)
    assert pairs, "the 'bus is late' texts are near each other"
    assert all(p.group_a != p.group_b and p.sim >= 0.5 for p in pairs)
    assert all("wifi" not in p.text_a + p.text_b for p in pairs)
    text = "the bus is very late"
    holdout = pd.DataFrame({"request_id": ["T2-0001"], "text_norm": [text], "model_text": [text]})
    hold_emb = leak._embed(encoder, holdout["model_text"].tolist())
    found = leak.holdout_near(frame, emb, holdout, hold_emb, encoder_threshold=0.9, char_threshold=0.8)
    exact = [(p.holdout_id, p.pool_id, p.pool_is_official) for p in found if p.measure == "exact"]
    assert exact == [("T2-0001", "AUG-NS-0001", False)]
    assert any(p.measure == "char" and not p.pool_is_official for p in found)
