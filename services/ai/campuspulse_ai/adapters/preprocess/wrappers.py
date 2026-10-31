"""Wrapper stripping and text normalization, byte-for-byte compatible with scripts/clean_data.py (P1.1).

`collapse_ws`, `script_lang` and `normalize_text` copy `clean_data.collapse_ws`, `clean_data.detect_lang`
and `clean_data.normalize` literally (same regex, char map and punctuation set), so the package
reproduces `core` and `text_norm` for all 432 official rows (tests/unit/test_normalizer_parity.py).
`scripts/clean_data.py` itself is never imported here (ARCHITECTURE §3.7).

`WrapperStripper` runs the same iterative longest-first loop as `clean_data.strip_wrappers`, then, only
when no exact wrapper matches, falls back to case-insensitive and punctuation variants of the known
wrappers and a case-insensitive `urgent` prefix regex (data audit F6, LD-35).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import yaml

from campuspulse_ai.domain.values import StripResult

# --- literal copies of scripts/clean_data.py (do not edit; parity is tested on 432 rows) ---
AR_DIACRITICS = re.compile("[ً-ْٰـ]")  # harakat, dagger alif, tatweel
AR_CHARMAP = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه",
     "ؤ": "و", "ئ": "ي"}
)
PUNCT = " \t\n.,;:!?؟،؛-"
_ARABIC_LETTER = re.compile(r"[؀-ۿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_WS = re.compile(r"\s+")

ScriptLang = Literal["ar", "en"]


def collapse_ws(s: str) -> str:
    """Replace NBSP with a space, collapse whitespace runs, strip. Same as `clean_data.collapse_ws`."""
    return _WS.sub(" ", s.replace("\xa0", " ")).strip()


def script_lang(text: str) -> ScriptLang:
    """`"ar"` if Arabic-block characters outnumber Latin letters, else `"en"` (= `clean_data.detect_lang`)."""
    ar = len(_ARABIC_LETTER.findall(text))
    lat = len(_LATIN_LETTER.findall(text))
    return "ar" if ar > lat else "en"


def normalize_text(core: str, lang: ScriptLang) -> str:
    """Normalize a stripped core exactly like `clean_data.normalize`.

    English: collapse whitespace, lowercase. Arabic: remove diacritics/tatweel and map أإآ→ا, ى→ي, ة→ه,
    ؤ→و, ئ→ي. Both: collapse whitespace again, strip leading/trailing `PUNCT`.
    """
    s = collapse_ws(core)
    s = s.lower() if lang == "en" else AR_DIACRITICS.sub("", s).translate(AR_CHARMAP)
    s = collapse_ws(s)
    return s.strip(PUNCT)


class WrapperStripper:
    """Strips greeting/urgency wrappers from a raw request and reports stated urgency.

    Matching order inside every loop iteration (prefix side, then suffix side, as in clean_data):
      1. exact known strings, longest first (identical to `clean_data.strip_wrappers`);
      2. if `prefix_variants`: case-insensitive matches of the known strings and of their
         punctuation variants (base + one of `variant_punctuation`), longest first;
      3. prefix side only: `urgent_regex`.
    Any stripped prefix that matches `urgent_regex` (by whichever route) sets `stated_urgency`.
    A wrapper is stripped only if text remains after it. The loop repeats until nothing changes.
    """

    def __init__(
        self,
        prefixes: Sequence[str],
        suffixes: Sequence[str],
        urgency_markers: Sequence[str],
        urgent_regex: str,
        *,
        prefix_variants: bool = False,
        variant_punctuation: Sequence[str] = (),
    ) -> None:
        """
        Args:
            prefixes, suffixes: the exact known wrappers (clean_data.KNOWN_PREFIXES / KNOWN_SUFFIXES).
            urgency_markers: case-sensitive substrings of the raw text that set `stated_urgency`.
            urgent_regex: anchored regex for an urgency prefix; a match is stripped and sets `stated_urgency`.
            prefix_variants: enable the case-insensitive / punctuation-variant fallback (both sides).
            variant_punctuation: trailing punctuation marks that may replace a wrapper's own.
        """
        self._prefixes = sorted(prefixes, key=len, reverse=True)
        self._suffixes = sorted(suffixes, key=len, reverse=True)
        self._markers = tuple(urgency_markers)
        self._urgent = re.compile(urgent_regex)
        punct = "".join(variant_punctuation)
        self._lead_punct = punct if prefix_variants else ""
        marks = variant_punctuation
        self._prefix_variants = self._variants(prefixes, marks, punct) if prefix_variants else []
        self._suffix_variants = self._variants(suffixes, marks, punct) if prefix_variants else []

    @staticmethod
    def _variants(wrappers: Sequence[str], marks: Sequence[str], punct: str) -> list[str]:
        """Lower-cased known wrappers plus `base + mark` variants, longest first (deterministic order).

        `base` is the wrapper without its trailing punctuation: "Hello," -> "hello!", "hello:" ...;
        "وشكرا" -> "وشكرا.", "وشكرا!" .... A bare base is never a variant ("Please help me ..." is content).
        """
        out: set[str] = set()
        for wrapper in wrappers:
            out.add(wrapper.lower())
            base = wrapper.rstrip(punct + " ")
            if base:
                out.update((base + mark).lower() for mark in marks)
        return sorted(out, key=lambda v: (-len(v), v))

    @classmethod
    def from_yaml(cls, path: Path) -> WrapperStripper:
        """Build from `config/lexicons/wrappers.yaml` (or its snapshot in a model dir)."""
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            prefixes=list(cfg["prefixes"]),
            suffixes=list(cfg["suffixes"]),
            urgency_markers=list(cfg["urgency_markers"]),
            urgent_regex=str(cfg["urgent_regex"]),
            prefix_variants=bool(cfg.get("prefix_variants", False)),
            variant_punctuation=list(cfg.get("variant_punctuation", [])),
        )

    def _match_prefix(self, t: str) -> str | None:
        """The matched prefix text (exact, then variant, then urgent regex) or None."""
        for p in self._prefixes:
            if t.startswith(p) and len(t) > len(p):
                return p
        for v in self._prefix_variants:
            if len(t) > len(v) and t[: len(v)].lower() == v:
                return t[: len(v)]
        m = self._urgent.match(t)
        if m and m.end() > 0 and len(t) > m.end():
            return t[: m.end()]
        return None

    def _match_suffix(self, t: str) -> str | None:
        for s in self._suffixes:
            if t.endswith(s) and len(t) > len(s):
                return s
        for v in self._suffix_variants:
            if len(t) > len(v) and t[-len(v) :].lower() == v:
                return t[-len(v) :]
        return None

    def strip(self, raw: str) -> StripResult:
        """Strip wrappers from `raw` (whitespace collapsed first, as in clean_data).

        Returns:
            `StripResult(prefix, suffix, core, stated_urgency)`. `prefix`/`suffix` join the stripped
            wrappers with single spaces in text order. `stated_urgency` is true if a marker occurs in
            `raw` or a stripped prefix matches the urgent regex. Empty input gives an empty core (the
            normalizer rejects it).
        """
        t = collapse_ws(raw)
        pres: list[str] = []
        sufs: list[str] = []
        urgent = any(marker in raw for marker in self._markers)
        changed = True
        while changed:
            changed = False
            matched = self._match_prefix(t)
            if matched is not None:
                # "لو سمحت، ..." matches the exact "لو سمحت" first; drop the orphaned mark too
                # (no official core starts with punctuation, so parity is unaffected; tested).
                rest = t[len(matched) :].strip()
                t = rest.lstrip(self._lead_punct).strip() or rest
                pres.append(matched.strip())
                # any stripped urgency wrapper counts, whichever route matched it ("Urgent!" is a variant)
                urgent = urgent or self._urgent.match(matched) is not None
                changed = True
            sm = self._match_suffix(t)
            if sm is not None:
                t = t[: -len(sm)].strip()
                sufs.insert(0, sm)
                changed = True
        return StripResult(prefix=" ".join(pres), suffix=" ".join(sufs), core=t, stated_urgency=urgent)
