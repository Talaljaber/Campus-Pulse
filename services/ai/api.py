"""ASGI entry point: ``uvicorn api:app`` (single worker, see Dockerfile).

The services are built at startup from the environment by ``composition.online.build_online``: the
real frozen model, Supabase, the sinks and the notifier chain. Startup fails (the process exits) if
the model artifacts or Supabase are missing, so a half-wired service never answers traffic.
"""

from campuspulse_ai.composition.online import build_online
from campuspulse_ai.frameworks.fastapi_app import create_app

app = create_app(build=build_online)
