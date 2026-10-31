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

TODO (P0.5: `.env.example` and the full table).

## Deploy

TODO (Render, Netlify).

## CI

TODO (GitHub Actions jobs and what each checks).

## Troubleshooting

TODO. Notes collected so far:

- `scripts/clean_data.py` and `scripts/test_clean.py` are excluded from ruff (root `extend-exclude`). They are legacy, byte-stable data scripts, and only the P0.3c print guard may change them.
