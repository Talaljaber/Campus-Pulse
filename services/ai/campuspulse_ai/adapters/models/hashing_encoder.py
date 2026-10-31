"""`HashingEncoder`: a deterministic, model-free `SentenceEncoder` (tests and `train.py --encoder hashing`).

Signed feature hashing of words and character 3-grams (blake2b, so every process agrees). Related texts get a
positive cosine, so kNN, OOD and memory logic behave sensibly without the ONNX model. It is never used by a
shipped model: a model directory trained with it has `encoder.runtime == "hashing"`, and `build_offline`
then requires an explicit `encoder_override`.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

_WORD = re.compile(r"\w+", re.UNICODE)
_NGRAM = 3


class HashingEncoder:
    """Deterministic `SentenceEncoder` for tests: signed feature hashing of words and char 3-grams.

    The same text gives the same unit vector in every process (blake2b, not Python's salted `hash`), and
    texts that share words or 3-grams have a positive cosine, so kNN, OOD and memory tests behave sensibly
    without a model. Empty or symbol-only text maps to the first basis vector.
    """

    def __init__(self, dim: int = 384, seed: int = 42) -> None:
        if dim < 2:
            raise ValueError("dim must be >= 2")
        self.dim = dim
        self.seed = seed
        self.model_id = f"hashing-{dim}-{seed}"

    def _features(self, text: str) -> list[str]:
        words = _WORD.findall(text.lower())
        grams = [f"#{w[i:i + _NGRAM]}" for w in words for i in range(max(len(w) - _NGRAM + 1, 1))]
        return words + grams

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for feat in self._features(text):
                digest = hashlib.blake2b(f"{self.seed}:{feat}".encode(), digest_size=8).digest()
                value = int.from_bytes(digest, "big")
                vec[value % self.dim] += 1.0 if (value >> 63) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec))
            if norm == 0.0:
                vec[0], norm = 1.0, 1.0
            out.append([v / norm for v in vec])
        return out
