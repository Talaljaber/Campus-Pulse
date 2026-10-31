"""ASGI entry point: ``uvicorn api:app`` (single worker, see Dockerfile).

The services are built at startup from the environment (``composition.api.build_api``).
"""

from campuspulse_ai.composition.api import build_api
from campuspulse_ai.frameworks.fastapi_app import create_app

app = create_app(build=build_api)
