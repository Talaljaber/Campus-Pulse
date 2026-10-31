# Appendix A — Pinned dependency versions and licences

> Part of the CampusPulse plan ([PLAN.md](../PLAN.md)). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md).

**Rules.** Every version is the highest non-prerelease, non-yanked release uploaded on or before **2026-10-17** (two-week cutoff; checked 2026-10-31). One pin per package, `==`, no environment markers, so every machine resolves the same set. Python range is `>=3.11,<3.14`; Docker and the clean-machine check run 3.11, the developer machine runs 3.13. Therefore numpy and scipy are pinned to the newest lines that still ship wheels for cp311, cp312 and cp313 (win_amd64 and manylinux x86_64), not the newest overall (numpy 2.5.x and scipy 1.18.x need Python >=3.12). Data came from the PyPI JSON API and the npm registry, plus the wheel tags and `requires_python` fields. `src` = V means verified that way; VERIFY@P0 means re-check in Phase 0. Non-OSI or non-commercial licences are flagged in A3 and none ships. This appendix is the source for the README Disclosures section.

## Table A1 — Python

| package | version | released | licence | file | used by | src |
|---|---|---|---|---|---|---|
| numpy | 2.4.6 | 2026-05-18 | BSD-3-Clause | requirements.txt | all ML; cp311-313 wheels (2.5.x rejected, needs 3.12) | V |
| scipy | 1.17.1 | 2026-02-23 | BSD-3-Clause | requirements.txt | sparse TF-IDF, calibration; cp311-313 wheels (1.18.x rejected) | V |
| scikit-learn | 1.9.1 | 2026-09-10 | BSD-3-Clause | requirements.txt | M1 TF-IDF+LR, calibration | V |
| joblib | 1.6.0 | 2026-08-31 | BSD-3-Clause | requirements.txt | artifact load | V |
| pandas | 3.0.6 | 2026-09-17 | BSD-3-Clause | requirements.txt | dataset/eval IO | V |
| onnxruntime | 1.31.0 | 2026-10-09 | MIT | requirements.txt | M2/M3 encoder inference | V |
| tokenizers | 0.23.3 | 2026-10-09 | Apache-2.0 | requirements.txt | tokenise for ONNX (abi3 wheels) | V |
| pyyaml | 6.0.3 | 2025-09-25 | MIT | requirements.txt | config/taxonomy YAML | V |
| pydantic | 2.14.1 | 2026-10-11 | MIT | requirements.txt | schemas | V |
| pydantic-settings | 2.16.0 | 2026-10-14 | MIT | requirements.txt | env settings | V |
| fastapi | 0.143.3 | 2026-10-16 | MIT | requirements-api.txt | API | V |
| uvicorn | 0.54.0 | 2026-09-25 | BSD-3-Clause | requirements-api.txt | ASGI server (no `[standard]`: uvloop absent on Windows) | V |
| httpx | 0.28.1 | 2024-12-06 | BSD-3-Clause | requirements-api.txt | OpenRouter, Linear GraphQL | V |
| supabase (supabase-py) | 2.33.0 | 2026-10-15 | MIT | requirements-api.txt | DB/storage/pgvector | V |
| psutil | 7.2.2 | 2026-01-28 | BSD-3-Clause | requirements-api.txt | /health resource stats | V |
| python-multipart | 0.0.32 | 2026-06-04 | Apache-2.0 | requirements-api.txt | UploadFile for /v1/batch | V |
| smtplib (stdlib) | n/a, no package | n/a | PSF | none | Gmail SMTP email | V |
| google-api-python-client | 2.201.0 | 2026-09-30 | Apache-2.0 | requirements-google.txt | optional Calendar (cut-order #5) | V |
| google-auth | 2.62.0 | 2026-10-12 | Apache-2.0 | requirements-google.txt | optional service-account auth | V |
| torch | 2.14.1+cpu | 2026-09-30 | BSD-3-Clause (PyPI: Apache-2.0 AND LLVM-exception) | requirements-train.txt | M3 fine-tune, dev machine only | V |
| sentence-transformers | 6.1.0 | 2026-09-18 | Apache-2.0 | requirements-train.txt | M2 embeddings, fine-tune | V |
| transformers | 5.20.1 | 2026-10-16 | Apache-2.0 | requirements-train.txt | model loading/export | V |
| safetensors | 0.8.0 | 2026-06-09 | Apache-2.0 | requirements-train.txt | weights format | V |
| huggingface-hub | 2.2.0 | 2026-10-08 | Apache-2.0 | requirements-train.txt | model download (train only) | V |
| matplotlib | 3.11.2 | 2026-09-11 | PSF-style (matplotlib licence) | requirements-train.txt | reports/figures | V |
| mapie | 1.5.0 | 2026-08-05 | BSD-3-Clause | requirements-train.txt | conformal cross-check in notebook 03 only | V |
| ipykernel | 7.4.0 | 2026-09-29 | BSD-3-Clause | requirements-train.txt | kernel for `scripts/run_notebooks.py` (nbclient) | V |
| pytest | 9.1.1 | 2026-06-19 | MIT | requirements-dev.txt | tests | V |
| pytest-asyncio | 1.4.0 | 2026-05-26 | Apache-2.0 | requirements-dev.txt | async API tests (drop if unused) | V |
| respx | 0.23.1 | 2026-04-08 | BSD-3-Clause | requirements-dev.txt | mock httpx | V |
| ruff | 0.17.1 | 2026-10-15 | MIT | requirements-dev.txt | lint/format | V |
| mypy | 2.4.0 | 2026-10-01 | MIT | requirements-dev.txt | type check `domain/`, `application/`, `config/` in CI ([P0.9](P0_foundations.md#p0-9)) | V |
| types-PyYAML | 6.0.12.20260906 | 2026-09-06 | Apache-2.0 | requirements-dev.txt | stubs for mypy | V |
| nbformat | 5.11.1 | 2026-08-17 | BSD-3-Clause | requirements-dev.txt | notebook checks | V |
| nbclient | 0.11.0 | 2026-06-05 | BSD-3-Clause | requirements-dev.txt | execute notebooks | V |
| jupyter | 1.1.1 | 2024-08-30 | BSD | (optional, not pinned in file) | interactive notebooks | V |

Model weights (multilingual-e5-small MIT, paraphrase-multilingual-MiniLM-L12-v2 Apache-2.0) are listed in the models appendix, not here.

## Table A2 — JavaScript (apps/web)

| package | version | released | licence | dev? | used by |
|---|---|---|---|---|---|
| next | 16.4.2 | 2026-10-15 | MIT | no | app framework (lead decision: Next 16; eslint-config-next 15.5.28 is the pairing only if a logged Next 15 fallback is ever needed) |
| react, react-dom | 19.3.1 | 2026-10-14 | MIT | no | UI |
| @supabase/supabase-js | 2.118.0 | 2026-10-15 | MIT | no | client; needs Node >=22 |
| @supabase/ssr | 0.12.7 | 2026-09-08 | MIT | no | cookie auth in Next |
| server-only | 0.0.1 | 2022-09-03 | MIT | no | guard server modules (latest, stable) |
| tailwindcss, @tailwindcss/postcss | 4.3.3 | 2026-07-16 | MIT | yes | styling, RTL logical utilities |
| typescript | 5.9.3 | 2025-09-30 | Apache-2.0 | yes | highest 5.x; supported by Next 16 |
| openapi-typescript | 7.13.0 | 2026-02-11 | MIT | yes | API types from FastAPI OpenAPI |
| eslint | 10.13.0 | 2026-10-16 | MIT | yes | lint |
| eslint-config-next | 16.4.2 | 2026-10-15 | MIT | yes | matches next |
| vitest | 4.1.12 | 2026-10-15 | MIT | yes | unit tests (5.0.5 rejected, 2 days old at cutoff) |
| @testing-library/react | 16.3.3 | 2026-08-27 | MIT | yes | component tests |
| jsdom | 29.1.1 | 2026-04-30 | MIT | yes | vitest DOM (30.x needs Node ^22.22.2, rejected) |
| @playwright/test | 1.64.1 | 2026-10-14 | Apache-2.0 | yes | e2e |
| supabase (CLI) | 2.121.0 | 2026-10-14 | MIT | yes | migrations/local stack |

Assets (not npm dependencies):

| asset | how loaded | licence |
|---|---|---|
| IBM Plex Sans Arabic | `next/font/google` | SIL OFL 1.1 |
| Inter | `next/font/google` | SIL OFL 1.1 |

Supabase CLI: [P0.10](P0_foundations.md#p0-10) runs it as `npx supabase@2.121.0` before `apps/web` exists; afterwards use the devDependency.

Peer note: @testing-library/react 16 also needs `@testing-library/dom` and `@types/react`; add them at P0 with `npm install` and record the resolved versions (VERIFY@P0).

## Table A3 — Rejected / flagged

| package | why |
|---|---|
| react-leaflet 5.0.0 | Hippocratic-2.1 licence, not OSI-open. Campus map is hand-built inline SVG instead |
| leaflet, maplibre-gl | not needed (no tiles, no network) |
| next-intl | not needed; brief says in-repo dictionaries |
| typescript 7.0.2 | brand-new native major (2026-07-08), toolchain risk; 5.9.3 pinned (6.0.3 also available) |
| vitest 5.0.5 | released 2 days before cutoff, new major |
| numpy 2.5.4, scipy 1.18.1 | require Python >=3.12, conflict with the 3.11 Docker/clean-machine target |
| torch, huggingface-hub, sentence-transformers at inference | not in requirements.txt; inference uses ONNX + tokenizers |
| lightgbm, rapidfuzz, apscheduler, faster-whisper, crepes | not needed by the binding scope |
| optimum 2.3.0 | not needed: the encoder export uses `torch.onnx.export` + `onnxruntime.quantization.quantize_dynamic` ([LD-8](../PLAN.md#ld-8)); 2.x may also have split ONNX export into `optimum-onnx` |
| PyJWT | not needed |
| jina-reranker-v2 (CC-BY-NC-4.0), MARBERTv2 / AraBERT-twitter (no licence on HF) | model flags, not used |

## Ready-to-paste Python files

```text
# services/ai/requirements.txt  (predict / offline inference only)
numpy==2.4.6
scipy==1.17.1
scikit-learn==1.9.1
joblib==1.6.0
pandas==3.0.6
onnxruntime==1.31.0
tokenizers==0.23.3
pyyaml==6.0.3
pydantic==2.14.1
pydantic-settings==2.16.0
```

```text
# services/ai/requirements-api.txt
-r requirements.txt
fastapi==0.143.3
uvicorn==0.54.0
httpx==0.28.1
supabase==2.33.0
psutil==7.2.2
python-multipart==0.0.32
```

```text
# services/ai/requirements-google.txt  (optional stretch, cut-order #5; not installed by default)
-r requirements-api.txt
google-api-python-client==2.201.0
google-auth==2.62.0
```

```text
# services/ai/requirements-train.txt  (dev machine only)
-r requirements.txt
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.14.1+cpu
sentence-transformers==6.1.0
transformers==5.20.1
safetensors==0.8.0
huggingface-hub==2.2.0
matplotlib==3.11.2
mapie==1.5.0
ipykernel==7.4.0
```

```text
# services/ai/requirements-dev.txt
-r requirements-api.txt
pytest==9.1.1
pytest-asyncio==1.4.0
respx==0.23.1
ruff==0.17.1
mypy==2.4.0
types-PyYAML==6.0.12.20260906
nbformat==5.11.1
nbclient==0.11.0
```

## package.json fragment (apps/web)

```json
{
  "engines": { "node": ">=22" },
  "dependencies": {
    "next": "16.4.2",
    "react": "19.3.1",
    "react-dom": "19.3.1",
    "@supabase/supabase-js": "2.118.0",
    "@supabase/ssr": "0.12.7",
    "server-only": "0.0.1"
  },
  "devDependencies": {
    "typescript": "5.9.3",
    "tailwindcss": "4.3.3",
    "@tailwindcss/postcss": "4.3.3",
    "openapi-typescript": "7.13.0",
    "eslint": "10.13.0",
    "eslint-config-next": "16.4.2",
    "vitest": "4.1.12",
    "@testing-library/react": "16.3.3",
    "jsdom": "29.1.1",
    "@playwright/test": "1.64.1",
    "supabase": "2.121.0"
  }
}
```

Commit `package-lock.json` and install with `npm ci`; set Netlify `NODE_VERSION=22`.

## Licence notes for README Disclosures

- No non-OSI, non-commercial or unlicensed package is shipped. react-leaflet (Hippocratic-2.1) and jina-reranker (CC-BY-NC) are explicitly excluded.
- Shipped Python and JS dependencies are MIT, BSD-3-Clause, Apache-2.0 or PSF (stdlib smtplib, matplotlib licence is PSF-style).
- onnxruntime is MIT and is the only inference runtime; tokenizers is Apache-2.0.
- torch (BSD-3) and transformers/sentence-transformers (Apache-2.0) are installed only on the training machine and are not in the Docker image.
- Fonts IBM Plex Sans Arabic and Inter are SIL OFL 1.1, served through next/font/google.
- Model weights and OpenRouter LLM use are disclosed in the models appendix (MIT / Apache-2.0 bases; derivatives state their base model).
