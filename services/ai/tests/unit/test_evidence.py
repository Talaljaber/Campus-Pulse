"""LexiconEvidenceExtractor (P1.12, ARCHITECTURE §3.8): positives per feature, order, no stated_urgency."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from fixtures.frozen_config import valid_config_dict

from campuspulse_ai.adapters.models.evidence import LexiconEvidenceExtractor
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, LEXICONS, REPO_ROOT
from campuspulse_ai.domain.ports import EvidenceExtractor
from campuspulse_ai.domain.priority_rules import EVIDENCE_FEATURES

FIXTURE_FILE = REPO_ROOT / "services" / "ai" / "tests" / "fixtures" / "evidence_fixtures.yaml"
FIXTURES: list[dict[str, Any]] = yaml.safe_load(FIXTURE_FILE.read_text(encoding="utf-8"))
NORMALIZER = DefaultNormalizer.from_lexicons(LEXICONS, 256)
EXTRACTOR = LexiconEvidenceExtractor.from_yaml(LEXICONS / "urgency.yaml")


@pytest.mark.parametrize("case", FIXTURES, ids=[f"{c['feature']}-{c['lang']}" for c in FIXTURES])
def test_feature_positive(case: dict[str, Any]) -> None:
    ev = EXTRACTOR.extract(NORMALIZER.normalize(case["text"]))
    assert ev.flags[case["feature"]], (case["text"], {k for k, v in ev.flags.items() if v})
    assert any(span.type == case["feature"] for span in ev.spans)


def test_stated_urgency_not_a_feature() -> None:
    assert "stated_urgency" not in EVIDENCE_FEATURES
    for base in ("The bus is late", "وين جدول الباصات", "The projector in room M214 is broken"):
        plain = NORMALIZER.normalize(base)
        urgent = NORMALIZER.normalize(f"URGENT: {base}")
        marker = NORMALIZER.normalize(f"عاجل!!! {base}")
        assert urgent.stated_urgency and not plain.stated_urgency
        assert EXTRACTOR.extract(urgent).flags == EXTRACTOR.extract(plain).flags
        assert EXTRACTOR.extract(marker).flags == EXTRACTOR.extract(plain).flags
        assert "stated_urgency" not in EXTRACTOR.extract(urgent).flags
    with pytest.raises(ValueError):
        LexiconEvidenceExtractor.from_yaml(LEXICONS / "urgency.yaml",
                                           features=(*EVIDENCE_FEATURES, "stated_urgency"))


def test_feature_order_matches_config() -> None:
    train = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
    assert tuple(train["priority_head"]["features"]) == EVIDENCE_FEATURES
    assert tuple(valid_config_dict()["priority_head"]["features"]) == EVIDENCE_FEATURES
    ev = EXTRACTOR.extract(NORMALIZER.normalize("The bus is late"))
    assert tuple(ev.flags) == EVIDENCE_FEATURES == EXTRACTOR.features
    assert isinstance(EXTRACTOR, EvidenceExtractor)
    assert len(EVIDENCE_FEATURES) == 10
