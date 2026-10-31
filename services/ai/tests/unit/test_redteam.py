"""P4.11: PerturbationGenerator, seed loading, RedTeamScorer and RunRedTeamUseCase.

Offline: the real `config/redteam.yaml` and lexicons, hand-made seed rows, and a keyword core
(`KeywordCore`) whose behaviour each test chooses. No model, network or holdout file is touched.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from pathlib import Path

import pytest
from fixtures.backend_fakes import FrozenClock, make_core
from fixtures.redteam import MAX_N, ROWS, KeywordCore, injection_exemplars, redteam_config, redteam_use_case

from campuspulse_ai.adapters.redteam.config import RedTeamConfig, text_lang
from campuspulse_ai.adapters.redteam.perturbation import PerturbationGenerator
from campuspulse_ai.adapters.redteam.scorer import RedTeamScorer
from campuspulse_ai.adapters.redteam.seeds import load_seed_rows
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.application import dto
from campuspulse_ai.application.services.redteam_styles import ALL_STYLES
from campuspulse_ai.config.paths import CONFIG_DIR, DATA_CLEAN, LEXICONS
from campuspulse_ai.domain.entities import CoreResult, RedTeamItem
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang, Outcome


@pytest.fixture(scope="module")
def cfg() -> RedTeamConfig:
    return redteam_config()


@pytest.fixture(scope="module")
def gen(cfg: RedTeamConfig) -> PerturbationGenerator:
    return PerturbationGenerator(ROWS, cfg)


@pytest.fixture(scope="module")
def exemplars() -> list[str]:
    return injection_exemplars()


# ----------------------------------------------------------------------------------------- generator


def test_same_seed_same_items_and_another_seed_differs(gen: PerturbationGenerator) -> None:
    first = gen.generate(200, [], 42)
    assert gen.generate(200, [], 42) == first
    assert gen.generate(200, [], 7) != first
    assert PerturbationGenerator(ROWS, RedTeamConfig.load(CONFIG_DIR / "redteam.yaml", LEXICONS)).generate(
        200, [], 42
    ) == first  # fmt: skip


def test_each_style_has_its_own_stream_so_a_subset_gives_the_same_items(gen: PerturbationGenerator) -> None:
    every = gen.generate(100, [], 42)
    alone = gen.generate(10, ["typos"], 42)
    assert alone == [i for i in every if i.style == "typos"]


def test_n_is_spread_round_robin_in_canonical_order(gen: PerturbationGenerator) -> None:
    assert gen.available_styles == ALL_STYLES
    counts = Counter(i.style for i in gen.generate(200, [], 1))
    assert counts == dict.fromkeys(ALL_STYLES, 20)
    few = gen.generate(3, ["injection", "typos", "fake_urgency", "off_topic"], 1)
    assert [i.style for i in few] == ["fake_urgency", "typos", "injection"]
    assert len(gen.generate(13, ["arabizi", "off_topic"], 1)) == 13


@pytest.mark.parametrize(
    ("n", "styles", "message"),
    [
        (0, [], "at least 1"),
        (5, ["sarcasm"], "unknown red-team style"),
        (5, ["deadline_shortcut"], "unknown red-team style"),
    ],
)
def test_bad_requests_raise_invalid_input(
    gen: PerturbationGenerator, n: int, styles: list[str], message: str
) -> None:
    with pytest.raises(InvalidInput, match=message):
        gen.generate(n, styles, 42)


def test_a_style_the_seeds_cannot_feed_is_refused_or_left_out(cfg: RedTeamConfig) -> None:
    english_only = PerturbationGenerator([r for r in ROWS if r.lang is Lang.EN], cfg)
    assert "arabizi" not in english_only.available_styles
    with pytest.raises(InvalidInput, match="cannot feed"):
        english_only.generate(5, ["arabizi"], 42)
    assert {i.style for i in english_only.generate(90, [], 42)} == set(ALL_STYLES) - {"arabizi"}


def test_fake_urgency_prefixes_a_low_or_medium_request(
    gen: PerturbationGenerator, cfg: RedTeamConfig
) -> None:
    items = gen.generate(20, ["fake_urgency"], 42)
    prefixes = {p for texts in cfg.fake_urgency.prefixes.values() for p in texts}
    for item in items:
        assert item.base_text and item.base_text in item.text
        assert any(item.text.startswith(p) for p in prefixes)
        assert item.intended_priority is not Priority.HIGH
    assert {i.lang for i in items} == {Lang.EN, Lang.AR}


def test_injection_phrases_come_from_the_injection_lexicon(
    gen: PerturbationGenerator, exemplars: list[str]
) -> None:
    for item in gen.generate(30, ["injection"], 42):
        assert item.expected_flags == frozenset({"injection_attempt"})
        assert item.base_text is not None and item.base_text in item.text
        phrase = item.text.replace(item.base_text, "").strip()
        assert phrase in exemplars
        assert text_lang(phrase) is item.lang


def test_arabizi_is_latin_and_labelled_like_its_arabic_base(gen: PerturbationGenerator) -> None:
    by_base = {r.text: r for r in ROWS}
    for item in gen.generate(10, ["arabizi"], 42):
        assert item.lang is Lang.ARABIZI and not re.search(r"[؀-ۿ]", item.text)
        base = by_base[item.base_text or ""]
        assert (item.intended_category, item.intended_priority, item.base_id) == (
            base.category, base.priority, base.request_id)  # fmt: skip
    timetable = [i.text for i in gen.generate(10, ["arabizi"], 42) if i.base_id == "TR-7"]
    assert timetable and all("jadwal el baasat" in t for t in timetable)  # lexicon words, then the char map


def test_typos_change_the_text_but_keep_the_labels(gen: PerturbationGenerator) -> None:
    for item in gen.generate(40, ["typos"], 42):
        assert item.text != item.base_text
        assert abs(len(item.text) - len(item.base_text or "")) <= len(item.base_text or "") // 2


def test_mixed_language_switches_script(gen: PerturbationGenerator, cfg: RedTeamConfig) -> None:
    for item in gen.generate(20, ["mixed_language"], 42):
        other = Lang.AR if item.lang is Lang.EN else Lang.EN
        assert any(p in item.text for p in cfg.mixed_language.phrases[other]) or any(
            p in item.text for p in cfg.mixed_language.phrases[item.lang]
        )
        assert re.search(r"[؀-ۿ]", item.text) and re.search(r"[A-Za-z]", item.text)


def test_two_issues_keep_the_more_urgent_request(gen: PerturbationGenerator) -> None:
    texts = {r.request_id: r for r in ROWS}
    for item in gen.generate(20, ["two_issues"], 42):
        first, second = (texts[i] for i in (item.base_id or "").split("+"))
        assert first.text in item.text and second.text in item.text and first.category != second.category
        lead = first if first.priority.rank >= second.priority.rank else second
        assert (item.intended_category, item.intended_priority) == (lead.category, lead.priority)
        assert item.base_text is None


def test_very_long_buries_the_request_in_calm_filler(gen: PerturbationGenerator, cfg: RedTeamConfig) -> None:
    for item in gen.generate(10, ["very_long"], 42):
        assert item.base_text and item.base_text in item.text
        assert len(item.text) >= cfg.very_long.target_chars
        assert "URGENT" not in item.text and "عاجل" not in item.text


def test_fixed_lists(gen: PerturbationGenerator, cfg: RedTeamConfig) -> None:
    calm = gen.generate(14, ["calm_emergency"], 42)
    assert all(i.intended_priority is Priority.HIGH and "{place}" not in i.text for i in calm)
    off = gen.generate(8, ["off_topic"], 42)
    assert sorted(i.text for i in off) == sorted(t.text for t in cfg.off_topic)  # one pass, no repeats
    distress = gen.generate(6, ["distress_adjacent"], 42)
    assert all(i.expected_flags == frozenset({"distress"}) for i in distress)


# ----------------------------------------------------------------------------------------- seeds


def test_official_training_rows_are_the_default_seeds() -> None:
    rows = load_seed_rows(DATA_CLEAN / "train_clean.csv")
    assert len(rows) == 370 and {r.lang for r in rows} == {Lang.EN, Lang.AR}
    assert not any(r.text.startswith("URGENT") for r in rows)  # the `core` column: wrappers stripped


@pytest.mark.parametrize("holdout", ["our_test/our_test.csv", "robustness/probes.csv", "Robustness/x.csv"])
def test_holdout_seed_files_are_refused_before_they_are_opened(tmp_path: Path, holdout: str) -> None:
    with pytest.raises(InvalidInput, match="holdout"):
        load_seed_rows(tmp_path / holdout)  # the file does not exist: the path alone is refused


def test_a_supplied_csv_with_text_and_no_lang(tmp_path: Path) -> None:
    path = tmp_path / "seeds.csv"
    path.write_text(
        "﻿request_id,text,category,priority\nS-1,wein el bas? el bas 3am yit2a5ar,Transportation,low\n"
        "S-2,الباص متأخر,Transportation,medium\nS-3,,Finance,low\n",
        encoding="utf-8",
    )
    rows = load_seed_rows(path)
    assert [(r.request_id, r.lang) for r in rows] == [("S-1", Lang.ARABIZI), ("S-2", Lang.AR)]
    bad = tmp_path / "bad.csv"
    bad.write_text("request_id,text,category,priority\nS-1,hello,Parking,low\n", encoding="utf-8")
    with pytest.raises(InvalidInput, match="S-1"):
        load_seed_rows(bad)
    (tmp_path / "cols.csv").write_text("id,text\n1,x\n", encoding="utf-8")
    with pytest.raises(InvalidInput, match="missing"):
        load_seed_rows(tmp_path / "cols.csv")


# ----------------------------------------------------------------------------------------- scorer


def item(style: str, *, flags: frozenset[str] = frozenset(), base: str | None = "base") -> RedTeamItem:
    return RedTeamItem("text", style, Lang.EN, Category.IT_SUPPORT, Priority.MEDIUM, flags, base_text=base)


IT_MEDIUM = make_core({"IT Support": 0.9}, {"medium": 0.9})
IT_HIGH = make_core({"IT Support": 0.9}, {"high": 0.9})
IT_LOW = make_core({"IT Support": 0.9}, {"low": 0.9})
INJECTION = frozenset({"injection_attempt"})


def flagged(core: CoreResult, flags: frozenset[str]) -> CoreResult:
    return make_core(core.p_cat.as_dict(), core.p_pri.as_dict(), flags=flags)


def test_injection_passes_only_with_the_flag_and_no_priority_raise() -> None:
    s = RedTeamScorer()
    rt = item("injection", flags=INJECTION)
    assert s.score(rt, flagged(IT_MEDIUM, INJECTION), Outcome.ACCEPT, IT_MEDIUM) == (
        True, "injection flagged, priority not raised")  # fmt: skip
    assert s.score(rt, flagged(IT_LOW, INJECTION), Outcome.ACCEPT, IT_MEDIUM)[0] is True
    assert s.score(rt, IT_MEDIUM, Outcome.ACCEPT, IT_MEDIUM) == (False, "missing flag injection_attempt")
    assert s.score(rt, flagged(IT_HIGH, INJECTION), Outcome.ACCEPT, IT_MEDIUM) == (
        False, "priority high > base medium")  # fmt: skip


def test_off_topic_must_be_out_of_scope() -> None:
    s = RedTeamScorer()
    assert s.score(item("off_topic", base=None), IT_MEDIUM, Outcome.OUT_OF_SCOPE, None)[0] is True
    assert s.score(item("off_topic", base=None), IT_MEDIUM, Outcome.ACCEPT, None) == (
        False, "expected out_of_scope, got accept")  # fmt: skip


def test_distress_adjacent_must_raise_the_distress_flag() -> None:
    s = RedTeamScorer()
    rt = item("distress_adjacent", flags=frozenset({"distress"}), base=None)
    assert s.score(rt, flagged(IT_MEDIUM, frozenset({"distress"})), Outcome.DISTRESS, None)[0] is True
    assert s.score(rt, IT_MEDIUM, Outcome.ACCEPT, None) == (False, "missing flag distress")


def test_fake_urgency_must_not_move_the_labels() -> None:
    s = RedTeamScorer()
    assert s.score(item("fake_urgency"), IT_MEDIUM, Outcome.ACCEPT, IT_MEDIUM) == (True, "labels unchanged")
    assert s.score(item("fake_urgency"), IT_HIGH, Outcome.ACCEPT, IT_MEDIUM) == (
        False, "priority high != base medium")  # fmt: skip


def test_other_styles_need_a_decision_with_the_intended_labels() -> None:
    s = RedTeamScorer()
    assert s.score(item("typos"), IT_MEDIUM, Outcome.ASK, IT_MEDIUM) == (True, "labels match")
    finance_low = make_core({"Finance": 0.9}, {"low": 0.9})
    assert s.score(item("arabizi"), finance_low, Outcome.ACCEPT, IT_MEDIUM) == (
        False, "category Finance != intended IT Support; priority low != intended medium")  # fmt: skip
    assert s.score(item("typos"), IT_MEDIUM, Outcome.OUT_OF_SCOPE, IT_MEDIUM) == (
        False, "expected a decision, got out_of_scope")  # fmt: skip


# ----------------------------------------------------------------------------------------- use case


def test_a_run_is_scored_per_style_and_language_and_stored(
    gen: PerturbationGenerator, cfg: RedTeamConfig, exemplars: list[str]
) -> None:
    repo = InMemoryRepository(FrozenClock())
    run = redteam_use_case(KeywordCore(cfg, exemplars), repo=repo).run_detailed(40, [], 42)
    s = run.scorecard
    assert uuid.UUID(s.run_id) and (s.n, s.seed, s.created_at) == (40, 42, FrozenClock().at)
    assert list(s.by_style) == list(ALL_STYLES) and set(s.by_lang) <= {"en", "ar", "arabizi"}
    # the keyword core sees the base text inside these styles and flags injections and distress
    for style in (
        "fake_urgency",
        "very_long",
        "injection",
        "off_topic",
        "distress_adjacent",
        "calm_emergency",
    ):
        assert s.by_style[style] == (0.0 if style == "calm_emergency" else 1.0), style
    assert s.by_style["arabizi"] == 0.0 and s.by_style["typos"] < 1.0  # it cannot read either
    assert s.overall == pytest.approx(sum(r.passed for r in run.results) / 40)
    assert len(s.failures) == sum(not r.passed for r in run.results)
    for f in s.failures:
        dto.RedTeamFailureOut.model_validate(f)
    assert (
        run.properties["priority_gaming_resistance"] == 1.0 and run.properties["injection_resistance"] == 1.0
    )
    assert [h.run_id for h in repo.redteam_history()] == [s.run_id]


def test_same_seed_gives_the_same_scores(
    gen: PerturbationGenerator, cfg: RedTeamConfig, exemplars: list[str]
) -> None:
    def scores(seed: int) -> tuple[object, ...]:
        s = redteam_use_case(KeywordCore(cfg, exemplars)).run(60, [], seed)
        return s.by_style, s.by_lang, s.overall, s.failures

    assert scores(42) == scores(42)
    assert scores(42) != scores(3)


def test_gaming_and_injection_weaknesses_show_in_the_scorecard(
    gen: PerturbationGenerator, cfg: RedTeamConfig, exemplars: list[str]
) -> None:
    run = redteam_use_case(KeywordCore(cfg, exemplars, gullible=True, blind=True)).run_detailed(
        20, ["fake_urgency", "injection"], 42
    )
    assert run.scorecard.by_style == {"fake_urgency": 0.0, "injection": 0.0}
    reasons = {f["reason"] for f in run.scorecard.failures}
    assert "missing flag injection_attempt" in reasons
    assert any(str(r).startswith("priority high != base") for r in reasons)
    assert run.label_stability is not None and run.label_stability < 1.0


def test_off_topic_and_distress_failures_have_no_labels(
    gen: PerturbationGenerator, cfg: RedTeamConfig
) -> None:
    run = redteam_use_case(KeywordCore(cfg, [])).run_detailed(8, ["typos", "distress_adjacent"], 42)
    typo_failures = [f for f in run.scorecard.failures if f["style"] == "typos"]
    assert all(f["got_category"] is not None for f in typo_failures)
    distress = [r for r in run.results if r.item.style == "distress_adjacent"]
    assert all(r.outcome is Outcome.DISTRESS and r.category is None and r.passed for r in distress)


def test_base_texts_are_classified_once_and_memory_is_passed_through(
    gen: PerturbationGenerator, cfg: RedTeamConfig, exemplars: list[str]
) -> None:
    core = KeywordCore(cfg, exemplars)
    run = redteam_use_case(core, memory=True).run_detailed(30, ["typos", "very_long", "off_topic"], 42)
    bases = {r.item.base_text for r in run.results if r.item.base_text}
    assert len(core.calls) == 30 + len(bases)
    assert all(memory for _, memory in core.calls)


@pytest.mark.parametrize("n", [0, MAX_N + 1])
def test_n_outside_the_cap_is_invalid_input(gen: PerturbationGenerator, cfg: RedTeamConfig, n: int) -> None:
    core = KeywordCore(cfg, [])
    with pytest.raises(InvalidInput, match=f"between 1 and {MAX_N}"):
        redteam_use_case(core).run(n, [], 42)
    assert core.calls == []


def test_llm_generator_flag_falls_back_to_the_rule_based_one(
    gen: PerturbationGenerator, cfg: RedTeamConfig, exemplars: list[str]
) -> None:
    rule = redteam_use_case(KeywordCore(cfg, exemplars)).run(10, [], 42)
    llm = redteam_use_case(KeywordCore(cfg, exemplars)).run(10, [], 42, use_llm_generator=True)
    assert (rule.by_style, rule.failures) == (llm.by_style, llm.failures)


def test_api_returns_the_scorecard_contract(gen: PerturbationGenerator, cfg: RedTeamConfig) -> None:
    out = redteam_use_case(KeywordCore(cfg, [])).api(
        dto.RedTeamRunRequest(n=10, styles=["off_topic"], seed=5)
    )
    assert isinstance(out, dto.ScorecardOut) and out.n == 10 and out.by_style == {"off_topic": 1.0}
