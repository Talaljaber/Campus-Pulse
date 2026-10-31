"""`LexiconEvidenceExtractor`: the ten labeller-rule evidence flags for the priority head (P1.12, §3.8).

The flags are features, not rules: `LogisticPriorityHead` learns their weights on OOF data. The extractor
only ever reads `req.model_text`; it has no access to `stated_urgency`, so an `URGENT:` wrapper can never
change a flag (the wrapper is stripped before `model_text` exists).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from campuspulse_ai.adapters.preprocess.arabizi import MODEL_TEXT_SEPARATOR
from campuspulse_ai.adapters.preprocess.patterns import compile_patterns, load_yaml
from campuspulse_ai.domain.priority_rules import EVIDENCE_FEATURES, FORBIDDEN_FEATURES
from campuspulse_ai.domain.values import Evidence, EvidenceVector, Lang, NormalizedRequest

INFO_REQUEST = "info_request"
FAULT_REPORT = "fault_report"
LANG_KEYS: tuple[str, ...] = ("en", "ar", "arabizi")
_ARABIC = re.compile(r"[؀-ۿ]")


class LexiconEvidenceExtractor:
    """Implements `domain.ports.EvidenceExtractor`.

    `extract(req)` returns `EvidenceVector(flags, spans)`: `flags` has exactly `features` as keys, in that
    order (default `EVIDENCE_FEATURES`); a flag is true when any of its patterns matches `req.model_text`.
    `info_request` is special: true when a `start` pattern matches at the start of the text (or of either
    half of an Arabizi `translit | original` text) or an `info_request` pattern matches anywhere, AND
    `fault_report` is false ("where is the bus timetable" is a request for information; "where is the bus,
    it is late" is a fault). `spans` holds one `Evidence(feature, matched text, lang)` per hit, where `lang`
    is AR for Arabic-script spans, else ARABIZI for an Arabizi request, else EN. Pure: never raises.
    """

    def __init__(
        self,
        patterns: Mapping[str, Sequence[re.Pattern[str]]],
        start_patterns: Mapping[str, Sequence[re.Pattern[str]]],
        features: Sequence[str] = EVIDENCE_FEATURES,
    ) -> None:
        """
        Args:
            patterns: feature -> compiled patterns (searched anywhere).
            start_patterns: feature -> compiled patterns that must match at the start (`info_request`).
            features: the ordered feature names (`FrozenConfig.priority_head.features`).

        Raises:
            ValueError: a forbidden feature (`stated_urgency`), a pattern for an unknown feature, or a feature
                with no pattern at all.
        """
        banned = FORBIDDEN_FEATURES.intersection(features)
        if banned:
            raise ValueError(f"{sorted(banned)} must never be an evidence feature (§3.8)")
        unknown = (set(patterns) | set(start_patterns)) - set(features)
        if unknown:
            raise ValueError(f"patterns for unknown features {sorted(unknown)}")
        empty = [f for f in features if not patterns.get(f) and not start_patterns.get(f)]
        if empty:
            raise ValueError(f"features without patterns: {empty}")
        self.features: tuple[str, ...] = tuple(features)
        self._patterns = {f: tuple(patterns.get(f, ())) for f in self.features}
        self._start = {f: tuple(start_patterns.get(f, ())) for f in self.features}

    @classmethod
    def from_yaml(cls, path: Path, features: Sequence[str] = EVIDENCE_FEATURES) -> LexiconEvidenceExtractor:
        """Build from `config/lexicons/urgency.yaml` (or its model-dir snapshot, LD-12).

        Raises:
            KeyError: a feature block is missing. ValueError / re.error: an invalid block or regex.
        """
        banned = FORBIDDEN_FEATURES.intersection(features)
        if banned:
            raise ValueError(f"{sorted(banned)} must never be an evidence feature (§3.8)")
        blocks = load_yaml(path)["features"]
        patterns: dict[str, list[re.Pattern[str]]] = {}
        starts: dict[str, list[re.Pattern[str]]] = {}
        for feature in features:
            block = blocks[feature]
            patterns[feature] = compile_patterns(p for lang in LANG_KEYS for p in block.get(lang) or [])
            start = block.get("start") or {}
            skip = "|".join(f"(?:{s})" for s in block.get("start_skip") or [])
            lead = rf"^(?:(?:{skip})(?![^\W\d_])[\W_]*)*" if skip else "^"
            starts[feature] = compile_patterns(lead + p.removeprefix("^")
                                               for lang in LANG_KEYS for p in start.get(lang) or [])
        return cls(patterns, starts, features)

    def extract(self, req: NormalizedRequest) -> EvidenceVector:
        text = req.model_text
        parts = [p.strip() for p in text.split(MODEL_TEXT_SEPARATOR.strip())]
        hits: dict[str, list[str]] = {}
        for feature in self.features:
            found = [m.group(0) for p in self._patterns[feature] for m in p.finditer(text) if m.group(0)]
            found += [m.group(0) for p in self._start[feature] for part in parts
                      if (m := p.match(part)) is not None and m.group(0)]
            hits[feature] = found
        if hits.get(FAULT_REPORT) and INFO_REQUEST in hits:
            hits[INFO_REQUEST] = []
        flags = {f: bool(hits[f]) for f in self.features}
        spans: list[Evidence] = []
        for feature in self.features:
            for span in dict.fromkeys(hits[feature]):
                spans.append(Evidence(feature, span, _span_lang(span, req.lang)))
        return EvidenceVector(flags=flags, spans=tuple(spans))


def _span_lang(span: str, lang: Lang) -> Lang:
    if _ARABIC.search(span):
        return Lang.AR
    return Lang.ARABIZI if lang is Lang.ARABIZI else Lang.EN
