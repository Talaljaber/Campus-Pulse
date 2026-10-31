"""PerturbationGenerator: the rule-based, seeded `RedTeamGenerator` (P4.11, ARCHITECTURE §2.4).

`generate(n, styles, seed)` returns `n` items spread round-robin over the requested styles in
`ALL_STYLES` order (an empty `styles` means every style these seeds can feed). Each style draws from
its own `random.Random(f"{seed}:{style}")`, so the same seed gives the same items, and asking for a
subset of styles gives the same items for those styles. Seed rows are drawn as shuffled passes over
the eligible rows (no repeat until every row was used once).

| style | made from | intended labels | `base_text` |
| --- | --- | --- | --- |
| fake_urgency | a low/medium row + URGENT!! / عاجل جدا prefix (and sometimes suffix) | the row's | the row |
| calm_emergency | a template with a place | the template's (high) | — |
| typos | a row, letters swapped (p=`swap_rate`) or dropped (p=`drop_rate`) | the row's | the row |
| arabizi | an Arabic row, reverse-transliterated | the row's | the row |
| mixed_language | a row, glossary words swapped, a phrase of the other language added | the row's | the row |
| two_issues | two rows of one language and different categories, joined | the more urgent row's | — |
| very_long | a row inside a wrapper greeting and benign filler (`target_chars`) | the row's | the row |
| injection | a row with an injection exemplar (`injection.yaml`) before or after it | the row's | the row |
| off_topic | the fixed list | nominal (ignored by the rule) | — |
| distress_adjacent | the fixed list | the template's | — |

The generator never reads a file: seed rows come from `adapters/redteam/seeds.py` (official training
rows or a supplied CSV; holdouts are refused) and the lists from `RedTeamConfig`.

Errors: `InvalidInput` for `n < 1`, an unknown style, or a requested style these seeds cannot feed
(e.g. `arabizi` without Arabic rows). No side effects.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TypeVar

from campuspulse_ai.adapters.preprocess.wrappers import normalize_text
from campuspulse_ai.adapters.redteam.config import RedTeamConfig, Template, for_lang
from campuspulse_ai.application.services.redteam_styles import (
    ALL_STYLES,
    ARABIZI,
    CALM_EMERGENCY,
    DISTRESS_ADJACENT,
    DISTRESS_FLAG,
    FAKE_URGENCY,
    INJECTION,
    INJECTION_FLAG,
    MIXED_LANGUAGE,
    OFF_TOPIC,
    TWO_ISSUES,
    TYPOS,
    VERY_LONG,
)
from campuspulse_ai.domain.entities import RedTeamItem
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang

PLACE_SLOT = "{place}"
PHRASE_SIDES = ("prefix", "suffix")
"""A code-switching phrase opens or closes the request with equal chance."""
_MIN_SWAP_LEN = 2
"""A forced typo needs two letters to swap."""


@dataclass(frozen=True, slots=True)
class SeedRow:
    """One labelled text to perturb (the plan's `OurTestRow`, but never a holdout row: D-013)."""

    request_id: str
    text: str
    lang: Lang
    category: Category
    priority: Priority


T = TypeVar("T")
Maker = Callable[[random.Random, int], list[RedTeamItem]]


class PerturbationGenerator:
    """`RedTeamGenerator` over seed rows and `RedTeamConfig` (see the module docstring)."""

    def __init__(self, rows: Sequence[SeedRow], config: RedTeamConfig) -> None:
        self._rows = tuple(rows)
        self._cfg = config
        self._latin = tuple(r for r in self._rows if r.lang is not Lang.AR)
        self._arabic = tuple(r for r in self._rows if r.lang is Lang.AR)
        self._makers: dict[str, Maker] = {
            FAKE_URGENCY: self._fake_urgency,
            CALM_EMERGENCY: self._calm_emergency,
            TYPOS: self._typos,
            ARABIZI: self._arabizi,
            MIXED_LANGUAGE: self._mixed_language,
            TWO_ISSUES: self._two_issues,
            VERY_LONG: self._very_long,
            INJECTION: self._injection,
            OFF_TOPIC: self._off_topic,
            DISTRESS_ADJACENT: self._distress_adjacent,
        }
        self._pools: dict[str, tuple[SeedRow, ...]] = {
            FAKE_URGENCY: tuple(r for r in self._rows if r.priority in config.fake_urgency.base_priorities),
            TYPOS: self._rows,
            ARABIZI: self._arabic,
            MIXED_LANGUAGE: self._rows,
            TWO_ISSUES: self._rows if self._two_issue_pairs_exist() else (),
            VERY_LONG: self._rows,
            INJECTION: tuple(r for r in self._rows if for_lang(config.injection.phrases, r.lang)),
        }

    @property
    def available_styles(self) -> tuple[str, ...]:
        """The styles these seeds and lists can feed, in canonical order."""
        return tuple(s for s in ALL_STYLES if s not in self._pools or self._pools[s])

    def generate(self, n: int, styles: Sequence[str], seed: int) -> list[RedTeamItem]:
        """`n` items over `styles` (empty = all available); see the module docstring."""
        if n < 1:
            raise InvalidInput(f"n must be at least 1, got {n}")
        chosen = self._resolve(styles)
        counts = {s: n // len(chosen) + (1 if i < n % len(chosen) else 0) for i, s in enumerate(chosen)}
        items: list[RedTeamItem] = []
        for style in chosen:
            if counts[style]:
                items.extend(self._makers[style](random.Random(f"{seed}:{style}"), counts[style]))
        return items

    def _resolve(self, styles: Sequence[str]) -> tuple[str, ...]:
        if not styles:
            return self.available_styles
        unknown = sorted(set(styles) - set(ALL_STYLES))
        if unknown:
            raise InvalidInput(f"unknown red-team style(s) {unknown}; known: {list(ALL_STYLES)}")
        unfed = sorted(set(styles) - set(self.available_styles))
        if unfed:
            raise InvalidInput(f"the seed rows cannot feed style(s) {unfed} (e.g. arabizi needs Arabic rows)")
        wanted = set(styles)
        return tuple(s for s in ALL_STYLES if s in wanted)

    # ------------------------------------------------------------------ styles built from seed rows

    def _fake_urgency(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        cfg = self._cfg.fake_urgency
        out = []
        for row in _draw(rng, self._pools[FAKE_URGENCY], k):
            text = f"{rng.choice(for_lang(cfg.prefixes, row.lang))} {row.text}"
            if rng.random() < cfg.suffix_rate:
                text = f"{text} {rng.choice(for_lang(cfg.suffixes, row.lang))}"
            out.append(_from_row(row, text, FAKE_URGENCY))
        return out

    def _typos(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        return [_from_row(r, self._misspell(rng, r.text), TYPOS) for r in _draw(rng, self._rows, k)]

    def _misspell(self, rng: random.Random, text: str) -> str:
        cfg = self._cfg.typos
        words = text.split(" ")
        for w, word in enumerate(words):
            if sum(ch.isalpha() for ch in word) < cfg.min_word_letters:
                continue
            chars = list(word)
            out: list[str] = []
            i = 0
            while i < len(chars):
                swappable = i + 1 < len(chars) and chars[i].isalpha() and chars[i + 1].isalpha()
                roll = rng.random()
                if swappable and roll < cfg.swap_rate:
                    out.extend((chars[i + 1], chars[i]))
                    i += 2
                    continue
                if chars[i].isalpha() and roll < cfg.swap_rate + cfg.drop_rate:
                    i += 1
                    continue
                out.append(chars[i])
                i += 1
            words[w] = "".join(out)
        typo = " ".join(words)
        return typo if typo != text else _force_swap(rng, text)

    def _arabizi(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        out = []
        for row in _draw(rng, self._arabic, k):
            item = _from_row(row, self._to_arabizi(row.text), ARABIZI)
            out.append(_replace_lang(item, Lang.ARABIZI))
        return out

    def _to_arabizi(self, arabic: str) -> str:
        """One Arabizi spelling (lexicon word, else proclitic + lexicon/char map, else char map)."""
        cfg = self._cfg.arabizi
        tokens: list[str] = []
        for word in normalize_text(arabic, "ar").split():
            if word in cfg.lexicon:
                tokens.append(cfg.lexicon[word])
                continue
            for prefix, latin in cfg.proclitics:
                stem = word[len(prefix) :]
                if word.startswith(prefix) and len(stem) >= cfg.min_stem and stem in cfg.lexicon:
                    tokens.extend((latin, cfg.lexicon[stem]))
                    break
            else:
                tokens.append(self._chars(word))
        return " ".join(tokens)

    def _chars(self, word: str) -> str:
        cfg = self._cfg.arabizi
        out: list[str] = []
        last = len(word) - 1
        for i, ch in enumerate(word):
            if i == last and i > 0 and ch == "ه":
                out.append(cfg.final_heh)
            elif i > 0 and ch in cfg.medial_vowels:
                out.append(cfg.medial_vowels[ch])
            else:
                out.append(cfg.charmap.get(ch, ch))
        return "".join(out)

    def _mixed_language(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        cfg = self._cfg.mixed_language
        out = []
        for row in _draw(rng, self._rows, k):
            text = row.text
            swaps = 0
            for en, ar in rng.sample(cfg.glossary, len(cfg.glossary)):
                if swaps >= cfg.max_swaps:
                    break
                source, target = (ar, en) if row.lang is Lang.AR else (en, ar)
                pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", re.IGNORECASE)
                text, hits = pattern.subn(target, text, count=1)
                swaps += hits
            phrase = rng.choice(for_lang(cfg.phrases, row.lang))
            text = f"{phrase} {text}" if rng.choice(PHRASE_SIDES) == "prefix" else f"{text} {phrase}"
            out.append(_from_row(row, text, MIXED_LANGUAGE))
        return out

    def _two_issue_pairs_exist(self) -> bool:
        return any(len({r.category for r in rows}) > 1 for rows in (self._latin, self._arabic) if rows)

    def _two_issues(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        out = []
        for first in _draw(rng, self._pools[TWO_ISSUES], k):
            same_lang = self._arabic if first.lang is Lang.AR else self._latin
            others = [r for r in same_lang if r.category != first.category]
            if not others:  # this row's language has one category only: pair within the other script
                others = [r for r in self._rows if r.category != first.category]
            second = rng.choice(others)
            joiner = rng.choice(for_lang(self._cfg.two_issues_joiners, first.lang))
            lead = first if first.priority.rank >= second.priority.rank else second
            out.append(
                RedTeamItem(
                    text=f"{first.text}{joiner}{second.text}",
                    style=TWO_ISSUES,
                    lang=first.lang,
                    intended_category=lead.category,
                    intended_priority=lead.priority,
                    base_id=f"{first.request_id}+{second.request_id}",
                )
            )
        return out

    def _very_long(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        cfg = self._cfg.very_long
        out = []
        for row in _draw(rng, self._rows, k):
            filler = list(for_lang(cfg.filler, row.lang))
            rng.shuffle(filler)
            before: list[str] = []
            after: list[str] = []
            prefixes = for_lang(cfg.wrapper_prefixes, row.lang)
            suffixes = for_lang(cfg.wrapper_suffixes, row.lang)
            head = [rng.choice(prefixes)] if prefixes else []
            tail = [rng.choice(suffixes)] if suffixes else []
            i = 0
            while len(" ".join((*head, *before, row.text, *after, *tail))) < cfg.target_chars:
                (before if i % 2 == 0 else after).append(filler[i % len(filler)])
                i += 1
            out.append(_from_row(row, " ".join((*head, *before, row.text, *after, *tail)), VERY_LONG))
        return out

    def _injection(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        cfg = self._cfg.injection
        out = []
        for row in _draw(rng, self._pools[INJECTION], k):
            phrase = rng.choice(for_lang(cfg.phrases, row.lang))
            text = f"{phrase} {row.text}" if rng.choice(cfg.positions) == "prefix" else f"{row.text} {phrase}"
            out.append(_from_row(row, text, INJECTION, frozenset({INJECTION_FLAG})))
        return out

    # ------------------------------------------------------------------ styles built from fixed lists

    def _calm_emergency(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        out = []
        for t in _draw(rng, self._cfg.calm_templates, k):
            text = t.text.replace(PLACE_SLOT, rng.choice(for_lang(self._cfg.calm_places, t.lang)))
            out.append(_from_template(t, text, CALM_EMERGENCY))
        return out

    def _off_topic(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        return [_from_template(t, t.text, OFF_TOPIC) for t in _draw(rng, self._cfg.off_topic, k)]

    def _distress_adjacent(self, rng: random.Random, k: int) -> list[RedTeamItem]:
        return [
            _from_template(t, t.text, DISTRESS_ADJACENT, frozenset({DISTRESS_FLAG}))
            for t in _draw(rng, self._cfg.distress_adjacent, k)
        ]


def _draw(rng: random.Random, pool: Sequence[T], k: int) -> list[T]:
    """`k` entries as shuffled passes over `pool`: no repeat before every entry was used once."""
    out: list[T] = []
    while len(out) < k:
        batch = list(pool)
        rng.shuffle(batch)
        out.extend(batch)
    return out[:k]


def _force_swap(rng: random.Random, text: str) -> str:
    """Swap two neighbouring letters of one word, for a text the random pass left unchanged."""
    spots = [i for i in range(len(text) - 1) if text[i].isalpha() and text[i + 1].isalpha()]
    spots = [i for i in spots if text[i] != text[i + 1]]
    if len(text) < _MIN_SWAP_LEN or not spots:
        return text
    i = rng.choice(spots)
    return f"{text[:i]}{text[i + 1]}{text[i]}{text[i + 2 :]}"


def _from_row(row: SeedRow, text: str, style: str, flags: frozenset[str] = frozenset()) -> RedTeamItem:
    return RedTeamItem(
        text=text,
        style=style,
        lang=row.lang,
        intended_category=row.category,
        intended_priority=row.priority,
        expected_flags=flags,
        base_text=row.text,
        base_id=row.request_id,
    )


def _from_template(t: Template, text: str, style: str, flags: frozenset[str] = frozenset()) -> RedTeamItem:
    return RedTeamItem(
        text=text,
        style=style,
        lang=t.lang,
        intended_category=t.category,
        intended_priority=t.priority,
        expected_flags=flags | t.flags,
    )


def _replace_lang(item: RedTeamItem, lang: Lang) -> RedTeamItem:
    return replace(item, lang=lang)
