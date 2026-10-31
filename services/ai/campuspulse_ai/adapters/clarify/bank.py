"""The clarification question bank (`config/clarify_questions.yaml`, SPEC §5.1 [8], P3.2).

A bank entry is bilingual (EN + Jordanian Arabic) and carries the label split it resolves. It is
rendered into the domain `ClarificationQuestion` (one language) only when it is asked.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from campuspulse_ai.domain.errors import InvalidInput, NotFound
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.values import (
    ClarificationConstraint,
    ClarificationOption,
    ClarificationQuestion,
    Lang,
    PredictionSet,
)

Target = Literal["category", "priority"]
TOPIC_QUESTION_ID = "topic"
"""The out_of_scope chip list (LD-36): option ids are the category labels."""

_LABELS: Mapping[str, frozenset[str]] = {
    "category": frozenset(CATEGORY_LABELS),
    "priority": frozenset(PRIORITY_LABELS),
}
# A split needs two labels to be a split at all; this is structure, not a tuned threshold.
_MIN_SPLIT = 2


@dataclass(frozen=True, slots=True)
class QuestionOption:
    """One answer chip of a bank question.

    `effect` is the constraint the answer applies (None = "not sure"). `labels` are the labels the
    answer points to, used to score the question: the effect value for category/priority effects, the
    declared `implies` label for a feature effect, and nothing for "not sure".
    """

    id: str
    text_en: str
    text_ar: str
    effect: ClarificationConstraint | None
    labels: frozenset[str]

    def text(self, lang: Lang) -> str:
        """The chip text in `lang` (Arabizi gets the Arabic text)."""
        return self.text_en if lang == Lang.EN else self.text_ar


@dataclass(frozen=True, slots=True)
class BankQuestion:
    """A bilingual bank entry. It applies when `split` ⊆ the current set of its `target`."""

    id: str
    target: Target
    split: frozenset[str]
    text_en: str
    text_ar: str
    options: tuple[QuestionOption, ...]
    when_category: frozenset[str] | None = None

    def text(self, lang: Lang) -> str:
        """The question text in `lang` (Arabizi gets the Arabic text)."""
        return self.text_en if lang == Lang.EN else self.text_ar

    def option(self, option_id: str) -> QuestionOption:
        """The option with `option_id`. Raises NotFound."""
        for opt in self.options:
            if opt.id == option_id:
                return opt
        raise NotFound(f"unknown option {option_id!r} for question {self.id!r}")

    def render(self, lang: Lang, expected_info_gain: float = 0.0) -> ClarificationQuestion:
        """The domain question in one language, with its chips."""
        return ClarificationQuestion(
            id=self.id,
            target=self.target,
            text=self.text(lang),
            lang=lang,
            options=tuple(
                ClarificationOption(id=o.id, text=o.text(lang), constraint=o.effect) for o in self.options
            ),
            expected_info_gain=expected_info_gain,
        )


class QuestionBank:
    """The loaded, validated question bank.

    `questions` are the questions InfoGainStrategy may ask, in bank order (the order breaks ties).
    `topic` is the out_of_scope chip list (question id `topic`); it is never selected by information
    gain but `get("topic")` returns it so a topic answer can be applied like any other.
    """

    def __init__(self, questions: Sequence[BankQuestion], topic: BankQuestion | None = None) -> None:
        ids = [q.id for q in questions] + ([topic.id] if topic else [])
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise InvalidInput(f"duplicate question ids: {dupes}")
        self.questions: tuple[BankQuestion, ...] = tuple(questions)
        self.topic = topic
        self._by_id = {q.id: q for q in self.questions}
        if topic is not None:
            self._by_id[topic.id] = topic

    @classmethod
    def load(cls, path: str | Path, *, features: Collection[str] | None = None) -> QuestionBank:
        """Load and validate a bank YAML file.

        `features` is the evidence-feature vocabulary (FrozenConfig `priority_head.features`); when
        given, every feature effect must name one of them. Raises InvalidInput on a missing or
        malformed file, an unknown label, a duplicate id, or options that do not cover the split.
        """
        p = Path(path)
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise InvalidInput(f"cannot read question bank {p}: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("questions"), list):
            raise InvalidInput(f"{p}: expected a mapping with a `questions` list")
        feats = frozenset(features) if features is not None else None
        questions = [_parse_question(q, feats) for q in raw["questions"]]
        topic_raw = raw.get("topic")
        topic = _parse_question(topic_raw, feats, needs_not_sure=False) if topic_raw is not None else None
        if topic is not None and topic.id != TOPIC_QUESTION_ID:
            raise InvalidInput(f"the topic question must have id {TOPIC_QUESTION_ID!r}, got {topic.id!r}")
        return cls(questions, topic)

    def applicable(
        self, set_cat: PredictionSet, set_pri: PredictionSet, *, top_category: str | None = None
    ) -> list[BankQuestion]:
        """Questions whose split lies inside the (non-singleton) set of their target, in bank order.

        With `top_category`, a question that has `when_category` applies only if the top category is
        listed (e.g. the safety question is for Facilities and Transportation requests).
        """
        sets = {"category": set_cat, "priority": set_pri}
        out = []
        for q in self.questions:
            current = sets[q.target]
            if current.size < _MIN_SPLIT or not q.split <= current.labels:
                continue
            if (
                q.when_category is not None
                and top_category is not None
                and top_category not in q.when_category
            ):
                continue
            out.append(q)
        return out

    def get(self, question_id: str) -> BankQuestion:
        """The question (or the topic list) with this id. Raises NotFound."""
        try:
            return self._by_id[question_id]
        except KeyError:
            raise NotFound(f"unknown clarification question {question_id!r}") from None


def _str(entry: Mapping[str, object], key: str, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f"{where}: `{key}` must be a non-empty string")
    return value


def _parse_effect(
    raw: object, target: Target, split: frozenset[str], features: frozenset[str] | None, where: str
) -> tuple[ClarificationConstraint | None, frozenset[str]]:
    if raw is None:
        return None, frozenset()
    if not isinstance(raw, dict):
        raise InvalidInput(f"{where}: `effect` must be a mapping or null")
    kind = raw.get("kind")
    value = raw.get("value")
    if not isinstance(value, str) or not value:
        raise InvalidInput(f"{where}: effect `value` must be a non-empty string")
    if kind in ("category", "priority"):
        if kind != target:
            raise InvalidInput(f"{where}: a {target} question cannot have a {kind} effect")
        if value not in _LABELS[kind]:
            raise InvalidInput(f"{where}: unknown {kind} label {value!r}")
        labels = frozenset({value})
    elif kind == "feature":
        if target != "priority":
            raise InvalidInput(f"{where}: feature effects belong to priority questions")
        if features is not None and value not in features:
            raise InvalidInput(f"{where}: unknown evidence feature {value!r}")
        implies = raw.get("implies")
        if not isinstance(implies, str) or implies not in _LABELS["priority"]:
            raise InvalidInput(f"{where}: a feature effect needs `implies: <priority label>`")
        labels = frozenset({implies})
    else:
        raise InvalidInput(f"{where}: effect kind must be category, priority or feature, got {kind!r}")
    if not labels <= split:
        raise InvalidInput(f"{where}: option label {sorted(labels)} is outside the split {sorted(split)}")
    constraint_kind = cast(Literal["category", "priority", "feature"], kind)
    return ClarificationConstraint(kind=constraint_kind, value=value), labels


def _parse_question(
    raw: object, features: frozenset[str] | None, *, needs_not_sure: bool = True
) -> BankQuestion:
    if not isinstance(raw, dict):
        raise InvalidInput("every question must be a mapping")
    qid = _str(raw, "id", "question")
    where = f"question {qid!r}"
    target = raw.get("target")
    if target not in ("category", "priority"):
        raise InvalidInput(f"{where}: target must be category or priority, got {target!r}")
    tgt = cast(Target, target)
    split_raw = raw.get("split")
    if not isinstance(split_raw, list) or len(set(split_raw)) < _MIN_SPLIT:
        raise InvalidInput(f"{where}: `split` must list at least {_MIN_SPLIT} labels")
    unknown = [lab for lab in split_raw if lab not in _LABELS[tgt]]
    if unknown:
        raise InvalidInput(f"{where}: unknown {tgt} labels in split: {unknown}")
    split = frozenset(cast(list[str], split_raw))
    when_raw = raw.get("when_category")
    when: frozenset[str] | None = None
    if when_raw is not None:
        if not isinstance(when_raw, list) or any(c not in _LABELS["category"] for c in when_raw):
            raise InvalidInput(f"{where}: `when_category` must list category labels")
        when = frozenset(cast(list[str], when_raw))
    opts_raw = raw.get("options")
    if not isinstance(opts_raw, list) or not opts_raw:
        raise InvalidInput(f"{where}: `options` must be a non-empty list")
    options: list[QuestionOption] = []
    for o in opts_raw:
        if not isinstance(o, dict):
            raise InvalidInput(f"{where}: every option must be a mapping")
        oid = _str(o, "id", where)
        owhere = f"{where} option {oid!r}"
        effect, labels = _parse_effect(o.get("effect"), tgt, split, features, owhere)
        options.append(
            QuestionOption(oid, _str(o, "text_en", owhere), _str(o, "text_ar", owhere), effect, labels)
        )
    opt_ids = [o.id for o in options]
    if len(set(opt_ids)) != len(opt_ids):
        raise InvalidInput(f"{where}: duplicate option ids")
    covered: set[str] = set()
    for o in options:
        if covered & o.labels:
            raise InvalidInput(f"{where}: two options point to the same label")
        covered |= o.labels
    if covered != split:
        raise InvalidInput(
            f"{where}: the options must cover the split {sorted(split)}, got {sorted(covered)}"
        )
    not_sure = [o for o in options if o.effect is None]
    if needs_not_sure and len(not_sure) != 1:
        raise InvalidInput(f"{where}: needs exactly one `not_sure` option (effect null)")
    return BankQuestion(
        qid, tgt, split, _str(raw, "text_en", where), _str(raw, "text_ar", where), tuple(options), when
    )
