"""Set-constrained prompting and parsing for the LLM tiers (ARCHITECTURE §3.9, P3.3).

Pure functions: the messages, the JSON-schema `response_format` whose enums are exactly the allowed
conformal sets, the cache key, and the parser that rejects any label outside those sets. The model
can never widen a set (UD-5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

from campuspulse_ai.adapters.llm.prompt import PromptTemplate
from campuspulse_ai.domain.errors import LLMOutputOutOfSet
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.values import NormalizedRequest, PredictionSet

ORACLE_SCHEMA_NAME = "triage_choice"
_KEY_SEP = "\x1f"  # unit separator: cannot appear in labels, so key parts never run together
_FENCE = "```"


def ordered(labels: Iterable[str], order: tuple[str, ...]) -> list[str]:
    """`labels` in the fixed domain label order (deterministic prompts and cache keys)."""
    wanted = set(labels)
    return [lab for lab in order if lab in wanted]


def truncate_tokens(text: str, max_tokens: int) -> str:
    """The first `max_tokens` whitespace tokens of `text` (guards.max_tokens)."""
    tokens = text.split()
    return " ".join(tokens[:max_tokens])


def cache_key(
    model_id: str,
    prompt_version: str,
    model_text: str,
    allowed_cat: PredictionSet,
    allowed_pri: PredictionSet,
) -> str:
    """sha256(model_id ‖ prompt_version ‖ model_text ‖ sorted(allowed_cat) ‖ sorted(allowed_pri))."""
    parts = [
        "oracle",
        model_id,
        prompt_version,
        model_text,
        ",".join(sorted(allowed_cat.labels)),
        ",".join(sorted(allowed_pri.labels)),
    ]
    return hashlib.sha256(_KEY_SEP.join(parts).encode("utf-8")).hexdigest()


def build_messages(
    req: NormalizedRequest,
    allowed_cat: PredictionSet,
    allowed_pri: PredictionSet,
    prompt: PromptTemplate,
    *,
    max_input_tokens: int,
) -> list[dict[str, str]]:
    """System + user messages. The system prompt lists only the allowed labels; the user message holds
    the wrapper-stripped original (`req.core`, so a stripped "URGENT:" never reaches the model) and the
    normalized model text, both truncated at `max_input_tokens`."""
    return prompt.render(
        allowed_categories=", ".join(ordered(allowed_cat.labels, CATEGORY_LABELS)),
        allowed_priorities=", ".join(ordered(allowed_pri.labels, PRIORITY_LABELS)),
        max_reason_words=str(prompt.limit("max_reason_words")),
        original=truncate_tokens(req.core, max_input_tokens),
        normalized=truncate_tokens(req.model_text, max_input_tokens),
    )


def answer_schema(allowed_cat: PredictionSet, allowed_pri: PredictionSet) -> dict[str, object]:
    """JSON schema of the oracle answer; the enums are exactly the allowed sets."""
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": ordered(allowed_cat.labels, CATEGORY_LABELS)},
            "priority": {"type": "string", "enum": ordered(allowed_pri.labels, PRIORITY_LABELS)},
            "reason": {"type": "string"},
        },
        "required": ["category", "priority", "reason"],
        "additionalProperties": False,
    }


def response_format(allowed_cat: PredictionSet, allowed_pri: PredictionSet) -> dict[str, object]:
    """OpenRouter structured-output `response_format` for the oracle."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": ORACLE_SCHEMA_NAME,
            "strict": True,
            "schema": answer_schema(allowed_cat, allowed_pri),
        },
    }


def load_json_object(raw_json: str) -> Mapping[str, object]:
    """Parse a model reply into a JSON object, tolerating a ```json fence. Raises LLMOutputOutOfSet."""
    text = raw_json.strip()
    if text.startswith(_FENCE):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[len("json") :]
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMOutputOutOfSet(f"LLM output is not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise LLMOutputOutOfSet("LLM output is not a JSON object")
    return obj


def parse_answer(
    raw_json: str, allowed_cat: PredictionSet, allowed_pri: PredictionSet, *, max_reason_words: int
) -> tuple[Category | None, Priority | None, str]:
    """Validate an oracle reply against the allowed sets.

    Returns (category, priority, reason), the reason cut to `max_reason_words`. Raises
    LLMOutputOutOfSet if the reply is not a JSON object, has keys other than the schema's, or names a
    label outside its allowed set (the set is never widened).
    """
    obj = load_json_object(raw_json)
    extra = set(obj) - {"category", "priority", "reason"}
    if extra:
        raise LLMOutputOutOfSet(f"LLM output has unexpected keys {sorted(extra)}")
    cat, pri, reason = obj.get("category"), obj.get("priority"), obj.get("reason", "")
    if not isinstance(cat, str) or cat not in allowed_cat.labels:
        raise LLMOutputOutOfSet(f"category {cat!r} is outside the allowed set {sorted(allowed_cat.labels)}")
    if not isinstance(pri, str) or pri not in allowed_pri.labels:
        raise LLMOutputOutOfSet(f"priority {pri!r} is outside the allowed set {sorted(allowed_pri.labels)}")
    if not isinstance(reason, str):
        raise LLMOutputOutOfSet("reason must be a string")
    return Category(cat), Priority(pri), " ".join(reason.split()[:max_reason_words])
