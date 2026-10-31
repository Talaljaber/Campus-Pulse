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
| `AI_SERVICE_TOKEN` | local, Render, Netlify | yes | ai, web | same value on both; on Netlify scope it to Functions/runtime as well as Builds |
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
| `SLA_SCAN_MINUTES` | local, Render | no | ai | default `5` |
| `INCIDENT_WINDOW_MIN` | local, Render | no | ai | default `30` |
| `ARTIFACT_DIR` | local, Render | no | ai | default `models/frozen` |
| `ORT_INTRA_OP_THREADS` | Render (and Dockerfile) | no | ai | `1` on Render, `4` locally. Appendix D writes `ORT_INTRA_OP_THREADS`; the code field is `ORT_INTRA_OP_THREADS` |
| `CAMPUSPULSE_ROOT` | local | no | ai | optional repo-root override |
| `PORT` | Render (injected), local | no | uvicorn | default 10000 |
| `NEXT_PUBLIC_SUPABASE_URL` | local, Netlify | no | web | |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | local, Netlify | no (public by design) | web | SPEC's `SUPABASE_ANON_KEY`, renamed for Next.js |
| `AI_SERVICE_URL` | local, Netlify | no | web | the Render URL |
| `NEXT_PUBLIC_DEMO_LOGIN_HINT` | local, Netlify | no | web | optional hint line on `/login`; never the password |
| `PW_PYTHON`, `PW_API_PORT` (8765), `PW_SUPABASE_PORT` (54399), `E2E_PASSWORD` | dev machine, CI | no | Playwright e2e | test-only; see docs/ui/README.md |
| `NODE_VERSION` | Netlify | no | Netlify build | `22` (P0.8) |
| `SUPABASE_PROJECT_REF`, `SUPABASE_DB_PASSWORD` | dev machine | DB password: yes | supabase CLI | |
| `SUPABASE_TEST_URL` (and `_SERVICE_ROLE_KEY`) | dev machine | key: yes | DB tests | |
| `GITHUB_TOKEN` | Render (build), dev, GitHub Actions (automatic) | yes | `scripts/fetch_models.py` | needed while the repo is private (UD-8) |
| `HF_TOKEN` | dev machine | yes | model mirror upload | optional |
| `WHATSAPP_*`, `DEMO_PHONE_ALLOWLIST`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DEMO_CALENDAR_IDS` | nowhere yet | | | future work (S1); commented out in `.env.example` |

Not yet read by `Settings` (added by later tasks through the same test): `AUTH_MODE`, `TZ`, `REPORTS_DIR`, `REDTEAM_MAX_N`.

## Deploy

### AI service on Render (Docker + `render.yaml`)

The service is a Docker web service defined in the repo-root `render.yaml` (LD-4): `runtime: docker`, plan `starter` (0.5 CPU, 512 MB), `dockerfilePath: ./services/ai/Dockerfile`, `dockerContext: .` (repo root), `healthCheckPath: /health`, `autoDeployTrigger: commit` on `main`. The image is `python:3.11-slim`, installs `requirements-api.txt` only (no torch), runs as a non-root user and starts `uvicorn api:app --workers 1` on `$PORT`. One worker is mandatory (SLA loop, memory budget).

One-time setup (human): Render dashboard, New, Blueprint, pick the repo (grant Render access to the private repo), apply. Then fill every `sync: false` variable in the service Environment tab (values from the table above). Confirm plan Starter and the health check path `/health` in Settings.

Health check: `GET /health` returns `{"status":"ok","artifact":null,"rss_mb":<float>}` (`artifact` is the model manifest sha once models are loaded). `/v1/health` is an alias. `rss_mb` is the number to compare against the 512 MB limit.

The encoder fetch step in the Dockerfile is a disabled TODO (`FETCH_MODELS=0`) until the `models-v1-rcN` releases exist (P4). It will read `GITHUB_TOKEN` as a BuildKit secret.

### Local Docker run

```bash
docker build -f services/ai/Dockerfile -t campuspulse-ai .            # context = repo root
docker run --rm -e PORT=8000 -p 8000:8000 campuspulse-ai              # Git Bash / PowerShell
curl.exe -s localhost:8000/health
# Render-like limits (RAM budget check):
docker run --rm -m 512m --cpus 0.5 -e PORT=8000 -p 8000:8000 campuspulse-ai
```

Without Docker: `cd services/ai && ../../.venv/Scripts/python -m uvicorn api:app --port 8000`.

The local image is about 880 MB on disk (onnxruntime, scipy, scikit-learn, pandas); idle RSS was about 52 MB in P0.

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

- `scripts/clean_data.py` and `scripts/test_clean.py` are excluded from ruff (root `extend-exclude`). They are legacy, byte-stable data scripts, and only the P0.3c print guard may change them.
