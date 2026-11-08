"""KnowledgeUseCase: the admin knowledge base the chat can quote (P10.19).

An admin adds a document (a PDF, a .txt/.md file, or pasted text). Its text is extracted, normalised, split
into passages, embedded with the deployed e5 encoder (the raw ONNX one the FAQ uses: no translation, no LLM)
and stored as the `knowledge` collection of the `VectorStore`. The chat then searches it with the person's
last message and offers the closest passages to the model as CURRENT SOURCES (`ChatUseCase`).

Rules:
- admin only, checked here as well as by the route;
- the type comes from the bytes, never the filename: a `%PDF-` header is a PDF, otherwise the bytes must
  be UTF-8 text without NUL bytes (a leading BOM is dropped); a filename that claims another type (.docx,
  .html, a .pdf that is text) is refused;
- refused with `InvalidInput` (422): no title, both or neither of file and text, an empty file, more than
  5 MB, pasted text over 200,000 characters, an unknown type, an unreadable PDF, no text (a scanned PDF),
  more than `MAX_PASSAGES` passages;
- passages: about `CHUNK_CHARS` characters with `OVERLAP_CHARS` overlap, cut at paragraph, then sentence,
  then word boundaries;
- the document row is written first, then the passages in batches; when a write fails the passages and the
  row are deleted again, so no half-written document stays, and the error goes on (`StoreError`, 503);
- passage ids are `uuid5(document id, "chunk:<n>")`, so a delete knows them without a read.

`search(text, k)` returns the `k` closest passages with a similarity of at least `min_sim`
(`KNOWLEDGE_MIN_SIM`). Errors: `InvalidInput` 422, `Unauthorized` 403, `NotFound` 404, `StoreError` 503.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from collections.abc import Sequence
from typing import Final

from campuspulse_ai.application.use_cases.knowledge_ports import (
    KnowledgeDocument,
    KnowledgeHit,
    KnowledgeStore,
    PdfText,
)
from campuspulse_ai.application.use_cases.ports import ROLE_ADMIN, Actor
from campuspulse_ai.domain.errors import InvalidInput, NotFound, Unauthorized
from campuspulse_ai.domain.ports import Clock, SentenceEncoder, VectorStore
from campuspulse_ai.domain.values import Lang, MetaValue, VectorItem

log = logging.getLogger(__name__)

COLLECTION: Final = "knowledge"
OFFICES: Final = frozenset({"registrar", "it", "finance", "transport", "facilities", "academic"})
MAX_FILE_BYTES: Final = 5 * 1024 * 1024
MAX_TEXT_CHARS: Final = 200_000
MAX_TITLE_CHARS: Final = 200
MAX_FILENAME_CHARS: Final = 200
MAX_PDF_PAGES: Final = 500
CHUNK_CHARS: Final = 800
OVERLAP_CHARS: Final = 100
MAX_PASSAGES: Final = 300
EMBED_BATCH: Final = 32
WRITE_BATCH: Final = 50
QUERY_CHARS: Final = 1000
"""Only the start of a long question is embedded (e5 reads at most a few hundred tokens anyway)."""
DEFAULT_MIN_SIM: Final = 0.82
TEXT_EXTS: Final = frozenset({"txt", "md", "markdown", "text"})

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?؟۔])\s+")
_SPACES = re.compile(r"[^\S\n]+")
_MANY_BREAKS = re.compile(r"\n{3,}")
_ARABIC = re.compile("[؀-ۿ]")
_LATIN = re.compile("[A-Za-z]")


# ---------------------------------------------------------------- text


def normalise(text: str) -> str:
    """NFC, Unix line ends, no control characters, one space between words, at most one blank line
    between paragraphs, no spaces at line ends."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MANY_BREAKS.sub("\n\n", text).strip()


def _split_long(unit: str, size: int) -> list[str]:
    """Pieces of at most `size` characters, cut at the last space before the limit when there is one."""
    pieces: list[str] = []
    rest = unit.strip()
    while len(rest) > size:
        cut = rest.rfind(" ", 0, size + 1)
        cut = cut if cut > size // 2 else size
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def _units(text: str, size: int) -> list[str]:
    """Paragraphs of at most `size` characters; a longer paragraph is split into sentences, and a longer
    sentence at word boundaries."""
    units: list[str] = []
    for para in _PARAGRAPH.split(text):
        para = " ".join(para.split())
        if not para:
            continue
        if len(para) <= size:
            units.append(para)
            continue
        for sentence in _SENTENCE_END.split(para):
            units.extend(_split_long(sentence, size))
    return units


def _tail(text: str, size: int) -> str:
    """The last `size` characters or fewer, starting at a word."""
    if len(text) <= size:
        return text
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail


def chunk(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Passages of about `size` characters. Paragraphs and sentences are packed together while they fit;
    every passage after the first starts with the last `overlap` characters of the one before (at a word
    boundary), so a fact cut at a border is still whole in one of them. A passage is at most
    `size + overlap + 1` characters."""
    passages: list[str] = []
    current = ""
    for unit in _units(text, size):
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= size:
            current = f"{current}\n{unit}"
        else:
            passages.append(current)
            carry = _tail(current, overlap) if overlap > 0 else ""
            current = f"{carry}\n{unit}" if carry else unit
    if current:
        passages.append(current)
    return passages


def lang_of(text: str) -> Lang:
    """`ar` when the text has more Arabic letters than Latin ones, else `en` (a tag; search ignores it)."""
    return Lang.AR if len(_ARABIC.findall(text)) > len(_LATIN.findall(text)) else Lang.EN


def _claimed_ext(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[1].strip().lower() or None


def _display_name(filename: str | None) -> str | None:
    """The base name only (no directories), trimmed; None when nothing is left."""
    if not filename:
        return None
    name = re.split(r"[\\/]", filename)[-1].strip()
    return name[:MAX_FILENAME_CHARS] or None


def passage_id(doc_id: str, ord_: int) -> str:
    return str(uuid.uuid5(uuid.UUID(doc_id), f"chunk:{ord_}"))


# ---------------------------------------------------------------- use case


class KnowledgeUseCase:
    """See the module docstring. `pdf` None = PDF uploads are refused (no extractor installed)."""

    def __init__(
        self,
        documents: KnowledgeStore,
        vectors: VectorStore,
        encoder: SentenceEncoder,
        clock: Clock,
        *,
        pdf: PdfText | None = None,
        min_sim: float = DEFAULT_MIN_SIM,
    ) -> None:
        if not 0.0 < min_sim <= 1.0:
            raise ValueError(f"min_sim must be in (0, 1], got {min_sim}")
        self._documents = documents
        self._vectors = vectors
        self._encoder = encoder
        self._clock = clock
        self._pdf = pdf
        self.min_sim = min_sim

    # ------------------------------------------------------------ admin

    def upload(
        self,
        actor: Actor,
        title: str,
        office: str | None = None,
        *,
        text: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> KnowledgeDocument:
        """Add a document from pasted `text` or a file's `data` (exactly one of them)."""
        _admin(actor)
        title = " ".join(title.split())
        if not title:
            raise InvalidInput("the title is empty")
        if len(title) > MAX_TITLE_CHARS:
            raise InvalidInput(f"the title is longer than {MAX_TITLE_CHARS} characters")
        office = (office or "").strip() or None
        if office is not None and office not in OFFICES:
            raise InvalidInput(f"unknown office {office!r}")
        has_text = text is not None and text.strip() != ""
        if has_text == (data is not None):
            raise InvalidInput("send either a file or pasted text, not both and not neither")
        if text is not None and has_text:
            if len(text) > MAX_TEXT_CHARS:
                raise InvalidInput(f"the pasted text is longer than {MAX_TEXT_CHARS:,} characters")
            body, shown_name = normalise(text), None
        else:
            assert data is not None
            body, shown_name = normalise(self._file_text(data, filename)), _display_name(filename)
        if not body:
            raise InvalidInput("no text found (a scanned PDF has no text layer; paste the text instead)")
        passages = chunk(body)
        if len(passages) > MAX_PASSAGES:
            raise InvalidInput(
                f"the document is too long: it makes {len(passages)} passages, at most {MAX_PASSAGES} "
                f"(about {MAX_PASSAGES * (CHUNK_CHARS - OVERLAP_CHARS):,} characters); split it into parts"
            )
        vectors = self._embed(passages)
        doc = KnowledgeDocument(
            id=str(uuid.uuid4()),
            title=title,
            filename=shown_name,
            office=office,
            char_count=len(body),
            chunk_count=len(passages),
            uploaded_by=actor.alias,
            created_at=self._clock.now(),
        )
        self._store(doc, passages, vectors)
        return doc

    def list_documents(self, actor: Actor) -> list[KnowledgeDocument]:
        """Every document, newest first."""
        _admin(actor)
        return self._documents.list_all()

    def delete(self, actor: Actor, doc_id: str) -> None:
        """Delete the document and its passages. `NotFound` for an unknown (or malformed) id."""
        _admin(actor)
        if not _is_uuid(doc_id):
            raise NotFound(f"document {doc_id} not found")
        doc = self._documents.get(doc_id)
        if doc is None:
            raise NotFound(f"document {doc_id} not found")
        self._vectors.delete(COLLECTION, [passage_id(doc.id, i) for i in range(doc.chunk_count)])
        if not self._documents.delete(doc.id):
            raise NotFound(f"document {doc_id} not found")

    # ------------------------------------------------------------ chat

    def search(self, text: str, k: int = 3) -> list[KnowledgeHit]:
        """The `k` closest passages with a similarity of at least `min_sim`, best first."""
        text = " ".join(text.split())[:QUERY_CHARS]
        if not text or k <= 0:
            return []
        query = [float(x) for x in self._encoder.encode([text])[0]]
        hits = self._vectors.search(COLLECTION, query, k=k, min_sim=self.min_sim)
        return [
            KnowledgeHit(
                document_id=str(h.meta.get("document_id") or ""),
                title=str(h.meta.get("title") or ""),
                office=str(h.meta["office"]) if h.meta.get("office") else None,
                text=h.text,
                sim=h.sim,
            )
            for h in hits
            if h.meta.get("document_id")
        ]

    # ------------------------------------------------------------ helpers

    def _file_text(self, data: bytes, filename: str | None) -> str:
        if not data:
            raise InvalidInput("the file is empty")
        if len(data) > MAX_FILE_BYTES:
            raise InvalidInput(f"the file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
        claim = _claimed_ext(filename)
        if data.startswith(b"%PDF-"):
            if claim is not None and claim != "pdf":
                raise InvalidInput("the file does not match its name; it was refused")
            if self._pdf is None:
                raise InvalidInput("PDF files cannot be read here; paste the text instead")
            return self._pdf.extract(data, MAX_PDF_PAGES)
        if claim is not None and claim not in TEXT_EXTS:
            raise InvalidInput("this file type is not allowed (PDF, .txt or .md)")
        if b"\x00" in data:
            raise InvalidInput("this file type is not allowed (PDF, .txt or .md)")
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            raise InvalidInput("the file is not a PDF or UTF-8 text (PDF, .txt or .md)") from None
        return decoded.removeprefix("﻿")

    def _embed(self, passages: Sequence[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(passages), EMBED_BATCH):
            batch = list(passages[start : start + EMBED_BATCH])
            vectors.extend(tuple(float(x) for x in v) for v in self._encoder.encode(batch))
        return vectors

    def _store(
        self, doc: KnowledgeDocument, passages: Sequence[str], vectors: Sequence[tuple[float, ...]]
    ) -> None:
        """The row first, then the passages; on any failure both are removed again and the error goes on."""
        meta: dict[str, MetaValue] = {"document_id": doc.id, "title": doc.title, "office": doc.office}
        items = [
            VectorItem(
                id=passage_id(doc.id, i),
                embedding=vec,
                text=passage,
                lang=lang_of(passage),
                meta={**meta, "ord": float(i)},
            )
            for i, (passage, vec) in enumerate(zip(passages, vectors, strict=True))
        ]
        self._documents.add(doc)
        try:
            for start in range(0, len(items), WRITE_BATCH):
                self._vectors.upsert(COLLECTION, items[start : start + WRITE_BATCH])
        except Exception:
            self._undo(doc)
            raise

    def _undo(self, doc: KnowledgeDocument) -> None:
        """Best effort: the error that caused the undo is the one the caller must see."""
        try:
            # the cascade on the row removes them in Postgres too; this covers the local store
            self._vectors.delete(COLLECTION, [passage_id(doc.id, i) for i in range(doc.chunk_count)])
        except Exception:
            log.warning("knowledge: passages of %s not removed after a failed upload", doc.id, exc_info=True)
        try:
            self._documents.delete(doc.id)
        except Exception:
            log.error("knowledge: document %s left behind after a failed upload", doc.id, exc_info=True)


def _admin(actor: Actor) -> None:
    if actor.role != ROLE_ADMIN:
        raise Unauthorized("only an admin may manage the knowledge base")


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
