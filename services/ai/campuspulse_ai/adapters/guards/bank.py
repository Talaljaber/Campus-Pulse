"""Load guard lexicons (`config/lexicons/{injection,safety}.yaml`, or their model-dir snapshot, LD-12)."""

from __future__ import annotations

import re
from pathlib import Path

from campuspulse_ai.adapters.preprocess.patterns import compile_patterns, load_yaml, string_list


def compile_bank(path: Path, key: str) -> list[re.Pattern[str]]:
    """Compile the regex list at `key` (dotted keys allowed) of a lexicon file.

    Patterns are normalized like `text_norm` (see `adapters.preprocess.patterns`) and case-insensitive.

    Raises:
        KeyError: the key is missing. ValueError: not a list of strings. re.error: an invalid regex.
    """
    return compile_patterns(string_list(load_yaml(path), key))


def load_texts(path: Path, key: str) -> list[str]:
    """The text list at `key` (e.g. `exemplars`, `exemplars.distress`), stripped, empty entries dropped."""
    return [t.strip() for t in string_list(load_yaml(path), key) if t.strip()]
