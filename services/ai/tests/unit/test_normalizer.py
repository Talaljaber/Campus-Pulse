"""DefaultNormalizer (P1.3): the Normalizer port used by every path."""

from __future__ import annotations

import pandas as pd
import pytest
import yaml

from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.values import Lang, Location

TRAIN_YAML = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
MAX_TOKENS = int(TRAIN_YAML["guards"]["max_tokens"])


@pytest.fixture(scope="module")
def normalizer() -> DefaultNormalizer:
    return DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)


def test_empty_raises_invalid_input(normalizer: DefaultNormalizer) -> None:
    for raw in ("", "   ", "\n\t"):
        with pytest.raises(InvalidInput):
            normalizer.normalize(raw)


def test_truncation_flag() -> None:
    small = DefaultNormalizer.from_lexicons(LEXICONS, max_tokens=3)
    req = small.normalize("URGENT: the bus is very late today")
    assert req.truncated is True
    assert req.core == "the bus is"
    assert req.text_norm == "the bus is"
    assert req.stated_urgency is True
    assert small.normalize("the bus").truncated is False


def test_arabizi_model_text_has_both(normalizer: DefaultNormalizer) -> None:
    req = normalizer.normalize("Hi team, mesh 3arif wein el bus")
    assert req.lang is Lang.ARABIZI and req.is_arabizi is True
    assert req.text_norm == "mesh 3arif wein el bus"
    assert req.model_text == "مش عارف وين الباص | mesh 3arif wein el bus"


def test_picked_location_wins(normalizer: DefaultNormalizer) -> None:
    picked = Location(building="K", room=None, source="picked")
    assert normalizer.normalize("The projector in M 214 is broken", picked_location=picked).location == picked


def test_room_extraction(normalizer: DefaultNormalizer) -> None:
    room = normalizer.normalize("The projector in M 214 is broken").location
    assert room == Location("M", "M 214", "extracted")
    building = Location("M", None, "extracted")
    assert normalizer.normalize("البروجكتور بمبنى M مش شغال").location == building  # attached clitic
    assert normalizer.normalize("البروجكتور في مبنى M مش شغال").location == building
    assert normalizer.normalize("A hallway light is broken").location is None


def test_official_text_norm_unaffected_by_location(normalizer: DefaultNormalizer) -> None:
    path = DATA_CLEAN / "train_val_combined.csv"
    official = pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False)
    no_location = DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS, with_location=False)
    mismatches = []
    for row in official.itertuples():
        req = normalizer.normalize(row.text)
        bare = no_location.normalize(row.text)
        same = (req.core, req.text_norm, req.model_text) == (bare.core, bare.text_norm, bare.model_text)
        if not same or (req.core, req.text_norm, req.lang.value) != (row.core, row.text_norm, row.lang):
            mismatches.append(row.request_id)
    assert mismatches == []
