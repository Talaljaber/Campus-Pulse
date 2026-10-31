# Appendix C — Frozen artifact shipping

> Part of the CampusPulse plan ([PLAN.md](../PLAN.md)). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md).

The brief chose **(a) committed small artifacts plus (b) a GitHub Release asset for the encoder**, with an HF model-repo mirror as backup. No LFS (§3.12).

**Layout.**
```
models/frozen/
├── CURRENT                                   "v1"
└── v1/
    ├── config.json                           FrozenConfig (train.py only)                 committed
    ├── MANIFEST.json                         sha256 of every file + fetch block            committed
    ├── m1/{category.joblib, priority.joblib}  TF-IDF + LR (≈ 3–8 MB)                       committed
    ├── m2/{lr_category.joblib, lr_priority.joblib}                                         committed
    ├── head/priority_head.joblib                                                           committed
    ├── conformal/quantiles.json                                                            committed
    ├── index/{train, injection_exemplars, safety_exemplars}/{embeddings.npy, items.jsonl}  committed (≈ 2–3 MB)
    ├── encoder/{model_int8.onnx, tokenizer.json, config.json, special_tokens_map.json}     FETCHED (.gitignore)
    └── m3/...                                (only if "m3" ∈ ensemble.members)            FETCHED (.gitignore)
```

**Size budget.**
- Committed: ≤ 25 MB total, every file < 50 MB. This is checked by `scripts/check_sizes.py` in CI and [P6.1](P6_ship.md#p6-1).
- Fetched tarball: ≤ 200 MB. That is e5-small int8 ≈ 118–125 MB plus the tokenizer ≈ 17 MB → tar.gz ≈ 110–130 MB (E).
- **M3 would push the fetch to ≈ 250 MB**. Raising the budget needs a lead decision ([LD-6](../PLAN.md#ld-6)).

**MANIFEST.json** (written by `artifacts/io.py::write_manifest`, P1):
```json
{
  "schema_version": 1, "artifact_version": "v1", "created_at": "2026-11-09T…+03:00",
  "files": [
    {"path": "config.json", "sha256": "…", "bytes": 2210, "tier": "committed"},
    {"path": "encoder/model_int8.onnx", "sha256": "…", "bytes": 123456789, "tier": "fetched"}
  ],
  "fetch": {
    "asset": "campuspulse-models-v1.tar.gz", "sha256": "…", "bytes": 120000000,
    "urls": ["https://github.com/<owner>/campuspulse/releases/download/models-v1/campuspulse-models-v1.tar.gz",
             "https://huggingface.co/<dev>/campuspulse-models/resolve/<commit>/campuspulse-models-v1.tar.gz"]
  },
  "runtime": {"python": "3.11", "scikit-learn": "1.9.1", "onnxruntime": "1.31.0", "numpy": "2.4.6", "tokenizers": "0.23.3"}
}
```

**`scripts/fetch_models.py` contract** (P1 owns it; [P6.2](P6_ship.md#p6-2) finalises the URLs):
- **Usage:** `python scripts/fetch_models.py [--version v1|CURRENT] [--source github|hf|file:<path>] [--force] [--verify]`.
- **Dependencies:** stdlib only (`urllib.request`, `hashlib`, `tarfile`), so it works straight after `pip install -r services/ai/requirements.txt`.
- **Flow:**
  1. download to `models/frozen/.cache/`;
  2. verify the tarball sha256;
  3. extract with `tarfile` `filter="data"`, which rejects absolute paths, `..` and links;
  4. verify every `tier: "fetched"` file against `MANIFEST.files`.
- **Idempotent:** if all fetched files already verify, it prints `up to date` and exits 0.
- **Exit codes:** 0 OK · 2 checksum mismatch (prints the expected and actual sha) · 3 network error (prints the manual download URL and the `--source file:` hint).

**How `predict.py` finds artifacts offline.**
1. `config/paths.py` resolves the repo root from `__file__`, not the CWD.
2. `--model-dir` defaults to `models/frozen/<CURRENT>`.
3. `build_offline` → `ArtifactStore.load_manifest` hashes **every** file, committed and fetched (≈ 0.3 s for 130 MB, E).
4. A missing encoder → exit 2: `encoder missing — run: python scripts/fetch_models.py`.
5. A mismatch → exit 2 naming the file.

No network call is ever made from this path. `socket` is monkeypatched in `test_predict_cli.py`, and `--network none` is used in [X6.1](P6_ship.md#exit-criteria).

**Release mechanics ([P6.2](P6_ship.md#p6-2)).**
- `scripts/package_models.py` builds a deterministic tarball (sorted entries, mtime 0, uid/gid 0), so re-packaging gives the same sha.
- `gh release create models-v1 …` publishes it.
- Pre-releases `models-v1-rcN` are published from P1 on: `models-v1-rc1` at [P1.19](P1_scored_core.md#p1-19) and `models-v1-rc2` at [P2.13](P2_data_rigor.md#p2-13), so CI and the P4 Render build can fetch the encoder ([LD-5](../PLAN.md#ld-5)). Each carries `SHA256SUMS`, verified against `MANIFEST.json`. The encoder bytes are fixed after the [P2.6](P2_data_rigor.md#p2-6) encoder decision; if they change, the sha check fails loudly and the next rc (or [P6.2](P6_ship.md#p6-2)) republishes.
- The repo must be **public** so judges, `fetch_models.py` and the Render build can download without a token ([OQ-7](../PLAN.md#oq-7)).

**Render image.** The Dockerfile (repo-root context):
1. copies the committed `models/frozen/v1`;
2. runs `python scripts/fetch_models.py --verify` at build time;
3. sets `ARTIFACT_DIR=/app/models/frozen`.

The running container therefore has byte-identical artifacts and needs no network for inference. `/health` reports `artifact` and the MANIFEST sha, so the hosted demo is traceable to the same `v1` as `predictions.csv`.
