"""The `Understanding` output contract: limits, the JSON schema sent to the model, and the validator.

No JSON-schema library is pinned, so `parse_understanding` checks the same rules by hand. A reply that
breaks any rule raises `LLMOutputOutOfSet` ("schema violation"), and the LLMUnderstander falls back to
the rule-based understander. Beyond the schema, the validator enforces the prompt's grounding rules:
the decided labels must be echoed unchanged, and a course code, room or building must occur in the
request (or its location).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from campuspulse_ai.adapters.llm.prompt import PromptTemplate
from campuspulse_ai.adapters.llm.set_constrained import load_json_object
from campuspulse_ai.adapters.understand.entities import grounded, has_arabic, has_latin
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import LLMOutputOutOfSet
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Entities, Lang, NormalizedRequest, Understanding

UNDERSTANDING_SCHEMA_NAME = "request_understanding"
ENTITY_KEYS = ("building", "room", "course_code", "deadline", "system")
TEXT_KEYS = ("summary_en", "summary_ar", "student_reply", "ticket_title", "ticket_body")
TOP_KEYS = ("category", "priority", *TEXT_KEYS[:2], "entities", *TEXT_KEYS[2:])


@dataclass(frozen=True, slots=True)
class UnderstandLimits:
    """Output length limits (characters). They are part of the prompt version's contract and are read
    from the prompt front matter, so the LLM and the rule-based understander share them."""

    max_title_chars: int
    max_reply_chars: int
    max_summary_chars: int
    max_body_chars: int
    max_entity_chars: int

    @classmethod
    def from_prompt(cls, prompt: PromptTemplate) -> UnderstandLimits:
        """Raises InvalidInput if the prompt does not declare every limit."""
        return cls(
            max_title_chars=prompt.limit("max_title_chars"),
            max_reply_chars=prompt.limit("max_reply_chars"),
            max_summary_chars=prompt.limit("max_summary_chars"),
            max_body_chars=prompt.limit("max_body_chars"),
            max_entity_chars=prompt.limit("max_entity_chars"),
        )

    def for_key(self, key: str) -> int:
        return {
            "summary_en": self.max_summary_chars,
            "summary_ar": self.max_summary_chars,
            "student_reply": self.max_reply_chars,
            "ticket_title": self.max_title_chars,
            "ticket_body": self.max_body_chars,
        }[key]


def decided_labels(core: CoreResult) -> tuple[Category, Priority]:
    """The labels the understanding must describe: a singleton set's label, otherwise the argmax.

    This matches the decision rule of ARCHITECTURE §2.1 [9] (argmax of the final core; sets are
    singletons after ACCEPT or a clarification answer).
    """
    cat = next(iter(core.set_cat.labels)) if core.set_cat.is_singleton else core.p_cat.argmax()
    pri = next(iter(core.set_pri.labels)) if core.set_pri.is_singleton else core.p_pri.argmax()
    return Category(cat), Priority(pri)


def understanding_schema(
    category: Category, priority: Priority, limits: UnderstandLimits
) -> dict[str, object]:
    """The JSON schema sent to the model; the label enums hold only the decided labels.

    Length limits travel as descriptions, not `maxLength`: strict structured-output modes of several
    providers reject string-length keywords. `parse_understanding` enforces the limits locally.
    """
    nullable = {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "description": f"null when absent; at most {limits.max_entity_chars} characters",
    }
    text = {
        key: {"type": "string", "description": f"at most {limits.for_key(key)} characters"}
        for key in TEXT_KEYS
    }
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": [str(category)]},
            "priority": {"type": "string", "enum": [str(priority)]},
            **text,
            "entities": {
                "type": "object",
                "properties": {
                    **{key: dict(nullable) for key in ENTITY_KEYS},
                    "deadline": {**nullable, "description": "YYYY-MM-DD, or null when no date is named"},
                },
                "required": list(ENTITY_KEYS),
                "additionalProperties": False,
            },
        },
        "required": list(TOP_KEYS),
        "additionalProperties": False,
    }


def response_format(category: Category, priority: Priority, limits: UnderstandLimits) -> dict[str, object]:
    """OpenRouter structured-output `response_format` for the understander."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": UNDERSTANDING_SCHEMA_NAME,
            "strict": True,
            "schema": understanding_schema(category, priority, limits),
        },
    }


def _exact_keys(obj: Mapping[str, object], keys: tuple[str, ...], where: str) -> None:
    if set(obj) != set(keys):
        missing, extra = sorted(set(keys) - set(obj)), sorted(set(obj) - set(keys))
        raise LLMOutputOutOfSet(f"{where}: missing keys {missing}, unexpected keys {extra}")


def _parse_entities(raw: object, req: NormalizedRequest, limits: UnderstandLimits) -> Entities:
    if not isinstance(raw, dict):
        raise LLMOutputOutOfSet("entities must be an object")
    _exact_keys(raw, ENTITY_KEYS, "entities")
    values: dict[str, str | None] = {}
    for key in ENTITY_KEYS:
        v = raw[key]
        if v is not None and (not isinstance(v, str) or not v.strip() or len(v) > limits.max_entity_chars):
            raise LLMOutputOutOfSet(f"entity {key} must be null or a short non-empty string")
        values[key] = v.strip() if isinstance(v, str) else None
    for key in ("course_code", "room"):
        v = values[key]
        if v is not None and not grounded(v, req):
            raise LLMOutputOutOfSet(f"entity {key}={v!r} is not in the request")
    building = values["building"]
    picked = req.location.building if req.location else None
    if building is not None and building != picked and not grounded(building, req):
        raise LLMOutputOutOfSet(f"entity building={building!r} is not in the request")
    deadline = None
    if values["deadline"] is not None:
        try:
            deadline = date.fromisoformat(values["deadline"])
        except ValueError as exc:
            raise LLMOutputOutOfSet(f"deadline {values['deadline']!r} is not YYYY-MM-DD") from exc
    return Entities(
        building=building,
        room=values["room"],
        course_code=values["course_code"],
        deadline=deadline,
        system=values["system"],
    )


def parse_understanding(
    raw_json: str,
    req: NormalizedRequest,
    category: Category,
    priority: Priority,
    limits: UnderstandLimits,
    prompt_version: str,
) -> Understanding:
    """Validate a model reply and build the `Understanding` (source "llm").

    Raises LLMOutputOutOfSet when: the reply is not one JSON object with exactly the schema's keys; the
    echoed category/priority differ from the decided labels; a text field is empty or over its limit;
    `summary_ar` has no Arabic letters or `summary_en` no Latin letters; the reply is not in the request
    language (Arabic script for Arabic and Arabizi requests); an entity is malformed, or a course code,
    room or building does not occur in the request.
    """
    obj = load_json_object(raw_json)
    _exact_keys(obj, TOP_KEYS, "understanding")
    if obj["category"] != str(category) or obj["priority"] != str(priority):
        raise LLMOutputOutOfSet(
            f"labels changed: got {obj['category']!r}/{obj['priority']!r}, decided {category}/{priority}"
        )
    texts: dict[str, str] = {}
    for key in TEXT_KEYS:
        v = obj[key]
        if not isinstance(v, str) or not v.strip() or len(v) > limits.for_key(key):
            raise LLMOutputOutOfSet(
                f"{key} must be a non-empty string of at most {limits.for_key(key)} chars"
            )
        texts[key] = v.strip()
    if not has_arabic(texts["summary_ar"]) or not has_latin(texts["summary_en"]):
        raise LLMOutputOutOfSet("summary_ar must be Arabic and summary_en English")
    reply = texts["student_reply"]
    if (req.lang == Lang.EN and not has_latin(reply)) or (req.lang != Lang.EN and not has_arabic(reply)):
        raise LLMOutputOutOfSet(f"student_reply is not in the request language ({req.lang})")
    return Understanding(
        summary_en=texts["summary_en"],
        summary_ar=texts["summary_ar"],
        entities=_parse_entities(obj["entities"], req, limits),
        student_reply=reply,
        ticket_title=texts["ticket_title"],
        ticket_body=texts["ticket_body"],
        source="llm",
        prompt_version=prompt_version,
    )
