"""LocationExtractor edge cases and DefaultNormalizer port conformance (P1.3)."""

from __future__ import annotations

import pytest

from campuspulse_ai.adapters.preprocess.location import LocationExtractor
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import LEXICONS
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.ports import Normalizer
from campuspulse_ai.domain.values import Location


@pytest.fixture(scope="module")
def extractor() -> LocationExtractor:
    return LocationExtractor.from_yaml(LEXICONS / "gazetteer.yaml")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Room M-214 has no power", Location("M", "M 214", "extracted")),
        ("lab K305 projector", Location("K", "K 305", "extracted")),
        ("The AC in Building H is loud", Location("H", None, "extracted")),
        ("wifi down in the M building", Location("M", None, "extracted")),
        ("المكيف في مبنى H خربان", Location("H", None, "extracted")),
    ],
)
def test_extracts(extractor: LocationExtractor, text: str, expected: Location) -> None:
    assert extractor.extract(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "A hallway light is broken",  # official row: "A" is an article
        "I am in a building near the gate",  # lower-case code never matches
        "Block b printer is jammed",  # "B" of "Block" is not the code token
        "My ID is 214 and room I 214",  # I is not a building code
        "CS2140 lecture moved",
    ],
)
def test_no_false_locations(extractor: LocationExtractor, text: str) -> None:
    assert extractor.extract(text) is None


def test_normalizer_implements_port() -> None:
    assert isinstance(DefaultNormalizer.from_lexicons(LEXICONS, max_tokens=8), Normalizer)


def test_punctuation_only_is_invalid_input() -> None:
    with pytest.raises(InvalidInput):
        DefaultNormalizer.from_lexicons(LEXICONS, max_tokens=8).normalize(" ?! ؟ ")
