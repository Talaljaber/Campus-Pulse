"""`LlmCueFloor`: the LLM front end's urgency cues as a raise-only priority floor (P7.9, D-056).

The front end's single call per Arabic or Arabizi request already returns structured cues (P8.5: urgency,
deadline, kind, affected, physical_danger, account_compromise, outage). This adapter reads them from the
`LlmFrontendEncoder.records` and names the conservative combinations that justify HIGH. A rule is a set of
conditions that must all hold (a bool must equal, any other cue must be one of the listed values); the rule
names that hold are the `hits`. Tone never counts (`urgency` alone is never a rule, only a qualifier), a
request with no valid LLM reply has no cues and therefore no hits, and English requests are not sent to the
LLM (`explain_english: false`), so they never have cues: English stays lexicon-only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from campuspulse_ai.adapters.models.llm_frontend_encoder import LlmFrontendEncoder, classify_source

Condition = bool | Sequence[str]


def parse_rules(raw: Mapping[str, Any]) -> dict[str, dict[str, Condition]]:
    """Validate the `cue_floor.rules` mapping of `config/llm_frontend.yaml`.

    Raises:
        ValueError: an unknown cue name, an empty rule or a condition of the wrong shape.
    """
    known = {"urgency", "deadline", "kind", "affected", "physical_danger", "account_compromise", "outage"}
    rules: dict[str, dict[str, Condition]] = {}
    for name, spec in raw.items():
        if not isinstance(spec, Mapping) or not spec:
            raise ValueError(f"cue_floor rule {name!r} must be a non-empty mapping")
        conds: dict[str, Condition] = {}
        for cue, want in spec.items():
            if cue not in known:
                raise ValueError(f"cue_floor rule {name!r}: unknown cue {cue!r}")
            if isinstance(want, bool):
                conds[cue] = want
            elif isinstance(want, list) and want and all(isinstance(v, str) for v in want):
                conds[cue] = tuple(want)
            else:
                raise ValueError(f"cue_floor rule {name!r}: {cue!r} must be a bool or a list of strings")
        rules[str(name)] = conds
    return rules


class LlmCueFloor:
    """Implements `domain.ports.CueFloor` over an `LlmFrontendEncoder`'s records."""

    def __init__(self, encoder: LlmFrontendEncoder, rules: Mapping[str, Mapping[str, Condition]]) -> None:
        self._encoder = encoder
        self._rules = {name: dict(conds) for name, conds in rules.items()}

    def cues(self, model_text: str) -> Mapping[str, object] | None:
        """The cue values the LLM returned for this request, or None (no call, call failed, English)."""
        kind, source = classify_source(model_text)
        if kind == "en":  # English is lexicon-only, even when an explanation call was made for it
            return None
        record = self._encoder.records.get(source)
        return None if record is None else dict(record.cues)

    def hits(self, model_text: str) -> tuple[str, ...]:
        cues = self.cues(model_text)
        if cues is None:
            return ()
        return tuple(name for name, conds in self._rules.items() if _holds(cues, conds))


def _holds(cues: Mapping[str, object], conds: Mapping[str, Condition]) -> bool:
    for cue, want in conds.items():
        value = cues.get(cue)
        if isinstance(want, bool):
            if value is not want:
                return False
        elif value not in want:
            return False
    return True
