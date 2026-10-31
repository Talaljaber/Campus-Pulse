"""OnnxEncoder, CachingEncoder and HashingEncoder (P1.6, ARCHITECTURE §3.17).

`train` needs torch + sentence-transformers; `artifacts` needs the exported/fetched encoder in
`models/frozen/<artifact_version>/encoder`.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml
from fixtures.fakes import HashingEncoder

from campuspulse_ai.adapters.models.encoder import ENCODER_META, CachingEncoder, OnnxEncoder
from campuspulse_ai.config.paths import CONFIG_DIR, MODELS_FROZEN, REPO_ROOT
from campuspulse_ai.domain.errors import ArtifactMissing
from campuspulse_ai.domain.ports import SentenceEncoder

TRAIN = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
ENCODER_DIR = MODELS_FROZEN / TRAIN["artifact_version"] / "encoder"
PARITY = REPO_ROOT / "services" / "ai" / "tests" / "fixtures" / "encoder_parity.txt"


def _need_encoder() -> None:
    if not (ENCODER_DIR / ENCODER_META).is_file():
        pytest.skip(f"no encoder in {ENCODER_DIR}: export it (P1.6) or run scripts/fetch_models.py")


@pytest.mark.train
def test_parity_with_fp32() -> None:
    _need_encoder()
    from sentence_transformers import SentenceTransformer

    meta = json.loads((ENCODER_DIR / ENCODER_META).read_text(encoding="utf-8"))
    sentences = [s for s in PARITY.read_text(encoding="utf-8").splitlines() if s.strip()]
    assert len(sentences) == 50
    st = SentenceTransformer(meta["model_id"], revision=meta["revision"], device="cpu")
    st.max_seq_length = meta["max_tokens"]
    ref = st.encode([meta["query_prefix"] + s for s in sentences], convert_to_numpy=True,
                    normalize_embeddings=True)
    got = OnnxEncoder(ENCODER_DIR).encode_array(sentences)
    cos = (ref * got).sum(axis=1)
    assert cos.min() >= TRAIN["encoder_export"]["min_cosine"], sentences[int(cos.argmin())]


@pytest.mark.artifacts
def test_shape_and_unit_norm() -> None:
    _need_encoder()
    enc = OnnxEncoder(ENCODER_DIR, intra_op_threads=1)
    assert isinstance(enc, SentenceEncoder)
    assert (enc.dim, enc.model_id) == (TRAIN["encoder"]["dim"], TRAIN["encoder"]["model_id"])
    assert enc.revision == TRAIN["encoder"]["revision"] and enc.query_prefix == "query: "
    vecs = enc.encode(["The campus Wi-Fi disconnects", "وين جدول الباصات", "mesh 3arif wein el bus"])
    arr = np.asarray(vecs)
    assert arr.shape == (3, 384)
    assert np.allclose(np.linalg.norm(arr, axis=1), 1.0, atol=1e-5)
    assert enc.encode([]) == []
    # translation pairs land closer than unrelated requests
    en, ar, other = enc.encode_array(["Where is the bus timetable?", "وين جدول الباصات؟",
                                      "My scholarship discount is missing"])
    assert float(en @ ar) > float(en @ other)


def test_missing_dir_raises_artifact_missing(tmp_path: Path) -> None:
    with pytest.raises(ArtifactMissing, match="fetch_models"):
        OnnxEncoder(tmp_path / "no_such_encoder")
    (tmp_path / "enc").mkdir()
    with pytest.raises(ArtifactMissing):
        OnnxEncoder(tmp_path / "enc")  # no encoder_meta.json
    if (ENCODER_DIR / ENCODER_META).is_file():  # meta present but the ONNX file missing
        shutil.copyfile(ENCODER_DIR / ENCODER_META, tmp_path / "enc" / ENCODER_META)
        with pytest.raises(ArtifactMissing, match="model_int8.onnx"):
            OnnxEncoder(tmp_path / "enc")


def test_hashing_encoder_deterministic() -> None:
    a, b = HashingEncoder(dim=384, seed=42), HashingEncoder(dim=384, seed=42)
    texts = ["the bus is late", "الباص متاخر", "", "???"]
    va, vb = a.encode(texts), b.encode(texts)
    assert va == vb
    assert isinstance(a, SentenceEncoder) and a.dim == 384
    for vec in va:
        assert len(vec) == 384 and math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-9)
    near, far = a.encode(["the bus is late today", "scholarship invoice missing"])
    assert np.dot(va[0], near) > np.dot(va[0], far)
    assert HashingEncoder(seed=7).encode(["the bus is late"]) != va[:1]


def test_caching_encoder_hits() -> None:
    inner = HashingEncoder(dim=32)
    calls: list[list[str]] = []
    original = inner.encode

    def spy(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return original(texts)

    inner.encode = spy  # type: ignore[method-assign]
    cache = CachingEncoder(inner)
    assert isinstance(cache, SentenceEncoder) and cache.dim == 32 and cache.model_id == inner.model_id
    first = cache.encode(["a b", "c d", "a b"])
    assert calls == [["a b", "c d"]] and (cache.misses, cache.hits) == (2, 1)
    second = cache.encode(["c d", "e f", "a b"])
    assert calls[-1] == ["e f"] and (cache.misses, cache.hits) == (3, 3) and len(cache) == 3
    assert first[0] == second[2] == original(["a b"])[0]
