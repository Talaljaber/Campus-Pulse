"""SupabaseBlobStore: the `BlobStore` port over the Supabase Storage REST API (service key). Online only.

The bucket `ticket-files` is private and has no client policies (migration 0015), so this adapter is
the only way in: upload with `POST /object/<bucket>/<path>` and link with
`POST /object/sign/<bucket>/<path>`. The service key goes in headers only and is never logged or put in
an error message. The `httpx.Client` is passed in by the composition root (this module does not import
httpx at run time).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from campuspulse_ai.domain.errors import StoreError

if TYPE_CHECKING:
    import httpx

BUCKET = "ticket-files"
STORAGE_PATH = "/storage/v1"


class SupabaseBlobStore:
    def __init__(self, base_url: str, service_key: str, http: httpx.Client, bucket: str = BUCKET) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("SUPABASE_URL must be an http(s) URL")
        self._root = f"{base_url.rstrip('/')}{STORAGE_PATH}"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._http = http
        self._bucket = bucket

    def _object(self, path: str) -> str:
        return f"{self._bucket}/{quote(path, safe='/')}"

    def put(self, path: str, data: bytes, mime: str) -> None:
        try:
            res = self._http.post(
                f"{self._root}/object/{self._object(path)}",
                content=data,
                headers={**self._headers, "Content-Type": mime, "x-upsert": "false"},
            )
        except Exception as exc:
            raise StoreError(f"storage upload failed: {type(exc).__name__}") from exc
        if res.status_code >= 400:
            raise StoreError(f"storage upload failed: HTTP {res.status_code}")

    def sign(self, path: str, expires_in: int, download_as: str | None = None) -> str:
        try:
            res = self._http.post(
                f"{self._root}/object/sign/{self._object(path)}",
                json={"expiresIn": expires_in},
                headers=self._headers,
            )
        except Exception as exc:
            raise StoreError(f"storage sign failed: {type(exc).__name__}") from exc
        if res.status_code >= 400:
            raise StoreError(f"storage sign failed: HTTP {res.status_code}")
        body: Any = res.json()
        signed = body.get("signedURL") if isinstance(body, dict) else None
        if not isinstance(signed, str) or not signed:
            raise StoreError("storage sign failed: no signed URL in the answer")
        url = f"{self._root}{signed if signed.startswith('/') else '/' + signed}"
        if download_as:
            url += f"&download={quote(download_as, safe='')}"
        return url
