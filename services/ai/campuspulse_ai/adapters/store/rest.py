"""The PostgREST client the online adapters use (P4.13 memory budget).

`SupabaseRepository`, `PgVectorStore` and `PgVectorMemoryStore` only call `table(name)` and
`rpc(fn, params)`, the PostgREST half of supabase-py. `PostgrestRest` builds just that client from the
`postgrest` package (a dependency of `supabase`), so the API process never imports the SDK's auth,
storage, realtime and functions modules (about 10 MB of RSS on the 512 MB Render instance). The
request URLs, headers and JSON are the ones `supabase.create_client(...).table/.rpc` send.

`RestApi` is the structural type of both, so tests and scripts may still pass a full supabase client.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from typing import Any, Protocol

REST_PATH = "/rest/v1"
SCHEMA = "public"


class RestApi(Protocol):
    """`table(name)` -> a PostgREST query builder; `rpc(fn, params)` -> an RPC request builder."""

    def table(self, table_name: str, /) -> Any: ...

    def rpc(self, fn: str, params: dict[Any, Any] | None = None, /) -> Any: ...


class PostgrestRest:
    """`RestApi` over `postgrest.SyncPostgrestClient`, authenticated with the service-role key.

    Raises `ValueError` for a URL that is not http(s). Query errors surface as the postgrest/httpx
    exceptions the adapters already turn into `StoreError` (`adapters/vectors/pgvector.store_call`).
    """

    def __init__(self, url: str, service_key: str, *, timeout_s: float) -> None:
        if not url.startswith(("https://", "http://")):
            raise ValueError("SUPABASE_URL must be an http(s) URL")
        from postgrest import SyncPostgrestClient  # online only

        headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        with warnings.catch_warnings():
            # postgrest marks `timeout` deprecated in favour of a custom http client; supabase-py
            # itself still passes it this way, which keeps the session (HTTP/2, headers) identical.
            warnings.simplefilter("ignore", DeprecationWarning)
            self._client = SyncPostgrestClient(
                f"{url.rstrip('/')}{REST_PATH}", schema=SCHEMA, headers=headers, timeout=timeout_s
            )

    def table(self, table_name: str, /) -> Any:
        return self._client.from_(table_name)

    def rpc(self, fn: str, params: Mapping[Any, Any] | None = None, /) -> Any:
        return self._client.rpc(fn, dict(params or {}))
