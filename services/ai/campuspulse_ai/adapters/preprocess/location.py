"""Location extraction from request text with a fictional gazetteer (P1.3, cut-flagged sub-step).

Consumed online only (incident clustering, P4). It never changes `text_norm` or `model_text`, so it
cannot affect predictions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from campuspulse_ai.domain.values import Location

_BOUNDARY_START = r"(?<![A-Za-z0-9؀-ۿ])"
# Arabic-initial aliases may carry attached clitics ("بمبنى M", "المبنى M"), so only Latin/digits block them.
_BOUNDARY_START_ARABIC = r"(?<![A-Za-z0-9])"
_BOUNDARY_END = r"(?![A-Za-z0-9؀-ۿ])"
_ARABIC_INITIAL = re.compile(r"^[؀-ۿ]")


class LocationExtractor:
    """Finds a building (and room) mentioned in free text.

    A room match (`room_regex`, e.g. "M 214") wins, giving `Location("M", "M 214", "extracted")`.
    Otherwise the first building alias found gives `Location(code, None, "extracted")`. Aliases match
    case-insensitively, but the building code must appear upper-case in the text, so ordinary words
    ("a building") never match.
    """

    def __init__(self, buildings: Mapping[str, Sequence[str]], room_regex: str) -> None:
        """
        Args:
            buildings: building code -> alias phrases (each containing the code, e.g. "building M").
            room_regex: regex with named groups `building` and `number`.
        """
        self._room = re.compile(room_regex)
        self._codes = frozenset(buildings)
        self._aliases: list[tuple[str, re.Pattern[str]]] = []
        for code in sorted(buildings):
            for phrase in sorted(buildings[code], key=lambda p: (-len(p), p)):
                body = r"\s+".join(re.escape(part) for part in phrase.split())
                start = _BOUNDARY_START_ARABIC if _ARABIC_INITIAL.match(phrase) else _BOUNDARY_START
                pattern = re.compile(start + body + _BOUNDARY_END, re.IGNORECASE)
                self._aliases.append((code, pattern))

    @classmethod
    def from_yaml(cls, path: Path) -> LocationExtractor:
        """Build from `config/lexicons/gazetteer.yaml` (codes x alias_templates, room_regex)."""
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        templates = [str(t) for t in cfg["alias_templates"]]
        buildings = {str(code): [t.format(code=code) for t in templates] for code in cfg["buildings"]}
        return cls(buildings=buildings, room_regex=str(cfg["room_regex"]))

    def extract(self, text: str) -> Location | None:
        """The first room, else the first building alias, in `text`; None if nothing matches."""
        room = self._room.search(text)
        if room and room.group("building") in self._codes:
            building = room.group("building")
            return Location(building=building, room=f"{building} {room.group('number')}", source="extracted")
        for code, pattern in self._aliases:
            for match in pattern.finditer(text):
                if code in match.group(0).split():  # the code token itself is upper-case ("Block b" fails)
                    return Location(building=code, room=None, source="extracted")
        return None
