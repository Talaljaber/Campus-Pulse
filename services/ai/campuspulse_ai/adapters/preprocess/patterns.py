"""Compile lexicon regexes so they match normalized model text (P1.5, P1.12).

Guards and the evidence extractor run on `NormalizedRequest.model_text`, which is normalized like
`clean_data.normalize`: English is lower-cased, Arabic loses diacritics and tatweel and maps أ/إ/آ→ا, ى→ي,
ة→ه, ؤ→و, ئ→ي. Lexicon authors write natural Arabic (`عالية`, `الأوامر`); `normalize_pattern` applies the same
Arabic character map to the pattern text, so the pattern and the text agree. The mapped characters are not
regex metacharacters, so the regex structure is unchanged. Every pattern is compiled case-insensitive.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.adapters.preprocess.wrappers import AR_CHARMAP, AR_DIACRITICS


def normalize_pattern(pattern: str) -> str:
    """Apply the Arabic `text_norm` character map and diacritic removal to a regex source."""
    return AR_DIACRITICS.sub("", pattern).translate(AR_CHARMAP)


def compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    """Compile normalized, case-insensitive patterns.

    Raises:
        re.error: a pattern is not a valid regex (a lexicon bug; fail at load time, never at inspect time).
    """
    return [re.compile(normalize_pattern(p), re.IGNORECASE) for p in patterns]


def load_yaml(path: Path) -> Mapping[str, Any]:
    """Read a lexicon YAML file as a mapping."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def lookup(data: Mapping[str, Any], key: str) -> Any:
    """`data["a"]["b"]` for the dotted key `"a.b"`.

    Raises:
        KeyError: a component is missing.
    """
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise KeyError(f"lexicon key {key!r} not found (missing {part!r})")
        node = node[part]
    return node


def string_list(data: Mapping[str, Any], key: str) -> list[str]:
    """The list of strings at a dotted key (an empty YAML value gives `[]`).

    Raises:
        KeyError: the key is missing. ValueError: the value is not a list of strings.
    """
    value = lookup(data, key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"lexicon key {key!r} must be a list of strings")
    return list(value)
