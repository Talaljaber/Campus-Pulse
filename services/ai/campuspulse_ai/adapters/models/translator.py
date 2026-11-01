"""Translators for the translate-test front of the encoder (P2.15, D-019, `docs/ml/models.md` §26-27).

`Ct2Translator` runs `Helsinki-NLP/opus-mt-ar-en` converted to CTranslate2 int8 with sentencepiece
tokenization only (no torch at inference). Greedy decoding (beam 1), one text per call to the runtime so a
text's translation never depends on its neighbours, 1 intra-op thread, and a small in-process LRU cache.
`ctranslate2` and `sentencepiece` are imported lazily, so a model directory with `translate.enabled = false`
never loads them.

Directory layout (`models/frozen/vN/translator/`, fetched with the encoder, never committed):

    translator_meta.json   model_id, revision, license, beam, max_len
    source.spm, target.spm sentencepiece models
    model.bin, config.json, shared_vocabulary.json (or the vocabulary files CTranslate2 wrote)
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch

TRANSLATOR_META = "translator_meta.json"
SOURCE_SPM = "source.spm"
TARGET_SPM = "target.spm"
MODEL_BIN = "model.bin"
FETCH_HINT = "run `python scripts/fetch_models.py` (or `python scripts/translate_test.py fetch`)"
DEFAULT_BEAM = 1
DEFAULT_MAX_LEN = 256
DEFAULT_CACHE_SIZE = 256


class NoopTranslator:
    """Returns every text unchanged (translate disabled, tests)."""

    model_id = "none"
    revision = "none"

    def translate(self, texts: Sequence[str]) -> list[str]:
        return list(texts)


def read_translator_meta(directory: Path) -> dict[str, Any]:
    """Load `translator_meta.json` and check that the model files exist.

    Raises:
        ArtifactMissing: the directory or one of its required files is absent.
        ArtifactVersionMismatch: unreadable JSON or a missing key.
    """
    directory = Path(directory)
    path = directory / TRANSLATOR_META
    if not path.is_file():
        raise ArtifactMissing(f"translator missing: {path} not found; {FETCH_HINT}")
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactVersionMismatch(f"{path}: unreadable translator meta: {exc}") from exc
    missing = [k for k in ("model_id", "revision") if k not in meta]
    if missing:
        raise ArtifactVersionMismatch(f"{path}: missing keys {missing}")
    for name in (SOURCE_SPM, TARGET_SPM, MODEL_BIN):
        if not (directory / name).is_file():
            raise ArtifactMissing(f"translator missing: {directory / name} not found; {FETCH_HINT}")
    return dict(meta)


class Ct2Translator:
    """Implements `domain.ports.Translator` with CTranslate2 int8 (module docstring)."""

    def __init__(
        self,
        directory: Path,
        *,
        threads: int = 1,
        beam: int = DEFAULT_BEAM,
        max_len: int = DEFAULT_MAX_LEN,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        """
        Raises:
            ArtifactMissing, ArtifactVersionMismatch: see `read_translator_meta`. ValueError: bad sizes.
        """
        if beam < 1 or max_len < 2 or cache_size < 0 or threads < 1:
            raise ValueError("beam and threads must be >= 1, max_len >= 2, cache_size >= 0")
        directory = Path(directory)
        meta = read_translator_meta(directory)
        import ctranslate2
        import sentencepiece as spm

        self.model_id: str = str(meta["model_id"])
        self.revision: str = str(meta["revision"])
        self._beam, self._max_len, self._cache_size = beam, max_len, cache_size
        self._tr = ctranslate2.Translator(
            str(directory), device="cpu", compute_type="int8", intra_threads=threads, inter_threads=1
        )
        self._src = spm.SentencePieceProcessor(model_file=str(directory / SOURCE_SPM))
        self._tgt = spm.SentencePieceProcessor(model_file=str(directory / TARGET_SPM))
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def translate(self, texts: Sequence[str]) -> list[str]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> str:
        with self._lock:
            hit = self._cache.get(text)
            if hit is not None:
                self._cache.move_to_end(text)
                return hit
        tokens = self._src.encode(text, out_type=str)[: self._max_len - 1] + ["</s>"]
        result = self._tr.translate_batch(
            [tokens], beam_size=self._beam, max_decoding_length=self._max_len, max_batch_size=1
        )
        out = str(self._tgt.decode(result[0].hypotheses[0])).strip()
        if self._cache_size:
            with self._lock:
                self._cache[text] = out
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return out
