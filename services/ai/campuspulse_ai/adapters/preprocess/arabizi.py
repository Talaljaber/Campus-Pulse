"""Arabizi → Arabic-script transliteration (P1.2, ARCHITECTURE §3.7, SPEC §5.1[2]).

Models see `"<transliteration> | <original>"`, so the encoder gets both the Arabic reading and the raw
Latin text; a wrong transliteration never removes the original signal.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from campuspulse_ai.adapters.preprocess.wrappers import normalize_text

# chunk = leading punctuation, word core (letters/digits, inner joiners, Arabizi apostrophe), trailing punct.
_CHUNK = re.compile(r"^([^a-z0-9']*)([a-z0-9'](?:[a-z0-9'/:.-]*[a-z0-9'])?)?([^a-z0-9']*)$")
MODEL_TEXT_SEPARATOR = " | "


class ArabiziTransliterator:
    """Lexicon-first transliteration of Latin-script Jordanian Arabic.

    Per whitespace token (lower-cased):
      1. a standalone proclitic (`el`, `w`, `b`, `bel`, ...) is glued to the next token (`el bus` → `الباص`);
      2. a whole-token lexicon hit (`mesh` → `مش`), or a proclitic + lexicon word (`elbus` → `الباص`);
      3. otherwise digraphs (longest first: `sh`, `kh`, `3'`, ...) then the single-character map
         (`2`→ء, `3`→ع, `5`→خ, `6`→ط, `7`→ح, `8`→ق, `9`→ص, ...); unmapped characters are kept.
    Latin punctuation is mapped (`?`→`؟`, `,`→`،`), then the whole output is normalized exactly like an
    Arabic `text_norm` (`normalize_text(..., "ar")`), so it matches the training-text conventions.
    """

    def __init__(
        self,
        lexicon: Mapping[str, str],
        digraphs: Mapping[str, str],
        charmap: Mapping[str, str],
        *,
        proclitics: Mapping[str, str] | None = None,
        punctuation: Mapping[str, str] | None = None,
    ) -> None:
        """
        Args:
            lexicon: lower-case Arabizi word → Arabic.
            digraphs: multi-character Latin sequences → Arabic (tried longest first).
            charmap: single Latin letter or digit → Arabic (may be "" to drop, e.g. short vowel `e`).
            proclitics: standalone/attached prefixes → Arabic (`el` → `ال`).
            punctuation: Latin punctuation → Arabic punctuation.
        """
        self._lexicon = {k.lower(): v for k, v in lexicon.items()}
        pairs = [(k.lower(), v) for k, v in digraphs.items()]
        self._digraphs = sorted(pairs, key=lambda kv: (-len(kv[0]), kv[0]))
        self._charmap = {k.lower(): v for k, v in charmap.items()}
        self._proclitics = {k.lower(): v for k, v in (proclitics or {}).items()}
        self._proclitic_order = sorted(self._proclitics, key=lambda p: (-len(p), p))
        self._punct = str.maketrans(dict(punctuation or {}))

    @classmethod
    def from_yaml(cls, path: Path) -> ArabiziTransliterator:
        """Build from `config/lexicons/arabizi.yaml` (or its model-dir snapshot)."""
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            lexicon={str(k): str(v) for k, v in cfg["lexicon"].items()},
            digraphs={str(k): str(v) for k, v in cfg["digraphs"].items()},
            charmap={str(k): str(v) for k, v in cfg["charmap"].items()},
            proclitics={str(k): str(v) for k, v in cfg.get("proclitics", {}).items()},
            punctuation={str(k): str(v) for k, v in cfg.get("punctuation", {}).items()},
        )

    def _chars(self, word: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(word):
            for key, value in self._digraphs:
                if word.startswith(key, i):
                    out.append(value)
                    i += len(key)
                    break
            else:
                out.append(self._charmap.get(word[i], word[i]))
                i += 1
        return "".join(out)

    def _word(self, word: str) -> str:
        if word in self._lexicon:
            return self._lexicon[word]
        for p in self._proclitic_order:
            rest = word[len(p) :]
            if word.startswith(p) and len(rest) > 1 and rest in self._lexicon:
                return self._proclitics[p] + self._lexicon[rest]
        return self._chars(word)

    def transliterate(self, text: str) -> str:
        """Arabic-script reading of `text`, normalized like an Arabic `text_norm`."""
        pieces: list[str] = []
        pending = ""
        for chunk in text.lower().split():
            m = _CHUNK.match(chunk)
            if m is None:  # mixed scripts or symbols: keep as is
                pieces.append(pending + chunk)
                pending = ""
                continue
            lead, core, trail = m.group(1), m.group(2) or "", m.group(3)
            if core in self._proclitics and not lead and not trail:
                pending += self._proclitics[core]
                continue
            word = self._word(core) if core else ""
            pieces.append(lead.translate(self._punct) + pending + word + trail.translate(self._punct))
            pending = ""
        if pending:
            pieces.append(pending)
        return normalize_text(" ".join(pieces), "ar")

    def model_text(self, original: str) -> str:
        """What the models see for an Arabizi request: `f"{transliterate(original)} | {original}"`."""
        return f"{self.transliterate(original)}{MODEL_TEXT_SEPARATOR}{original}"
