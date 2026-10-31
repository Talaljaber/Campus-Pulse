"""Sentence encoders: `OnnxEncoder` (frozen int8 e5-small) and `CachingEncoder` (P1.6, §3.6/§3.17).

Inference never imports torch: `OnnxEncoder` runs the ONNX int8 export with `onnxruntime` and the
`tokenizers` fast tokenizer, then masked mean-pools and L2-normalizes in numpy. The export (and torch) live
only in `frameworks/cli/export_encoder.py`, on the training machine.

Encoder directory layout (`models/frozen/vN/encoder/`, fetched, never committed; Appendix C):

    model_int8.onnx      inputs input_ids, attention_mask (int64, [batch, seq]); output last_hidden_state
    tokenizer.json       the model's Hugging Face fast-tokenizer file, byte-identical to the pinned revision
    encoder_meta.json    model_id, revision, dim, max_tokens, query_prefix, pooling, normalize, file names,
                         pad_token_id, input/output names, quantization settings, sha256 of both files
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped, unused-ignore]
from numpy.typing import NDArray
from tokenizers import Tokenizer

from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.ports import SentenceEncoder

ENCODER_META = "encoder_meta.json"
META_SCHEMA_VERSION = 1
FETCH_HINT = "run `python scripts/fetch_models.py` (or export it with frameworks.cli.export_encoder)"
_REQUIRED_META = ("schema_version", "model_id", "revision", "dim", "max_tokens", "query_prefix", "pooling",
                  "normalize", "onnx_file", "tokenizer_file", "pad_token_id", "input_names", "output_name")
_NORM_FLOOR = 1e-12  # guards the L2 division for an all-zero vector (cannot occur for a real encoder)


def read_encoder_meta(encoder_dir: Path) -> dict[str, Any]:
    """Load and check `encoder_meta.json`.

    Raises:
        ArtifactMissing: the directory or the meta file is absent.
        ArtifactVersionMismatch: unreadable JSON, a missing key, an unknown schema version, or a pooling
            other than `mean`.
    """
    encoder_dir = Path(encoder_dir)
    path = encoder_dir / ENCODER_META
    if not encoder_dir.is_dir() or not path.is_file():
        raise ArtifactMissing(f"encoder missing: {path} not found; {FETCH_HINT}")
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactVersionMismatch(f"{path}: unreadable encoder meta: {exc}") from exc
    missing = [k for k in _REQUIRED_META if k not in meta]
    if missing:
        raise ArtifactVersionMismatch(f"{path}: missing keys {missing}")
    if meta["schema_version"] != META_SCHEMA_VERSION:
        found = meta["schema_version"]
        raise ArtifactVersionMismatch(f"{path}: schema_version {found!r} != {META_SCHEMA_VERSION}")
    if meta["pooling"] != "mean":
        raise ArtifactVersionMismatch(f"{path}: pooling {meta['pooling']!r} is not supported (mean only)")
    return dict(meta)


class OnnxEncoder:
    """Implements `domain.ports.SentenceEncoder` with the ONNX int8 export.

    `encode(texts)`: prefix each text with `query_prefix` (LD-9; callers never add it), tokenize with
    truncation to `max_tokens` (special tokens included), right-pad each batch of `batch_size` to its
    longest row, run ONNX Runtime on CPU, mean-pool the last hidden state over the attention mask, then
    L2-normalize (when the export says `normalize`). Returns `len(texts)` lists of `dim` floats, in input
    order; `[]` for no texts.

    `batch_size` defaults to the export's `encoder_meta.json` value (1). Dynamic int8 quantization scales
    activations per batch tensor, padding included, so in a padded batch a text's vector depends on its
    neighbours (cosine down to 0.993 in `reports/encoder_export.json`). With batch size 1 every text gets
    the same vector in `train.py`, `predict.py` and the API, at the same measured throughput.

    Raises:
        ArtifactMissing: the encoder directory, `encoder_meta.json`, the ONNX file or `tokenizer.json` is
            absent (message carries the fetch command).
        ArtifactVersionMismatch: a malformed meta file, or an ONNX graph whose inputs differ from the meta.
    """

    def __init__(
        self,
        encoder_dir: Path,
        *,
        query_prefix: str | None = None,
        max_tokens: int | None = None,
        intra_op_threads: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        """
        Args:
            encoder_dir: `models/frozen/vN/encoder`.
            query_prefix: overrides `encoder_meta.json` (`FrozenConfig.encoder.query_prefix`); None = meta.
            max_tokens: overrides the meta's truncation length (`FrozenConfig.encoder.max_tokens`).
            intra_op_threads: ONNX Runtime intra-op threads (`Settings.ort_intra_op_threads`; Render uses 1);
                None = the runtime default (all cores).
            batch_size: texts per ONNX call; None = the meta's `batch_size` (1 when absent).

        Raises:
            ArtifactMissing, ArtifactVersionMismatch: see the class docstring. ValueError: a size < 1.
        """
        encoder_dir = Path(encoder_dir)
        meta = read_encoder_meta(encoder_dir)
        onnx_path = encoder_dir / str(meta["onnx_file"])
        tokenizer_path = encoder_dir / str(meta["tokenizer_file"])
        for path in (onnx_path, tokenizer_path):
            if not path.is_file():
                raise ArtifactMissing(f"encoder missing: {path} not found; {FETCH_HINT}")
        batch_size = int(meta.get("batch_size", 1)) if batch_size is None else batch_size
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.model_id: str = str(meta["model_id"])
        self.revision: str = str(meta["revision"])
        self.dim: int = int(meta["dim"])
        self.query_prefix: str = str(meta["query_prefix"]) if query_prefix is None else query_prefix
        self.max_tokens: int = int(meta["max_tokens"]) if max_tokens is None else max_tokens
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self._normalize = bool(meta["normalize"])
        self._pad_id = int(meta["pad_token_id"])
        self._batch_size = batch_size
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.no_padding()
        self._tokenizer.enable_truncation(max_length=self.max_tokens)
        options = ort.SessionOptions()
        if intra_op_threads is not None:
            options.intra_op_num_threads = intra_op_threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.log_severity_level = 3
        self._session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
        graph_inputs = [i.name for i in self._session.get_inputs()]
        if sorted(graph_inputs) != sorted(meta["input_names"]):
            raise ArtifactVersionMismatch(f"{onnx_path}: inputs {graph_inputs} != meta {meta['input_names']}")
        self._input_names = tuple(graph_inputs)
        self._output_name = str(meta["output_name"])

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts (see the class docstring). Returns unit-norm float vectors of length `dim`."""
        return self.encode_array(texts).tolist()  # type: ignore[no-any-return]

    def encode_array(self, texts: Sequence[str]) -> NDArray[np.float32]:
        """Like `encode`, as a float32 array of shape (len(texts), dim)."""
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            out[start : start + len(batch)] = self._encode_batch(batch)
        return out

    def _encode_batch(self, texts: Sequence[str]) -> NDArray[np.float32]:
        encodings = self._tokenizer.encode_batch([self.query_prefix + t for t in texts])
        width = max(len(e.ids) for e in encodings)
        ids = np.full((len(texts), width), self._pad_id, dtype=np.int64)
        mask = np.zeros((len(texts), width), dtype=np.int64)
        for row, enc in enumerate(encodings):
            ids[row, : len(enc.ids)] = enc.ids
            mask[row, : len(enc.ids)] = 1
        feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        hidden = self._session.run([self._output_name], {k: feeds[k] for k in self._input_names})[0]
        weights = mask[:, :, None].astype(np.float32)
        pooled = (np.asarray(hidden, dtype=np.float32) * weights).sum(axis=1) / weights.sum(axis=1)
        if self._normalize:
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), _NORM_FLOOR)
        result: NDArray[np.float32] = pooled.astype(np.float32)
        return result


class CachingEncoder:
    """Implements `SentenceEncoder` by memoizing another encoder per exact text (train/CV only).

    Cross-validation re-embeds the same texts once per fold; the cache makes that one ONNX pass. Misses are
    embedded in one `inner.encode` call, in first-seen order. Per call, `misses` grows by the number of
    distinct new texts and `hits` by the rest of the input positions.
    """

    def __init__(self, inner: SentenceEncoder) -> None:
        self._inner = inner
        self.dim: int = inner.dim
        self.model_id: str = inner.model_id
        self._cache: dict[str, tuple[float, ...]] = {}
        self.hits = 0
        self.misses = 0

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        todo = list(dict.fromkeys(t for t in texts if t not in self._cache))
        self.misses += len(todo)
        self.hits += len(texts) - len(todo)
        if todo:
            for text, vec in zip(todo, self._inner.encode(todo), strict=True):
                self._cache[text] = tuple(vec)
        return [list(self._cache[t]) for t in texts]

    def __len__(self) -> int:
        return len(self._cache)
