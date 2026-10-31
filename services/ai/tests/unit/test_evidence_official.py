"""Evidence features on the official rows and on Arabizi (P1.12 extras beyond the 22 acceptance tests)."""

from __future__ import annotations

import csv

import pytest

from campuspulse_ai.adapters.models.evidence import LexiconEvidenceExtractor
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import DATA_CLEAN, LEXICONS
from campuspulse_ai.domain.priority_rules import EVIDENCE_FEATURES, evidence_row
from campuspulse_ai.domain.values import Lang

HIGH_CUES = ("deadline_today", "exam_now", "safety_risk", "stranded", "enrollment_blocked")
NORMALIZER = DefaultNormalizer.from_lexicons(LEXICONS, 256)
EXTRACTOR = LexiconEvidenceExtractor.from_yaml(LEXICONS / "urgency.yaml")


@pytest.fixture(scope="module")
def official() -> list[tuple[dict[str, str], dict[str, bool]]]:
    with (DATA_CLEAN / "train_val_combined.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [(r, dict(EXTRACTOR.extract(NORMALIZER.normalize(r["text"])).flags)) for r in rows]


def test_wrappers_never_change_flags(official: list[tuple[dict[str, str], dict[str, bool]]]) -> None:
    per_scenario: dict[str, set[tuple[bool, ...]]] = {}
    for row, flags in official:
        per_scenario.setdefault(row["scenario_id"], set()).add(tuple(flags.values()))
    assert len(per_scenario) == 42 and all(len(v) == 1 for v in per_scenario.values())


Official = list[tuple[dict[str, str], dict[str, bool]]]


def test_high_cues_separate_official_priorities(official: Official) -> None:
    for row, flags in official:
        has_cue = any(flags[c] for c in HIGH_CUES)
        assert has_cue == (row["priority"] == "high"), (row["scenario_id"], row["text_norm"])
        if row["priority"] == "low":
            assert flags["info_request"] or flags["ambient_fixture"], row["scenario_id"]
        if row["priority"] == "medium":
            assert not flags["info_request"], row["scenario_id"]


ARABIZI = (
    ("deadline_today", "el tasjeel bisakker elyom w ana msh msajjal"),
    ("exam_now", "el moodle wa2ef w ana b nos el emte7an"),
    ("stranded", "dallo el tolab bdoon mwasalat"),
    ("enrollment_blocked", "shalooni mn el mada bdoon ma y7koli"),
    ("transient_glitch", "el site m3alla2a w bati2 kteer"),
    ("info_request", "wein bala2i jadwal el emte7anat?"),
    ("fault_report", "el projector bel 2a3a 5arban"),
    ("teaching_room", "el projector bel 2a3a 5arban"),
)


@pytest.mark.parametrize(("feature", "text"), ARABIZI)
def test_arabizi_positives(feature: str, text: str) -> None:
    req = NORMALIZER.normalize(text)
    assert req.lang is Lang.ARABIZI
    ev = EXTRACTOR.extract(req)
    assert ev.flags[feature], (text, {k for k, v in ev.flags.items() if v})


def test_info_request_needs_no_fault_and_evidence_row() -> None:
    ev = EXTRACTOR.extract(NORMALIZER.normalize("Where is the bus? It is twenty minutes late"))
    assert ev.flags["fault_report"] and not ev.flags["info_request"]
    row = evidence_row(ev.flags)
    assert len(row) == len(EVIDENCE_FEATURES) and set(row) <= {0.0, 1.0}
    assert row[EVIDENCE_FEATURES.index("fault_report")] == 1.0
    with pytest.raises(ValueError):
        evidence_row(ev.flags, (*EVIDENCE_FEATURES, "stated_urgency"))
