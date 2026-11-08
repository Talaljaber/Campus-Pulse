"""The admin knowledge base (P10.19): upload, list and delete documents the chat may quote.

Routes only: each authenticates (admin only); the type check, the caps, the admin check and the storage
are in `KnowledgeUseCase`. Without it wired (`ApiServices.knowledge`) every route answers 501.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from campuspulse_ai.application.dto import KnowledgeDeleteOut, KnowledgeDocOut, KnowledgeListOut
from campuspulse_ai.domain.journey import MAX_FILE_BYTES
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()
NOT_WIRED = "knowledge base"


def doc_out(doc: object) -> KnowledgeDocOut:
    """A `KnowledgeDocument` in the contract shape (same attribute names)."""
    return KnowledgeDocOut.model_validate(doc, from_attributes=True)


@router.api_route(**route_kwargs("admin_knowledge_upload"))
def admin_knowledge_upload(
    services: Services,
    caller: Annotated[Principal, Depends(authorize("admin_knowledge_upload"))],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    office: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form(max_length=200_000)] = None,
    file: Annotated[UploadFile | None, File(description="PDF, .txt or .md, 5 MB at most.")] = None,
) -> KnowledgeDocOut:
    """Add a document (a file or pasted text)."""
    if services.knowledge is None:
        raise not_wired(NOT_WIRED)
    data = file.file.read(MAX_FILE_BYTES + 1) if file is not None else None  # one byte over is enough
    doc = services.knowledge.upload(
        caller,
        title,
        office or None,
        text=text,
        data=data,
        filename=file.filename if file is not None else None,
    )
    return doc_out(doc)


@router.api_route(**route_kwargs("admin_knowledge_list"))
def admin_knowledge_list(
    services: Services,
    caller: Annotated[Principal, Depends(authorize("admin_knowledge_list"))],
) -> KnowledgeListOut:
    """Every document, newest first."""
    if services.knowledge is None:
        raise not_wired(NOT_WIRED)
    docs = services.knowledge.list_documents(caller)
    return KnowledgeListOut(documents=[doc_out(d) for d in docs])


@router.api_route(**route_kwargs("admin_knowledge_delete"))
def admin_knowledge_delete(
    doc_id: str,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("admin_knowledge_delete"))],
) -> KnowledgeDeleteOut:
    """Delete a document and its passages."""
    if services.knowledge is None:
        raise not_wired(NOT_WIRED)
    services.knowledge.delete(caller, doc_id)
    return KnowledgeDeleteOut(id=doc_id, deleted=True)
