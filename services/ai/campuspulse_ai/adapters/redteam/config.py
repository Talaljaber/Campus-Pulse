"""Typed red-team configuration (P4.11): `config/redteam.yaml` plus the shared lexicons.

`RedTeamConfig.load(redteam_yaml, lexicons_dir)` reads:
- `config/redteam.yaml`: perturbation rates, prefixes, filler, glossary, templates and fixed lists;
- `<lexicons>/injection.yaml` `exemplars`: the injection phrases, grouped by script (en / ar / arabizi);
- `<lexicons>/wrappers.yaml` `prefixes`/`suffixes`: wrapper noise, minus any wrapper that contains an
  `urgency_markers` entry (so `very_long` never claims urgency);
- `<lexicons>/arabizi.yaml` `lexicon`: reversed into an Arabic -> Arabizi word map.

Errors: `KeyError` for a missing key, `ValueError` for a malformed value (a bad label, an unknown
language, a rate outside [0, 1]). Both are raised once, at load time.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from campuspulse_ai.adapters.guards.bank import load_texts
from campuspulse_ai.adapters.preprocess.patterns import load_yaml, lookup, string_list
from campuspulse_ai.adapters.preprocess.wrappers import normalize_text, script_lang
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang

LangTexts = Mapping[Lang, tuple[str, ...]]

REQUIRED_LANGS: tuple[Lang, ...] = (Lang.EN, Lang.AR)
"""Every per-language list needs these; Arabizi falls back to English (both are Latin script)."""
INJECTION_POSITIONS = frozenset({"prefix", "suffix"})

_ARABIZI_WORD = re.compile(r"[a-z]*[2-9][a-z]+|[a-z]+[2-9]")
"""A Latin word with an Arabizi digit letter (3=ع, 7=ح, 2=ء ...), e.g. `ta3limat`, `5aliha`."""


def text_lang(text: str) -> Lang:
    """`ar` for Arabic script; `arabizi` for Latin text with Arabizi digit-words; else `en`.

    Used for texts that carry no language column (lexicon exemplars, a supplied seed CSV). The
    package `LangIdentifier` is stricter; this only has to split the lexicons by script.
    """
    if script_lang(text) == "ar":
        return Lang.AR
    return Lang.ARABIZI if _ARABIZI_WORD.search(text.lower()) else Lang.EN


def for_lang(texts: LangTexts, lang: Lang) -> tuple[str, ...]:
    """The list for `lang`; Arabizi without its own list uses the English one."""
    if lang in texts:
        return texts[lang]
    return texts[Lang.EN] if lang is Lang.ARABIZI else ()


@dataclass(frozen=True, slots=True)
class Template:
    """A fixed red-team text with the labels the pass rule checks (§2.4)."""

    text: str
    lang: Lang
    category: Category
    priority: Priority
    flags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class TyposConfig:
    swap_rate: float
    drop_rate: float
    min_word_letters: int


@dataclass(frozen=True, slots=True)
class FakeUrgencyConfig:
    base_priorities: frozenset[Priority]
    prefixes: LangTexts
    suffixes: LangTexts
    suffix_rate: float


@dataclass(frozen=True, slots=True)
class InjectionConfig:
    positions: tuple[str, ...]
    phrases: LangTexts


@dataclass(frozen=True, slots=True)
class VeryLongConfig:
    target_chars: int
    filler: LangTexts
    wrapper_prefixes: LangTexts
    wrapper_suffixes: LangTexts


@dataclass(frozen=True, slots=True)
class MixedLanguageConfig:
    glossary: tuple[tuple[str, str], ...]
    """(english, arabic) pairs."""
    max_swaps: int
    phrases: LangTexts


@dataclass(frozen=True, slots=True)
class ArabiziConfig:
    charmap: Mapping[str, str]
    final_heh: str
    medial_vowels: Mapping[str, str]
    proclitics: tuple[tuple[str, str], ...]
    min_stem: int
    lexicon: Mapping[str, str]
    """Normalized Arabic word -> its first Arabizi spelling in `arabizi.yaml`."""


@dataclass(frozen=True, slots=True)
class RedTeamConfig:
    typos: TyposConfig
    fake_urgency: FakeUrgencyConfig
    injection: InjectionConfig
    very_long: VeryLongConfig
    mixed_language: MixedLanguageConfig
    two_issues_joiners: LangTexts
    arabizi: ArabiziConfig
    calm_places: LangTexts
    calm_templates: tuple[Template, ...]
    off_topic: tuple[Template, ...]
    distress_adjacent: tuple[Template, ...]
    sources: tuple[Path, ...] = field(default=())
    """The files it was read from (recorded in the CLI report)."""

    @classmethod
    def load(cls, redteam_yaml: Path, lexicons: Path) -> RedTeamConfig:
        """Read and validate everything (module docstring). Raises KeyError / ValueError."""
        cfg = load_yaml(redteam_yaml)
        injection_yaml = lexicons / "injection.yaml"
        wrappers_yaml = lexicons / "wrappers.yaml"
        arabizi_yaml = lexicons / "arabizi.yaml"
        markers = string_list(load_yaml(wrappers_yaml), "urgency_markers")
        wrappers = load_yaml(wrappers_yaml)
        nominal = lookup(cfg, "off_topic.nominal")
        return cls(
            typos=TyposConfig(
                swap_rate=_rate(cfg, "typos.swap_rate"),
                drop_rate=_rate(cfg, "typos.drop_rate"),
                min_word_letters=_positive_int(cfg, "typos.min_word_letters"),
            ),
            fake_urgency=FakeUrgencyConfig(
                base_priorities=frozenset(
                    _priority(p) for p in string_list(cfg, "fake_urgency.base_priorities")
                ),
                prefixes=_lang_texts(cfg, "fake_urgency.prefixes"),
                suffixes=_lang_texts(cfg, "fake_urgency.suffixes"),
                suffix_rate=_rate(cfg, "fake_urgency.suffix_rate"),
            ),
            injection=InjectionConfig(
                positions=_positions(string_list(cfg, "injection.positions")),
                phrases=_by_lang(load_texts(injection_yaml, "exemplars")),
            ),
            very_long=VeryLongConfig(
                target_chars=_positive_int(cfg, "very_long.target_chars"),
                filler=_lang_texts(cfg, "very_long.filler"),
                wrapper_prefixes=_by_lang(_calm(string_list(wrappers, "prefixes"), markers)),
                wrapper_suffixes=_by_lang(_calm(string_list(wrappers, "suffixes"), markers)),
            ),
            mixed_language=MixedLanguageConfig(
                glossary=_pairs(lookup(cfg, "mixed_language.glossary"), "mixed_language.glossary"),
                max_swaps=_positive_int(cfg, "mixed_language.max_swaps"),
                phrases=_lang_texts(cfg, "mixed_language.phrases"),
            ),
            two_issues_joiners=_lang_texts(cfg, "two_issues.joiners"),
            arabizi=_arabizi(cfg, load_yaml(arabizi_yaml)),
            calm_places=_lang_texts(cfg, "calm_emergency.places"),
            calm_templates=_templates(lookup(cfg, "calm_emergency.templates"), None),
            off_topic=_templates(lookup(cfg, "off_topic.texts"), nominal),
            distress_adjacent=_templates(lookup(cfg, "distress_adjacent.texts"), None),
            sources=(redteam_yaml, injection_yaml, wrappers_yaml, arabizi_yaml),
        )


def _rate(cfg: Mapping[str, Any], key: str) -> float:
    value = float(lookup(cfg, key))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"redteam.yaml {key} must be in [0, 1], got {value}")
    return value


def _positive_int(cfg: Mapping[str, Any], key: str) -> int:
    value = lookup(cfg, key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"redteam.yaml {key} must be a positive integer, got {value!r}")
    return value


def _priority(value: object) -> Priority:
    try:
        return Priority(str(value))
    except ValueError as exc:
        raise ValueError(f"redteam.yaml: unknown priority {value!r}") from exc


def _category(value: object) -> Category:
    try:
        return Category(str(value))
    except ValueError as exc:
        raise ValueError(f"redteam.yaml: unknown category {value!r}") from exc


def _lang(value: object) -> Lang:
    try:
        return Lang(str(value))
    except ValueError as exc:
        raise ValueError(f"redteam.yaml: unknown language {value!r}") from exc


def _lang_texts(cfg: Mapping[str, Any], key: str) -> LangTexts:
    node = lookup(cfg, key)
    if not isinstance(node, Mapping):
        raise ValueError(f"redteam.yaml {key} must map a language to a list of texts")
    out = {_lang(lang): tuple(string_list(node, str(lang))) for lang in node}
    missing = [lang.value for lang in REQUIRED_LANGS if not out.get(lang)]
    if missing:
        raise ValueError(f"redteam.yaml {key} needs a non-empty list for {missing}")
    return out


def _by_lang(texts: Sequence[str]) -> LangTexts:
    grouped: dict[Lang, list[str]] = {}
    for text in texts:
        grouped.setdefault(text_lang(text), []).append(text)
    return {lang: tuple(items) for lang, items in grouped.items()}


def _calm(wrappers: Sequence[str], markers: Sequence[str]) -> list[str]:
    return [w for w in wrappers if not any(m in w for m in markers)]


def _positions(values: Sequence[str]) -> tuple[str, ...]:
    unknown = sorted(set(values) - INJECTION_POSITIONS)
    if not values or unknown:
        raise ValueError(
            f"redteam.yaml injection.positions must be a subset of {sorted(INJECTION_POSITIONS)}"
        )
    return tuple(values)


def _pairs(node: object, key: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(node, list) or not all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p) for p in node
    ):
        raise ValueError(f"redteam.yaml {key} must be a list of [text, text] pairs")
    return tuple((str(a), str(b)) for a, b in node)


def _templates(node: object, nominal: object) -> tuple[Template, ...]:
    if not isinstance(node, list) or not node:
        raise ValueError("redteam.yaml: a template list must be a non-empty list")
    defaults: Mapping[str, Any] = nominal if isinstance(nominal, Mapping) else {}
    out: list[Template] = []
    for entry in node:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("text"), str):
            raise ValueError(f"redteam.yaml: bad template entry {entry!r}")
        out.append(
            Template(
                text=entry["text"],
                lang=_lang(entry.get("lang")),
                category=_category(entry.get("category", defaults.get("category"))),
                priority=_priority(entry.get("priority", defaults.get("priority"))),
                flags=frozenset(string_list(entry, "flags")) if "flags" in entry else frozenset(),
            )
        )
    return tuple(out)


def _arabizi(cfg: Mapping[str, Any], arabizi_lexicon: Mapping[str, Any]) -> ArabiziConfig:
    proclitics = _pairs(lookup(cfg, "arabizi.proclitics"), "arabizi.proclitics")
    lexicon: dict[str, str] = {}
    for latin, arabic in dict(lookup(arabizi_lexicon, "lexicon")).items():
        lexicon.setdefault(normalize_text(str(arabic), "ar"), str(latin))
    return ArabiziConfig(
        charmap={str(k): str(v) for k, v in dict(lookup(cfg, "arabizi.charmap")).items()},
        final_heh=str(lookup(cfg, "arabizi.final_heh")),
        medial_vowels={str(k): str(v) for k, v in dict(lookup(cfg, "arabizi.medial_vowels")).items()},
        proclitics=proclitics,
        min_stem=_positive_int(cfg, "arabizi.min_stem"),
        lexicon=lexicon,
    )
