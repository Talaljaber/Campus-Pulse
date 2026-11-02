"""Ticket files (P9.10): `POST /v1/tickets/{ticket_id}/files` and `GET /v1/files/{file_id}/link`.

Routes only: the caller comes from `authorize`; the type check, the caps and the access rules are in
`TicketFilesUseCase`. The original filename is passed on for the claim check and never stored.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from campuspulse_ai.application.dto import FileLinkOut, FileOut
from campuspulse_ai.domain.journey import MAX_FILE_BYTES, TicketFile
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


def file_out(f: TicketFile) -> FileOut:
    return FileOut.model_validate(
        {
            "id": f.id,
            "ticket_id": f.ticket_id,
            "mime": f.mime,
            "size_bytes": f.size_bytes,
            "ext": f.ext,
            "visibility": f.visibility.value,
            "created_at": f.created_at,
        }
    )


@router.api_route(**route_kwargs("ticket_file_upload"))
def ticket_file_upload(
    ticket_id: str,
    file: Annotated[UploadFile, File(description="The file (5 MB at most).")],
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("ticket_file_upload"))],
    internal: Annotated[bool, Form()] = False,
    activity_id: Annotated[str | None, Form()] = None,
) -> FileOut:
    """Check the bytes, store them privately and record the row (see the use case for the rules)."""
    if services.files is None:
        raise not_wired("ticket files")
    data = file.file.read(MAX_FILE_BYTES + 1)  # one byte over the cap is enough to refuse it
    saved = services.files.upload(
        ticket_id,
        caller,
        data,
        internal=internal,
        activity_id=activity_id or None,
        claimed_name=file.filename,
        claimed_mime=file.content_type,
    )
    return file_out(saved)


@router.api_route(**route_kwargs("file_link"))
def file_link(
    file_id: str,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("file_link"))],
) -> FileLinkOut:
    """A signed link that works for 60 seconds, for a file the caller may read."""
    if services.files is None:
        raise not_wired("ticket files")
    link = services.files.link(file_id, caller)
    return FileLinkOut(url=link.url, expires_in=link.expires_in)
