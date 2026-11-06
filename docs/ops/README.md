# Ops guide (owner: Foundation stream)

Kept current at every Foundation task. Sections marked "TODO" are filled by later P0 tasks.

## Local Python setup

Requires Python 3.11 to 3.13 (`requires-python = ">=3.11,<3.14"`). Run everything from the repo root.

```bash
python -m venv .venv                     # .venv/ is gitignored
# Git Bash:    source .venv/Scripts/activate      (or call .venv/Scripts/python directly)
# PowerShell:  .venv\Scripts\Activate.ps1
python -m pip install -r services/ai/requirements-dev.txt -e services/ai
python -m pip check                      # must print: No broken requirements found.
```

### The four requirement sets (all in `services/ai/`, every line an exact `==` pin)

| File | Contents | Who installs it |
| --- | --- | --- |
| `requirements.txt` | Inference only: numpy, scipy, scikit-learn, joblib, pandas, onnxruntime, tokenizers, pyyaml, pydantic, pydantic-settings. No torch. | Everyone (pulled in by the others); `predict.py` runs from this alone (a clean machine, judges). |
| `requirements-api.txt` | `-r requirements.txt` + fastapi, uvicorn, httpx, supabase, psutil, python-multipart. | Render / Docker image; Backend and DB streams. |
| `requirements-dev.txt` | `-r requirements-api.txt` + pytest, pytest-asyncio, respx, ruff, mypy, types-PyYAML, nbformat, nbclient. | All streams (the default dev install above); CI. |
| `requirements-train.txt` | `-r requirements.txt` + torch (CPU index), sentence-transformers, transformers, safetensors, huggingface-hub, matplotlib, mapie, ipykernel. | ML stream only, on the dev machine. Never in Docker or CI's default job. |

Install the training set on top of the dev one, only if you are the ML stream:

```bash
python -m pip install -r services/ai/requirements-train.txt
```

Changing any `requirements*.txt` is a change request to the lead.

### Lint and test

```bash
ruff check .                                                    # root pyproject.toml holds the ruff config
pytest services/ai/tests/unit/test_requirements_pinned.py -q    # one file
pytest services/ai -q                                           # whole suite (testpaths and markers in services/ai/pyproject.toml)
```

Ruff bans `sklearn.model_selection` random splitters (`train_test_split`, `KFold`, `StratifiedKFold`, `ShuffleSplit`, `StratifiedShuffleSplit`); use `adapters.training.cv` (frozen `cv_fold`).

## Env vars

Source of truth: `.env.example` (repo root) and `services/ai/campuspulse_ai/config/settings.py`; `test_env_example.py` keeps them in sync. Copy `.env.example` to `.env` (gitignored) for local work. Empty values count as unset. "Secret" means: never committed, never in client code.

| Variable | Set in | Secret | Read by | Notes |
| --- | --- | --- | --- | --- |
| `OPENROUTER_API_KEY` | local, Render | yes | ai | $10 spending limit on the key |
| `OPENROUTER_TIER1_MODEL` | local, Render | no | ai | pinned model id |
| `OPENROUTER_TIER2_MODEL` | (unset) | no | ai | documented only; tier 2 is off (UD-3) |
| `ENABLE_LLM` | local, Render | no | ai | default `false`; Render blueprint sets `false` |
| `LLM_DAILY_BUDGET_USD` | local, Render | no | ai | default `5.0` |
| `LLM_TIMEOUT_S` | local, Render | no | ai | default `20` (seconds per OpenRouter call) |
| `LLM_MAX_RETRIES` | local, Render | no | ai | default `2` (5xx and timeouts only) |
| `LLM_RETRY_BACKOFF_S` | local, Render | no | ai | default `0.5` (linear backoff) |
| `LLM_CACHE_PATH` | local, Render | no | ai | default `.cache/llm.sqlite` (gitignored) |
| `SUPABASE_URL` | local, Render | no | ai | |
| `SUPABASE_SERVICE_ROLE_KEY` | local, Render | yes | ai | never on Netlify |
| `AI_SERVICE_TOKEN` | local, Render, Netlify | yes | ai, web | same value on both; on Netlify scope it to Functions/runtime as well as Builds. Unset on the AI service = every `/v1` route answers 401 (fail closed) |
| `AUTH_MODE` | local, Render | no | ai | default `supabase_jwt` (P4.12: the user token in `X-CP-User-JWT` is verified with Supabase Auth and the role/office/alias read from `profiles`; needs `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`). `trusted_headers` takes the caller from `X-CP-*` headers: tests and local dev only, never on Render. See [docs/api/README.md › Auth](../api/README.md#auth) |
| `AUTH_CACHE_S` | local, Render | no | ai | default `60`; seconds a verified user token (and its profile) is cached, so a revoked session works at most this long |
| `AUTH_TIMEOUT_S` | local, Render | no | ai | default `5`; per call to Supabase Auth and to `profiles` |
| `REPORTS_DIR` | local, Render (image) | no | ai | default `reports`; `/v1/metrics` reads `model_lab.json` from it (written by `evaluate.py`) |
| `BATCH_MAX_ROWS` | local, Render | no | ai | default `10000`; `/v1/batch` rejects a larger CSV with 422 |
| `BATCH_MAX_BYTES` | local, Render | no | ai | default `5000000`; `/v1/batch` rejects a larger upload with 422 |
| `REDTEAM_MAX_N` | local, Render | no | ai | default `200`; P4.11: `/v1/redteam/run` and the red-team CLI reject a larger `n` with 422 / exit 4 |
| `REDTEAM_SEED_CSV` | local, Render (image) | no | ai | default `data/clean/train_clean.csv` (relative to the repo root); the official training rows the red team perturbs. A path under `data/our_test` or `data/robustness` is refused (D-013). The file must be in the image for the online route |
| `GMAIL_SMTP_USER` | local, Render | no | ai | the campuspulse support Gmail address |
| `GMAIL_APP_PASSWORD` | local, Render | yes | ai | needs 2-Step Verification |
| `SMTP_HOST` | local, Render | no | ai | `smtp.gmail.com` |
| `SMTP_PORT` | local, Render | no | ai | `465` (implicit TLS). Verified 2026-10-31: the dev network times out on 587 and 25, 465 works (`smoke_email.py` → `SMTP OK port=465`). Render Free blocks SMTP; use Starter |
| `SMTP_TIMEOUT_S` | local, Render | no | ai | default `10` (seconds per SMTP connection) |
| `SMTP_MAX_RETRIES` | local, Render | no | ai | default `2`; 4xx replies, disconnects, timeouts and a blocked port only |
| `SMTP_BACKOFF_S` | local, Render | no | ai | default `1.0`; exponential (`backoff * 2**attempt`) |
| `SMTP_DAILY_CAP` | local, Render | no | ai | default `100` sends per Asia/Amman day (Gmail allows 500); counted in-process, reset on restart |
| `DEMO_EMAIL_ALLOWLIST` | local, Render | no | ai | comma-separated; empty rejects every recipient |
| `DEMO_STUDENT_INBOX` | local, Render | no | ai | P4.8: the allow-listed developer inbox that stands in for every student's email (booking confirmations); unset = no student emails |
| `DEMO_OFFICE_INBOX` | local, Render | no | ai | P4.8: the allow-listed developer inbox for safety and transport alerts; unset = alerts are not emailed (the ticket still carries them) |
| `LINEAR_API_KEY` | local, Render | yes | ai | |
| `LINEAR_WEBHOOK_SECRET` | local, Render | yes | ai | |
| `OUTBOUND_WEBHOOK_URL` | local, Render | no | ai | optional |
| `OUTBOUND_WEBHOOK_SECRET` | local, Render | yes | ai | optional |
| `ENABLE_SINKS` | local, Render | no | ai | default `true` |
| `SINK_RETRY_MAX` | local, Render | no | ai | default `3` attempts per sink call (retryable `SinkError` only) |
| `SINK_RETRY_BASE_S` | local, Render | no | ai | default `0.5`; exponential (`base * 2**(attempt-1)`) |
| `GAMING_MIN_REQUESTS` | local, Render | no | ai | default `5`; requests before an alias can be flagged `priority_gaming_suspected` |
| `GAMING_CLAIM_RATIO` | local, Render | no | ai | default `0.8`; share of requests that claim urgency |
| `GAMING_HIGH_RATIO_MAX` | local, Render | no | ai | default `0.2`; max share of those claims that were really high |
| `SLA_SCAN_MINUTES` | local, Render | no | ai | default `5`; P4.9: the SLA scanner in the API lifespan scans at startup and then every N minutes; `0` disables it |
| `INCIDENT_WINDOW_MIN` | local, Render | no | ai | default `30` |
| `ARTIFACT_DIR` | local, Render | no | ai | default `models/frozen` |
| `ORT_INTRA_OP_THREADS` | Render (and Dockerfile) | no | ai | `1` on Render, `4` locally. Appendix D writes `ORT_INTRA_OP_THREADS`; the code field is `ORT_INTRA_OP_THREADS` |
| `CAMPUSPULSE_ROOT` | local | no | ai | optional repo-root override |
| `PORT` | Render (injected), local | no | uvicorn | default 10000 |
| `NEXT_PUBLIC_SUPABASE_URL` | local, Netlify | no | web | |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | local, Netlify | no (public by design) | web | SPEC's `SUPABASE_ANON_KEY`, renamed for Next.js |
| `AI_SERVICE_URL` | local, Netlify | no | web | the Render URL |
| `CAMPUSPULSE_HF_REPO` | dev machine | no | `scripts/fetch_models.py --source hf` only | Hugging Face repo id for the model tarball; not part of `Settings` |
| `NEXT_PUBLIC_DEMO_LOGIN_HINT` | local, Netlify | no | web | optional hint line on `/login`; never the password |
| `PW_PYTHON`, `PW_API_PORT` (8765), `PW_SUPABASE_PORT` (54399), `E2E_PASSWORD` | dev machine, CI | no | Playwright e2e | test-only; see docs/ui/README.md |
| `NODE_VERSION` | Netlify | no | Netlify build | `22` (P0.8) |
| `SUPABASE_PROJECT_REF`, `SUPABASE_DB_PASSWORD` | dev machine | DB password: yes | supabase CLI | |
| `SUPABASE_TEST_URL` (and `_SERVICE_ROLE_KEY`) | dev machine | key: yes | DB tests | |
| `GITHUB_TOKEN` | Render (build), dev, GitHub Actions (automatic) | yes | `scripts/fetch_models.py` | needed while the repo is private (UD-8) |
| `HF_TOKEN` | dev machine | yes | model mirror upload | optional |
| `WHATSAPP_*`, `DEMO_PHONE_ALLOWLIST`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DEMO_CALENDAR_IDS` | nowhere yet | | | future work (S1); commented out in `.env.example` |

Not yet read by `Settings` (added by later tasks through the same test): `TZ`.

## Optional LLM Arabizi translation (P2.20, D-025)

Off by default. Set `LLM_ARABIZI_TRANSLATE=true` and `OPENROUTER_API_KEY` on the AI service to translate Arabizi requests into English with the pinned `LLM_ARABIZI_MODEL` before the encoder. Guards, language id, M1, priority floors and conformal read the original text. Responses are cached in `LLM_ARABIZI_CACHE_PATH` (SQLite, local to the instance; delete the file to refresh). A timeout (`LLM_ARABIZI_TIMEOUT_S`, 6 s), an HTTP error, a missing key or an implausible reply means no translation and the request goes through the offline path unchanged. Cost: about $0.00004 per uncached request (`LLM_DAILY_BUDGET_USD` caps it); added latency about 0.7 s p50 / 0.95 s p95 on a cache miss. `predict.py --use-llm` exits 3 without a key. The key never leaves the server.

## Deploy

### AI service on Render (Docker + `render.yaml`)

The service is a Docker web service defined in the repo-root `render.yaml` (LD-4): `runtime: docker`, plan `starter` (0.5 CPU, 512 MB), `dockerfilePath: ./services/ai/Dockerfile`, `dockerContext: .` (repo root), `healthCheckPath: /health`, `autoDeployTrigger: commit` on `main`. The image is `python:3.11-slim`, installs `requirements-api.txt` only (no torch), runs as a non-root user and starts `uvicorn api:app --workers 1` on `$PORT`. One worker is mandatory (SLA loop, memory budget).

One-time setup (human): Render dashboard, New, Blueprint, pick the repo (grant Render access to the private repo), apply. Then fill every `sync: false` variable in the service Environment tab (values from the table above). Confirm plan Starter and the health check path `/health` in Settings.

Health check: `GET /health` returns `{"status":"ok","artifact":"v1","sha":"<manifest sha>","rss_mb":<float>,"encoder_loaded":true,"sinks":["supabase","linear"],"llm_tiers":[],"vector_store":"pgvector"}`. `/v1/health` is an alias. `rss_mb` is the number to compare against the 512 MB limit (budget 400 MB, §3.17).

**What the image contains (Backend batch 7).** `services/ai`, `config/`, `reports/model_lab.json`, `data/clean/train_clean.csv` (red-team seeds) and `models/frozen/v1` with the encoder. `.dockerignore` admits nothing else of `data/` or `reports/`. `CAMPUSPULSE_ROOT=/app`, `TZ=Asia/Amman`, `ORT_INTRA_OP_THREADS=1` are set in the image. The app is `build_online` ([docs/api/README.md › build_online](../api/README.md#build-online)): it **refuses to start** without the model artifacts or without `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.

**Encoder in the image.** If `models/frozen/v1/encoder` exists in the build context (after `python scripts/fetch_models.py` locally) it is copied; otherwise (Render, CI: a clean checkout) the build downloads the GitHub Release asset `MODELS_TAG` (build arg, default `models-v1-rc1`). Both paths end with `fetch_models.py` verifying every file against `MANIFEST.json`, so a mismatch fails the build. While the repo is private the download needs `GITHUB_TOKEN` as a BuildKit secret: `docker build --secret id=gh_token,env=GITHUB_TOKEN ...` (on Render: a secret file named `gh_token`). **Open item for Foundation:** check that Render passes `GITHUB_TOKEN` to the Docker build as a secret, and give the CI `docker` job the secret (or make the release public at submission, UD-8).

### Local Docker run

```bash
python scripts/fetch_models.py                                         # once; else the build downloads it
docker build -f services/ai/Dockerfile -t campuspulse-ai .            # context = repo root
# Render-like limits (RAM budget check); .env must set AI_SERVICE_TOKEN and the Supabase keys:
docker run --rm -m 512m --cpus 0.5 -p 8000:10000 --env-file .env -e SLA_SCAN_MINUTES=0 campuspulse-ai
curl.exe -s localhost:8000/health
```

`--env-file` passes the `.env` lines as they are; it does not strip inline `# comments`, so for Docker use a copy of `.env` without them (uvicorn's `--env-file` and pydantic-settings strip them). Without Docker: `uvicorn api:app --app-dir services/ai --env-file .env --port 8000` from the repo root.

Measured 2026-10-31 (Backend batch 7, image 308 MB, `-m 512m --cpus 0.5`, live Supabase, Linear off): startup under a minute (model load on 0.5 CPU); 20 sequential `/v1/triage` p50 1538 ms, p95 1699 ms; RSS (`/health`, psutil) idle 428.5 MB, max 433.0 MB; cgroup usage (`docker stats`) 362 MiB. Over the 400 MB / 1.5 s budget of ARCHITECTURE §3.17, under the 512 MB limit: the §3.17 ladder is a lead/user decision.

### Web on Netlify

TODO (P0.8/P0.10).

## CI

Workflow: `.github/workflows/ci.yml`. No secrets are used or needed (Supabase-marked tests stay deselected).

**Triggers:** push and pull request to `main` and `stream/**`, plus manual `workflow_dispatch`. A newer run on the same ref cancels the older one (`concurrency`). The repo is private, so minutes are scarce: pip and pnpm-store caches, path filters, docker on `main` only. Playwright is not run in CI yet (browser download, needs a running server).

A `changes` job (`dorny/paths-filter`) gates the others: `python` and `data-gates` run on changes to `services/`, `scripts/`, `data/`, `config/`, `pyproject.toml` or the workflows; `api-contract` on those plus `apps/web/`, `docs/api/` or the lockfile; `web` on `apps/web/`, `services/ai/openapi.json`, the lockfile or the workflows. Skipped jobs show as "skipped", which branch protection accepts.

| Job | Checks | Reproduce locally (repo root, venv active) |
|---|---|---|
| `python (3.11)`, `python (3.13)` | ruff, `mypy --strict`, pytest without `train`, `artifacts`, `supabase` | `ruff check .`, `mypy --strict services/ai/campuspulse_ai`, `pytest services/ai/tests -q -m "not train and not artifacts and not supabase"` |
| `data-gates` (3.11) | `data/clean` regenerates byte-identically (LD-39), data audit, leakage gate | `python scripts/test_clean.py`, then `git diff --exit-code -- data/clean` (on Windows add `--ignore-cr-at-eol`, since pandas writes CRLF, then `git checkout -- data/clean`), `python scripts/test_data_audit.py`, `python scripts/check_leakage.py --official` |
| `api-contract` (3.11) | `docs/api/endpoints.md` is current, `services/ai/openapi.json` equals a fresh mock export, generated web types are current (only once `apps/web` has a `gen:types` script) | `python scripts/gen_api_docs.py --check`, `python -m campuspulse_ai.frameworks.export_openapi --mock --out .tmp/openapi.json` then `diff .tmp/openapi.json services/ai/openapi.json`, `cd apps/web && pnpm gen:types && git diff --exit-code -- apps/web` |
| `web` (Node 22) | typecheck, eslint, vitest, `next build` | `cd apps/web && pnpm install --frozen-lockfile && pnpm typecheck && pnpm lint && pnpm test --run && pnpm build` |
| `docker` (push to `main` only) | the AI image builds, not pushed | `docker build -f services/ai/Dockerfile .` |

Notes:
- Run pnpm from `apps/web`. The `packageManager` pin (`pnpm@10.17.0`, via corepack) lives in `apps/web/package.json` and the repo root has no `package.json`, so root-level `pnpm --filter web ...` uses whatever pnpm is installed.
- `pnpm test` is plain `vitest` (watch mode), so CI and scripts pass `--run`.
- Enable Actions for the private repo (Settings, Actions, General). To require the checks, add branch protection on `main` with `python (3.11)`, `python (3.13)`, `data-gates`, `api-contract` and `web`.
- Not covered yet: a Windows leg (CRLF, `utf-8-sig`, paths) and the P1.19 `artifacts` job. `ruff format --check` is not run because the repo has not adopted the formatter.

## Troubleshooting

TODO. Notes collected so far:

- Every `/v1` route answers 401 locally: `AI_SERVICE_TOKEN` is empty in `.env` (the service fails closed). Set it on both the AI service and the web app.
- The API exits at startup with `ArtifactMissing ... fetch_models.py`: the encoder is not installed; run `python scripts/fetch_models.py` (or `--from-file <tar.gz>`).

- `scripts/clean_data.py` and `scripts/test_clean.py` are excluded from ruff (root `extend-exclude`). They are legacy, byte-stable data scripts, and only the P0.3c print guard may change them.
