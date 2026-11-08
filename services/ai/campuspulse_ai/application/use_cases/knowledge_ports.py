"""Ports of the admin knowledge base (P10.19, docs/plan/p10/P10.19_knowledge_base.md).

- `KnowledgeStore`: the document rows (`knowledge_documents`). Impls:
  `adapters/store/knowledge_inmemory.InMemoryKnowledgeStore` (tests, offline runs) and
  `adapters/store/knowledge_supabase.SupabaseKnowledgeStore` (service role). The passages are not here:
  they are the `knowledge` collection of the `VectorStore`.
- `PdfText`: the text layer of a PDF (`adapters/knowledge/pdf_text.PypdfText`); kept behind a port so the
  application layer stays stdlib + numpy (tests/test_architecture.py).
- `KnowledgeSearch`: what the chat needs (`KnowledgeUseCase.search`).

Errors: `StoreError` from the stores; `PdfText.extract` raises `InvalidInput` for an unreadable PDF.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """One uploaded document. Its text lives only in its passages; `office` is None for the whole campus."""

    id: str
    title: str
    filename: str | None
    office: str | None
    char_count: int
    chunk_count: int
    uploaded_by: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """One passage close to a question: the document it comes from, its text and the cosine similarity."""

    document_id: str
    title: str
    office: str | None
    text: str
    sim: float


@runtime_checkable
class KnowledgeStore(Protocol):
    def add(self, doc: KnowledgeDocument) -> None:
        """Insert the row with its given id."""
        ...

    def get(self, doc_id: str) -> KnowledgeDocument | None: ...

    def list_all(self) -> list[KnowledgeDocument]:
        """Every document, newest first (ties by id, descending)."""
        ...

    def delete(self, doc_id: str) -> bool:
        """Delete the row (its passages go by cascade in Postgres); False when there was none."""
        ...


@runtime_checkable
class PdfText(Protocol):
    def extract(self, data: bytes, max_pages: int) -> str:
        """The text of every page (pages joined by a blank line). `InvalidInput` for an unreadable,
        encrypted or longer than `max_pages` PDF."""
        ...


@runtime_checkable
class KnowledgeSearch(Protocol):
    def search(self, text: str, k: int = 3) -> Sequence[KnowledgeHit]:
        """The `k` closest passages at or above the similarity floor, best first."""
        ...
