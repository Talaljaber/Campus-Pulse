"""`UrgencyFloorRule`: raise-only high-priority floors for implicit urgency (P7.3, D-031).

Reads the `high_floor:` block of `config/lexicons/urgency.yaml` (or its model-dir snapshot, LD-12).
A family is a list of variants; a variant is a list of groups; a group is a set of regexes per language.
A variant fires when every group has at least one match in `req.model_text`; a family fires when any
variant fires. Tone never counts: the rule reads the stripped `model_text`, never `stated_urgency`.
A lexicon without a `high_floor:` block (an older model dir) gives a rule that never fires.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from campuspulse_ai.adapters.preprocess.patterns import compile_patterns, load_yaml
from campuspulse_ai.domain.values import NormalizedRequest

LANG_KEYS: tuple[str, ...] = ("en", "ar", "arabizi")
BLOCK_KEY = "high_floor"

Group = tuple[re.Pattern[str], ...]
Variant = tuple[Group, ...]


def _compile_group(group: Mapping[str, Any]) -> list[re.Pattern[str]]:
    return compile_patterns(p for lang in LANG_KEYS for p in (group.get(lang) or []))


class UrgencyFloorRule:
    """Implements `domain.ports.UrgencyFloor`: `hits(req)` returns the fired family names (sorted)."""

    def __init__(self, families: Mapping[str, Sequence[Sequence[Sequence[re.Pattern[str]]]]]) -> None:
        self._families: dict[str, tuple[Variant, ...]] = {
            name: tuple(tuple(tuple(g) for g in variant) for variant in variants)
            for name, variants in families.items()
        }
        for name, variants in self._families.items():
            if not variants or any(not variant or any(not g for g in variant) for variant in variants):
                raise ValueError(f"high_floor family {name!r} has an empty variant or group")

    @property
    def families(self) -> tuple[str, ...]:
        return tuple(self._families)

    @classmethod
    def from_yaml(cls, path: Path) -> UrgencyFloorRule:
        """Build from the lexicon file; an absent `high_floor:` block gives a rule with no families.

        Raises:
            ValueError / re.error: an invalid block or regex (fail at load time).
        """
        block: Any = load_yaml(path).get(BLOCK_KEY) or {}
        if not isinstance(block, Mapping):
            raise ValueError(f"{path}: {BLOCK_KEY} must be a mapping")
        families: dict[str, list[list[list[re.Pattern[str]]]]] = {}
        for name, spec in block.items():
            variants = spec.get("variants") if isinstance(spec, Mapping) else None
            if not variants:
                raise ValueError(f"{path}: {BLOCK_KEY}.{name} needs a `variants` list")
            families[str(name)] = [[_compile_group(group) for group in variant] for variant in variants]
        return cls(families)

    def hits(self, req: NormalizedRequest) -> tuple[str, ...]:
        text = req.model_text
        if not text:
            return ()
        return tuple(
            sorted(
                name
                for name, variants in self._families.items()
                if any(all(any(p.search(text) for p in group) for group in variant) for variant in variants)
            )
        )
