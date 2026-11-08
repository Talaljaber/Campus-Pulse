"""The admin knowledge base (P10.19): upload, list and delete documents the chat may quote.

Contract stubs: each route authenticates (admin only) and answers 501 until the knowledge use case is
wired (`ApiServices`); the backend stream of P10.19 replaces the bodies.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from campuspulse_ai.application.dto import KnowledgeDeleteOut, KnowledgeDocOut, KnowledgeListOut
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired

router = APIRouter()


@router.api_route(**route_kwargs("admin_knowledge_upload"))
def admin_knowledge_upload(
    caller: Annotated[Principal, Depends(authorize("admin_knowledge_upload"))],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    office: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form(max_length=200_000)] = None,
    file: Annotated[UploadFile | None, File(description="PDF, .txt or .md, 5 MB at most.")] = None,
) -> KnowledgeDocOut:
    """Add a document (a file or pasted text)."""
    raise not_wired("knowledge base")


@router.api_route(**route_kwargs("admin_knowledge_list"))
def admin_knowledge_list(
    caller: Annotated[Principal, Depends(authorize("admin_knowledge_list"))],
) -> KnowledgeListOut:
    """Every document, newest first."""
    raise not_wired("knowledge base")


@router.api_route(**route_kwargs("admin_knowledge_delete"))
def admin_knowledge_delete(
    doc_id: str,
    caller: Annotated[Principal, Depends(authorize("admin_knowledge_delete"))],
) -> KnowledgeDeleteOut:
    """Delete a document and its passages."""
    raise not_wired("knowledge base")
