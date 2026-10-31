"""`DefaultNormalizer`: the `Normalizer` port implementation every path uses (P1.3, ARCHITECTURE §1.4)."""

from __future__ import annotations

from pathlib import Path

from campuspulse_ai.adapters.preprocess.arabizi import ArabiziTransliterator
from campuspulse_ai.adapters.preprocess.langid import LangIdentifier
from campuspulse_ai.adapters.preprocess.location import LocationExtractor
from campuspulse_ai.adapters.preprocess.wrappers import WrapperStripper, normalize_text, script_lang
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.values import Lang, Location, NormalizedRequest


class DefaultNormalizer:
    """raw text → `NormalizedRequest` (implements `domain.ports.Normalizer`).

    Steps:
      1. reject empty/whitespace-only input (`InvalidInput`);
      2. strip wrappers (`WrapperStripper`), which also sets `stated_urgency`;
      3. truncate the core to `max_tokens` whitespace tokens (`truncated=True` when cut);
      4. `text_norm = normalize_text(core, script_lang(core))`; reject an empty `text_norm` (punctuation
         only) as `InvalidInput` too;
      5. `lang = langid.identify(core)`; `model_text` = `translit | text_norm` for ARABIZI, else `text_norm`;
      6. location: a picked location beats an extracted one; no extractor → None.
    On the 432 official rows `core` and `text_norm` equal `data/clean` byte for byte.
    `stated_urgency` is for the gaming detector only and is never a model input.
    """

    def __init__(
        self,
        wrappers: WrapperStripper,
        langid: LangIdentifier,
        arabizi: ArabiziTransliterator,
        location: LocationExtractor | None,
        max_tokens: int,
    ) -> None:
        """
        Args:
            wrappers, langid, arabizi: the P1.1/P1.2 components.
            location: optional extractor (None offline if the cut-flagged sub-step is deferred).
            max_tokens: `FrozenConfig.guards.max_tokens`.

        Raises:
            ValueError: `max_tokens` < 1.
        """
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self._wrappers = wrappers
        self._langid = langid
        self._arabizi = arabizi
        self._location = location
        self._max_tokens = max_tokens

    @classmethod
    def from_lexicons(
        cls, lexicon_dir: Path, max_tokens: int, *, with_location: bool = True
    ) -> DefaultNormalizer:
        """Build from a lexicon directory (`config/lexicons` or a model dir's `lexicons/` snapshot, LD-12)."""
        location = LocationExtractor.from_yaml(lexicon_dir / "gazetteer.yaml") if with_location else None
        return cls(
            wrappers=WrapperStripper.from_yaml(lexicon_dir / "wrappers.yaml"),
            langid=LangIdentifier.from_yaml(lexicon_dir / "arabizi.yaml"),
            arabizi=ArabiziTransliterator.from_yaml(lexicon_dir / "arabizi.yaml"),
            location=location,
            max_tokens=max_tokens,
        )

    def normalize(self, raw: str, picked_location: Location | None = None) -> NormalizedRequest:
        """Normalize one raw request.

        Raises:
            InvalidInput: `raw` is empty/whitespace, or nothing but punctuation remains after normalization.
        """
        if not raw or not raw.strip():
            raise InvalidInput("empty request text")
        stripped = self._wrappers.strip(raw)
        tokens = stripped.core.split(" ")
        truncated = len(tokens) > self._max_tokens
        core = " ".join(tokens[: self._max_tokens]) if truncated else stripped.core
        text_norm = normalize_text(core, script_lang(core))
        if not text_norm:
            raise InvalidInput("request text has no content after normalization")
        lang = self._langid.identify(core)
        model_text = self._arabizi.model_text(text_norm) if lang is Lang.ARABIZI else text_norm
        location = picked_location
        if location is None and self._location is not None:
            location = self._location.extract(core)
        return NormalizedRequest(
            raw=raw,
            core=core,
            text_norm=text_norm,
            model_text=model_text,
            lang=lang,
            is_arabizi=lang is Lang.ARABIZI,
            stated_urgency=stripped.stated_urgency,
            truncated=truncated,
            location=location,
        )
