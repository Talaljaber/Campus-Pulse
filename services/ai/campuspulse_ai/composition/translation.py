"""Translator wiring shared by `build_offline` (predict.py, API, evaluate.py) and `run_training` (D-019).

`make_translator(model_dir, cfg)` returns the `NoopTranslator` when `translate.enabled` is false, otherwise a
`Ct2Translator` over `<model_dir>/<cfg.dir>`. It never falls back silently: a missing directory or file
raises `ArtifactMissing` (with the fetch command), and a translator whose model id or revision differs from
the config raises `ArtifactVersionMismatch`. `wrap_encoder` puts the translator in front of the encoder only.
"""

from __future__ import annotations

from pathlib import Path

from campuspulse_ai.adapters.models.translating_encoder import TranslatingEncoder
from campuspulse_ai.adapters.models.translator import Ct2Translator, NoopTranslator
from campuspulse_ai.config.frozen import TranslateCfg
from campuspulse_ai.domain.errors import ArtifactVersionMismatch
from campuspulse_ai.domain.ports import SentenceEncoder, Translator

TRANSLATOR_THREADS = 1  # deterministic and small; the API runs one worker on Render's 0.5 CPU


def make_translator(model_dir: Path, cfg: TranslateCfg) -> Translator:
    """The configured translator (module docstring).

    Raises:
        ArtifactMissing: enabled, but the translator files are not under `model_dir`.
        ArtifactVersionMismatch: the files are another model or revision than `cfg`.
    """
    if not cfg.enabled:
        return NoopTranslator()
    translator = Ct2Translator(Path(model_dir) / cfg.dir, threads=TRANSLATOR_THREADS)
    if (translator.model_id, translator.revision) != (cfg.model, cfg.revision):
        raise ArtifactVersionMismatch(
            f"translator {translator.model_id}@{translator.revision} != config {cfg.model}@{cfg.revision}"
        )
    return translator


def wrap_encoder(encoder: SentenceEncoder, translator: Translator, cfg: TranslateCfg) -> SentenceEncoder:
    """`TranslatingEncoder` when translation is enabled, else the encoder itself."""
    if not cfg.enabled:
        return encoder
    return TranslatingEncoder(encoder, translator, cfg.min_arabic_ratio)
