"""Language identification: EN, AR or ARABIZI (P1.2, ARCHITECTURE §3.7, LD-33).

The official data has no Arabizi and its `lang` column is script-only, so this class is the only
source of the ARABIZI label. It errs towards EN: a false Arabizi positive on an English hidden-test
row is the only way this step can cost macro-F1.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import yaml

from campuspulse_ai.domain.values import Lang

_ARABIC_LETTER = re.compile(r"[؀-ۿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
# Latin-script tokens: letters, digits and the joiners used in Arabizi (3'), times (24/7) and codes (cs-201).
_TOKEN = re.compile(r"[a-z0-9]+(?:['/.:-][a-z0-9]+)*'?")


def latin_tokens(text: str) -> list[str]:
    """Lower-cased Latin/digit tokens of `text`, outer punctuation removed."""
    return _TOKEN.findall(text.lower())


class LangIdentifier:
    """Rule-based EN / AR / ARABIZI identifier.

    Rules, in order:
      1. Arabic-block characters outnumber Latin letters → `Lang.AR` (the `clean_data.detect_lang` rule).
      2. Any guard hit (a token in `guard_tokens`, or fully matching a `guard_patterns` regex) → `Lang.EN`.
      3. ≥ `min_digit_tokens` Arabizi digit-words, or ≥ `min_lexicon_hits` `lexicon` tokens → `Lang.ARABIZI`.
      4. Otherwise `Lang.EN`.
    An Arabizi digit-word has a signal digit (2/3/5/6/7/8/9) touching a Latin letter, at least
    `min_letters_in_digit_token` letters, and does not fully match an `ignore_patterns` regex (course and
    room codes such as `cs201`, `m214`).
    """

    def __init__(
        self,
        lexicon: frozenset[str],
        guard_tokens: frozenset[str],
        signal_digits: frozenset[str],
        min_digit_tokens: int,
        min_lexicon_hits: int,
        *,
        guard_patterns: Sequence[str] = (),
        ignore_patterns: Sequence[str] = (),
        min_letters_in_digit_token: int = 1,
    ) -> None:
        """
        Args:
            lexicon: lower-case Arabizi words that count as evidence (English homographs excluded).
            guard_tokens: lower-case tokens that veto ARABIZI (English function words, "2nd", ...).
            signal_digits: digits used as letters in Arabizi.
            min_digit_tokens: digit-words needed for ARABIZI.
            min_lexicon_hits: lexicon words needed for ARABIZI.
            guard_patterns: full-token regexes that also veto (ordinals, clock times, units, versions).
            ignore_patterns: full-token regexes for tokens that are neither evidence nor guards.
            min_letters_in_digit_token: letters a digit-word must contain.

        Raises:
            ValueError: a word is both evidence and a guard (a configuration error).
        """
        overlap = lexicon & guard_tokens
        if overlap:
            raise ValueError(f"tokens are both Arabizi evidence and guards: {sorted(overlap)}")
        self._lexicon = lexicon
        self._guards = guard_tokens
        self._guard_res = tuple(re.compile(p) for p in guard_patterns)
        self._ignore_res = tuple(re.compile(p) for p in ignore_patterns)
        digits = "".join(sorted(signal_digits))
        self._digit_word = re.compile(f"[a-z][{digits}]|[{digits}][a-z]")
        self._min_digit_tokens = min_digit_tokens
        self._min_lexicon_hits = min_lexicon_hits
        self._min_letters = min_letters_in_digit_token

    @classmethod
    def from_yaml(cls, path: Path) -> LangIdentifier:
        """Build from `config/lexicons/arabizi.yaml` (or its model-dir snapshot).

        Evidence words = lexicon keys + multi-letter proclitics (`el`, `il`, ...) − `not_signals`.
        """
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        words = {str(k).lower() for k in cfg["lexicon"]}
        words |= {str(k).lower() for k in cfg.get("proclitics", {}) if len(str(k)) > 1}
        evidence = frozenset(words - {str(w).lower() for w in cfg.get("not_signals", [])})
        return cls(
            lexicon=evidence,
            guard_tokens=frozenset(str(t).lower() for t in cfg["guard_tokens"]),
            signal_digits=frozenset(str(d) for d in cfg["signal_digits"]),
            min_digit_tokens=int(cfg["min_digit_tokens"]),
            min_lexicon_hits=int(cfg["min_lexicon_hits"]),
            guard_patterns=list(cfg.get("guard_patterns", [])),
            ignore_patterns=list(cfg.get("ignore_patterns", [])),
            min_letters_in_digit_token=int(cfg.get("min_letters_in_digit_token", 1)),
        )

    def _is_guard(self, token: str) -> bool:
        return token in self._guards or any(r.fullmatch(token) for r in self._guard_res)

    def _is_digit_word(self, token: str) -> bool:
        if any(r.fullmatch(token) for r in self._ignore_res):
            return False
        letters = sum(ch.isascii() and ch.isalpha() for ch in token)
        return letters >= self._min_letters and self._digit_word.search(token) is not None

    def signals(self, text: str) -> tuple[int, int, int]:
        """(digit-words, lexicon hits, guard hits) over the Latin tokens of `text` (tests, debugging)."""
        tokens = latin_tokens(text)
        guards = sum(self._is_guard(t) for t in tokens)
        digit_words = sum(self._is_digit_word(t) for t in tokens if not self._is_guard(t))
        hits = sum(t in self._lexicon for t in tokens)
        return digit_words, hits, guards

    def identify(self, text: str) -> Lang:
        """Classify `text` as `Lang.AR`, `Lang.ARABIZI` or `Lang.EN` (rules in the class docstring)."""
        if len(_ARABIC_LETTER.findall(text)) > len(_LATIN_LETTER.findall(text)):
            return Lang.AR
        digit_words, hits, guards = self.signals(text)
        if guards:
            return Lang.EN
        if digit_words >= self._min_digit_tokens or hits >= self._min_lexicon_hits:
            return Lang.ARABIZI
        return Lang.EN
