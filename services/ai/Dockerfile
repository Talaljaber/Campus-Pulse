# syntax=docker/dockerfile:1.10
# Build context is the REPO ROOT:  docker build -f services/ai/Dockerfile -t campuspulse-ai .
#
# The image runs the real API (composition/online.py build_online): the frozen model, config/, the
# model-lab report and the red-team seed rows are inside, so inference never needs the network.
#
# The encoder (models/frozen/v1/encoder, gitignored, ~70 MB int8 ONNX) gets in one of two ways:
#  - pre-fetched: `python scripts/fetch_models.py` (or `--from-file <tar.gz>`) on the build machine,
#    then `COPY models/frozen` copies it with the committed parts (local builds);
#  - fetched at build time: when it is absent (Render builds from a clean git checkout), the RUN
#    below downloads the GitHub Release asset MODELS_TAG. While the repo is private (UD-8) this needs
#    GITHUB_TOKEN as a BuildKit secret, never an ARG (it would leak into the image history):
#      docker build --secret id=GITHUB_TOKEN,env=GITHUB_TOKEN -f services/ai/Dockerfile -t campuspulse-ai .
# Either way fetch_models.py verifies every file against MANIFEST.json (sha256) and fails the build on
# any mismatch, so the image never holds a model different from the one the reports describe.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ORT_INTRA_OP_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    TZ=Asia/Amman \
    CAMPUSPULSE_ROOT=/app

WORKDIR /app

# Dependencies first so this layer caches across code changes.
COPY services/ai/requirements.txt services/ai/requirements-api.txt services/ai/
RUN pip install --no-cache-dir -r services/ai/requirements-api.txt

# Runtime data. .dockerignore lets in only these files of data/ and reports/ (never a holdout).
COPY config config
COPY data/clean/train_clean.csv data/clean/train_clean.csv
COPY reports/model_lab.json reports/model_lab.json
COPY scripts/fetch_models.py scripts/fetch_models.py
COPY models/frozen models/frozen

ARG MODELS_TAG=models-v1-rc1
RUN --mount=type=secret,id=GITHUB_TOKEN,env=GITHUB_TOKEN \
    python scripts/fetch_models.py --tag "$MODELS_TAG" && rm -rf models/frozen/.cache

COPY services/ai services/ai
RUN pip install --no-cache-dir --no-deps -e services/ai

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

WORKDIR /app/services/ai
# One worker is mandatory: the SLA loop and the 512 MB budget depend on it. Shell form so $PORT expands.
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1
