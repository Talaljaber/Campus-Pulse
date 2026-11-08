"""In-memory `KnowledgeStore` (tests, offline runs). The passages live in the `VectorStore` (P10.19)."""

from __future__ import annotations

from campuspulse_ai.application.use_cases.knowledge_ports import KnowledgeDocument
from campuspulse_ai.domain.errors import StoreError


class InMemoryKnowledgeStore:
    def __init__(self) -> None:
        self._docs: dict[str, KnowledgeDocument] = {}

    def add(self, doc: KnowledgeDocument) -> None:
        if doc.id in self._docs:
            raise StoreError(f"knowledge document {doc.id} already exists")
        self._docs[doc.id] = doc

    def get(self, doc_id: str) -> KnowledgeDocument | None:
        return self._docs.get(doc_id)

    def list_all(self) -> list[KnowledgeDocument]:
        return sorted(self._docs.values(), key=lambda d: (d.created_at, d.id), reverse=True)

    def delete(self, doc_id: str) -> bool:
        return self._docs.pop(doc_id, None) is not None
