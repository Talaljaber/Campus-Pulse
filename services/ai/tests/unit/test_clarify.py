"""P3.2: the question bank and the expected-information-gain clarifier."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.backend_fakes import make_core

from campuspulse_ai.adapters.clarify.bank import TOPIC_QUESTION_ID, QuestionBank
from campuspulse_ai.adapters.clarify.info_gain import InfoGainStrategy, expected_set_size
from campuspulse_ai.domain.errors import InvalidInput, NotFound
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import ClarificationStrategy
from campuspulse_ai.domain.values import ClarificationConstraint, Lang

BANK_PATH = Path(__file__).resolve().parents[4] / "config" / "clarify_questions.yaml"
# FrozenConfig priority_head.features (ARCHITECTURE §1.6); production passes the frozen config's list.
EVIDENCE_FEATURES = (
    "deadline_today", "exam_now", "safety_risk", "stranded", "enrollment_blocked",
    "transient_glitch", "info_request", "fault_report", "ambient_fixture", "teaching_room",
)  # fmt: skip
REG, IT, FIN, ACA, FAC = "Registration", "IT Support", "Finance", "Academic Support", "Facilities"


@pytest.fixture(scope="module")
def bank() -> QuestionBank:
    return QuestionBank.load(BANK_PATH, features=EVIDENCE_FEATURES)


@pytest.fixture(scope="module")
def strategy(bank: QuestionBank) -> InfoGainStrategy:
    return InfoGainStrategy(bank)


def test_bank_loads_with_known_labels_and_topic(bank: QuestionBank) -> None:
    assert len(bank.questions) == 7
    ids = [q.id for q in bank.questions]
    assert ids[:4] == [f"cat:{REG}|{IT}", f"cat:{ACA}|{IT}", f"cat:{FIN}|{REG}", f"cat:{FAC}|{IT}"]
    assert set(ids[4:]) == {"pri:deadline", "pri:safety", "pri:low|medium"}
    for q in bank.questions:
        vocab = CATEGORY_LABELS if q.target == "category" else PRIORITY_LABELS
        assert q.split <= set(vocab) and q.text_en and q.text_ar
        assert sum(o.effect is None for o in q.options) == 1, q.id
        for o in q.options:
            if o.effect is not None and o.effect.kind != "feature":
                assert o.effect.value in vocab
    assert bank.topic is not None and bank.topic.id == TOPIC_QUESTION_ID
    assert [o.id for o in bank.topic.options] == list(CATEGORY_LABELS)


def test_info_gain_picks_registration_it_split(strategy: InfoGainStrategy) -> None:
    core = make_core({REG: 0.48, IT: 0.44}, {"high": 0.8}, set_cat=[REG, IT])
    q = strategy.select(core, Lang.EN, asked=[])
    assert q is not None and q.id == f"cat:{REG}|{IT}"
    assert q.target == "category" and q.lang == Lang.EN
    assert q.expected_info_gain == pytest.approx(1.0)  # a full split always leaves one label


def test_category_question_goes_before_priority(strategy: InfoGainStrategy) -> None:
    core = make_core(
        {REG: 0.5, IT: 0.45}, {"medium": 0.5, "high": 0.45}, set_cat=[REG, IT], set_pri=["medium", "high"]
    )
    q = strategy.select(core, Lang.EN, asked=[])
    assert q is not None and q.target == "category"
    # Once the category question was asked, the priority split is next.
    q2 = strategy.select(core, Lang.EN, asked=[q.id])
    assert q2 is not None and q2.id == "pri:deadline"


def test_no_question_is_repeated_and_none_when_nothing_applies(strategy: InfoGainStrategy) -> None:
    core = make_core({REG: 0.5, IT: 0.45}, set_cat=[REG, IT])
    assert strategy.select(core, Lang.EN, asked=[f"cat:{REG}|{IT}"]) is None
    assert strategy.select(make_core({REG: 0.9}, {"low": 0.9}), Lang.EN, asked=[]) is None
    # {low, high} has no split question in the bank.
    assert strategy.select(make_core({REG: 0.9}, set_pri=["low", "high"]), Lang.EN, asked=[]) is None


def test_not_sure_has_no_effect(bank: QuestionBank, strategy: InfoGainStrategy) -> None:
    for q in bank.questions:
        assert q.option("not_sure").effect is None
    core = make_core({REG: 0.5, IT: 0.45}, set_cat=[REG, IT])
    new_core, constraints = strategy.apply(core, f"cat:{REG}|{IT}", "not_sure")
    assert new_core is core and list(constraints) == []


def test_apply_category_restricts_the_set_only(strategy: InfoGainStrategy) -> None:
    core = make_core({REG: 0.5, IT: 0.45}, set_cat=[REG, IT])
    new_core, constraints = strategy.apply(core, f"cat:{REG}|{IT}", "it")
    assert new_core.set_cat.labels == {IT}
    assert new_core.p_cat == core.p_cat and new_core.set_pri == core.set_pri
    assert core.set_cat.labels == {REG, IT}  # the input is not mutated
    assert list(constraints) == [ClarificationConstraint("category", IT)]


def test_apply_feature_leaves_core_for_the_rerun(strategy: InfoGainStrategy) -> None:
    core = make_core({REG: 0.9}, {"medium": 0.55, "high": 0.4}, set_pri=["medium", "high"])
    new_core, constraints = strategy.apply(core, "pri:deadline", "yes_today")
    assert new_core.set_pri == core.set_pri
    assert list(constraints) == [ClarificationConstraint("feature", "deadline_today")]
    no_core, no_constraints = strategy.apply(core, "pri:deadline", "no_deadline")
    assert no_core.set_pri.labels == {"medium"}
    assert list(no_constraints) == [ClarificationConstraint("priority", "medium")]


def test_unknown_question_or_option_raises_not_found(strategy: InfoGainStrategy) -> None:
    core = make_core()
    with pytest.raises(NotFound):
        strategy.apply(core, "cat:nope", "x")
    with pytest.raises(NotFound):
        strategy.apply(core, f"cat:{REG}|{IT}", "nope")


def test_arabic_and_arabizi_get_the_fixture_text(strategy: InfoGainStrategy) -> None:
    core = make_core({REG: 0.52, IT: 0.40}, set_cat=[REG, IT])
    for lang in (Lang.AR, Lang.ARABIZI):
        q = strategy.select(core, lang, asked=[])
        assert q is not None
        assert q.text == "المشكلة بتسجيل المادة نفسها، ولا بالدخول أو الموقع مش شغال؟"
        assert [(o.id, o.text) for o in q.options] == [
            ("registration", "بتسجيل المادة"),
            ("it", "بالدخول أو الموقع"),
            ("not_sure", "مش متأكد"),
        ]


def test_priority_question_depends_on_the_top_category(strategy: InfoGainStrategy) -> None:
    pri = {"medium": 0.5, "high": 0.45}
    leak = strategy.select(make_core({FAC: 0.9}, pri, set_pri=["medium", "high"]), Lang.EN, asked=[])
    exam = strategy.select(make_core({IT: 0.9}, pri, set_pri=["medium", "high"]), Lang.EN, asked=[])
    assert leak is not None and leak.id == "pri:safety"
    assert exam is not None and exam.id == "pri:deadline"


def test_wider_set_prefers_the_split_covering_more_mass(
    bank: QuestionBank, strategy: InfoGainStrategy
) -> None:
    core = make_core({REG: 0.40, IT: 0.35, FIN: 0.20}, set_cat=[REG, IT, FIN])
    reg_it, fin_reg = bank.get(f"cat:{REG}|{IT}"), bank.get(f"cat:{FIN}|{REG}")
    assert expected_set_size(core, reg_it) < expected_set_size(core, fin_reg)
    q = strategy.select(core, Lang.EN, asked=[])
    assert q is not None and q.id == reg_it.id


def test_topic_chips_for_out_of_scope(strategy: InfoGainStrategy) -> None:
    q = strategy.topic_question(Lang.EN)
    assert q.id == "topic" and q.text == "Which of these topics is closest?"
    assert [(o.id, o.text) for o in q.options] == [(c, c) for c in CATEGORY_LABELS]
    new_core, constraints = strategy.apply(make_core(set_cat=list(CATEGORY_LABELS)), "topic", FAC)
    assert new_core.set_cat.labels == {FAC}
    assert list(constraints) == [ClarificationConstraint("category", FAC)]


def test_strategy_implements_the_port(strategy: InfoGainStrategy) -> None:
    assert isinstance(strategy, ClarificationStrategy)


_GOOD_Q = """
  - id: q1
    target: category
    split: [Registration, IT Support]
    text_en: e
    text_ar: a
    options:
      - {id: a, text_en: a, text_ar: a, effect: {kind: category, value: Registration}}
      - {id: b, text_en: b, text_ar: b, effect: {kind: category, value: IT Support}}
      - {id: not_sure, text_en: n, text_ar: n, effect: null}
"""


@pytest.mark.parametrize(
    "body",
    [
        "questions:" + _GOOD_Q.replace("value: IT Support", "value: Parking"),  # unknown label
        "questions:" + _GOOD_Q + _GOOD_Q,  # duplicate id
        "questions:" + _GOOD_Q.replace("      - {id: not_sure, text_en: n, text_ar: n, effect: null}\n", ""),
        "questions:" + _GOOD_Q.replace("target: category", "target: priority"),  # labels vs target
        "questions: {}",
    ],
    ids=["unknown_label", "duplicate_id", "no_not_sure", "wrong_target", "not_a_list"],
)
def test_invalid_bank_raises_invalid_input(tmp_path: Path, body: str) -> None:
    path = tmp_path / "bank.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(InvalidInput):
        QuestionBank.load(path)


def test_unknown_feature_is_rejected_when_the_vocabulary_is_given(tmp_path: Path) -> None:
    text = BANK_PATH.read_text(encoding="utf-8").replace("value: deadline_today", "value: deadline_tmrw")
    path = tmp_path / "bank.yaml"
    path.write_text(text, encoding="utf-8")
    assert len(QuestionBank.load(path).questions) == 7  # no vocabulary given: accepted
    with pytest.raises(InvalidInput):
        QuestionBank.load(path, features=EVIDENCE_FEATURES)
