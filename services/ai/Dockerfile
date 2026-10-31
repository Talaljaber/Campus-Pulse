# Build context is the REPO ROOT:  docker build -f services/ai/Dockerfile -t campuspulse-ai .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ORT_INTRA_OP_THREADS=1

WORKDIR /app

# Dependencies first so this layer caches across code changes.
COPY services/ai/requirements.txt services/ai/requirements-api.txt services/ai/
RUN pip install --no-cache-dir -r services/ai/requirements-api.txt

COPY services/ai services/ai
# TODO(P1/P4): also COPY config/, scripts/ and models/frozen/ once those directories exist.
RUN pip install --no-cache-dir --no-deps -e services/ai

# TODO(P4): encoder fetch. Stays disabled until the model releases (models-v1-rcN) exist.
# The repo is private until submission (UD-8), so the fetch needs GITHUB_TOKEN. It is passed as a
# BuildKit secret (never an ARG, which would leak into image history):
#   docker build --build-arg FETCH_MODELS=1 --build-arg MODELS_TAG=models-v1-rc1 --secret id=GITHUB_TOKEN,env=GITHUB_TOKEN ...
# On Render, set GITHUB_TOKEN as a service env var (verify at the first deploy that it reaches the build). scripts/fetch_models.py reads GITHUB_TOKEN when set.
ARG FETCH_MODELS=0
ARG MODELS_TAG=models-v1-rc1
RUN --mount=type=secret,id=GITHUB_TOKEN,env=GITHUB_TOKEN     if [ "$FETCH_MODELS" = "1" ]; then python scripts/fetch_models.py --tag "$MODELS_TAG"; fi

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

WORKDIR /app/services/ai
# One worker is mandatory: the SLA loop and the 512 MB budget depend on it. Shell form so $PORT expands.
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1
