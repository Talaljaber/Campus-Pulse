"""GibberishGuard (P1.5): noise is flagged, the 432 official rows are not."""

from __future__ import annotations

import pandas as pd
import yaml

from campuspulse_ai.adapters.guards.gibberish import GibberishGuard
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS
from campuspulse_ai.domain.values import Lang, NormalizedRequest

GUARDS_CFG = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))["guards"]


def _guard() -> GibberishGuard:
    return GibberishGuard(GUARDS_CFG["gibberish_min_tokens"], GUARDS_CFG["gibberish_min_letter_ratio"])


def _req(text: str) -> NormalizedRequest:
    # built directly: the normalizer rejects "" and "???" before any guard runs (InvalidInput, LD-17)
    return NormalizedRequest(raw=text, core=text, text_norm=text, model_text=text, lang=Lang.EN,
                             is_arabizi=False, stated_urgency=False, truncated=False)


def test_flags_noise() -> None:
    guard = _guard()
    for text in ("", "???", "asdf;;;;", "!!!! ####", "7777 8888", "x"):
        assert guard.inspect(_req(text)).kind == "gibberish", text
    for text in ("the wifi is down", "وين جدول الباصات", "mesh 3arif wein el bus"):
        assert guard.inspect(_req(text)).kind == "none", text


def test_zero_gibberish_on_432_official() -> None:
    guard = _guard()
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, GUARDS_CFG["max_tokens"])
    df = pd.read_csv(DATA_CLEAN / "train_val_combined.csv", dtype=str, keep_default_na=False)
    flagged = [rid for rid, text in zip(df.request_id, df.text, strict=True)
               if guard.inspect(normalizer.normalize(text)).kind != "none"]
    assert len(df) == 432 and flagged == []
