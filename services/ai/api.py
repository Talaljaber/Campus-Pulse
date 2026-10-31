"""ASGI entry point: ``uvicorn api:app`` (single worker, see Dockerfile)."""

from campuspulse_ai.frameworks.fastapi_app import create_app

app = create_app()
