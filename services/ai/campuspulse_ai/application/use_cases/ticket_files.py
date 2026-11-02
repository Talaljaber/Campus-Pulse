"""Files on tickets (P9.10): upload with a server-side type check, and short-lived signed links.

Rules (docs/plan/p9/PLAN.md (h) P9.10, brainstorm section 16):

- allowed: PNG, JPEG, WEBP, PDF, Word/Excel/PowerPoint (OOXML) and plain UTF-8 text, decided by the
  bytes (`sniff`), never by the filename; a filename or content type that claims another type than the
  bytes show is refused too (a renamed `.exe` or `.html` as `.png` is a 422);
- caps: 5 MB per file, 5 files and 15 MB per ticket;
- the storage path is `tickets/<ticket_id>/<uuid4>.<ext>`: the original filename is used for the claim
  check only and is stored nowhere;
- who may use a file: the requester (public files only), staff of the ticket's office, an admin; a
  caller who owns the request is always the requester (as in the lifecycle);
- links last 60 seconds, are signed server-side and are the only way to open a file; files that are not
  an image or a PDF are served as a download, never rendered;
- the model never reads a file; there is no virus scan (out of scope for the demo).

Errors: `InvalidInput` 422, `Unauthorized` 403, `NotFound` 404, `StoreError` 503.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass

from campuspulse_ai.application.use_cases.file_ports import BlobStore, FileStore
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.ports import ROLE_ADMIN, ROLE_STAFF, USER_ROLES, Actor
from campuspulse_ai.domain.errors import InvalidInput, NotFound, Unauthorized
from campuspulse_ai.domain.journey import MAX_FILE_BYTES, TicketFile, Visibility
from campuspulse_ai.domain.ports import Clock, Repository
from campuspulse_ai.domain.values import TicketStatus

MAX_FILES_PER_TICKET = 5
MAX_BYTES_PER_TICKET = 15 * 1024 * 1024
LINK_EXPIRES_S = 60

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ALLOWED_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": DOCX,
    "xlsx": XLSX,
    "pptx": PPTX,
    "txt": "text/plain",
}
INLINE_EXT = frozenset({"png", "jpg", "webp", "pdf"})
"""The only types a browser may show in a tab; everything else is a download."""
_EXT_ALIASES = {"jpeg": "jpg", "text": "txt"}
_OOXML_DIRS = (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx"))


def sniff(data: bytes) -> tuple[str, str] | None:
    """`(mime, ext)` of the bytes, or None when they are not an allowed type."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ALLOWED_MIME["png"], "png"
    if data.startswith(b"\xff\xd8\xff"):
        return ALLOWED_MIME["jpg"], "jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ALLOWED_MIME["webp"], "webp"
    if data.startswith(b"%PDF-"):
        return ALLOWED_MIME["pdf"], "pdf"
    if data.startswith(b"PK\x03\x04"):
        return _sniff_ooxml(data)
    if data and b"\x00" not in data:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return ALLOWED_MIME["txt"], "txt"
    return None


def _sniff_ooxml(data: bytes) -> tuple[str, str] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()  # only the directory is read, never the contents
    except (zipfile.BadZipFile, ValueError):
        return None
    if "[Content_Types].xml" not in names:
        return None
    for prefix, ext in _OOXML_DIRS:
        if any(n.startswith(prefix) for n in names):
            return ALLOWED_MIME[ext], ext
    return None


def claimed_ext(filename: str | None) -> str | None:
    """The extension the uploader's filename claims (lower case, aliases folded), or None."""
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].strip().lower()
    return _EXT_ALIASES.get(ext, ext) or None


def storage_path(ticket_id: str, ext: str) -> str:
    """`tickets/<ticket_id>/<uuid4>.<ext>`; no part of it comes from the uploader."""
    return f"tickets/{ticket_id}/{uuid.uuid4()}.{ext}"


def _role(actor: Actor, request_alias: str, office: str) -> str:
    if actor.alias and actor.role in USER_ROLES and actor.alias == request_alias:
        return "requester"
    if actor.role == ROLE_ADMIN:
        return "admin"
    if actor.role == ROLE_STAFF and actor.office is not None and actor.office == office:
        return "office"
    raise Unauthorized(f"role {actor.role!r} of office {actor.office!r} may not use files of this ticket")


def validate_attachments(
    store: FileStore, ticket_id: str, actor: Actor, file_ids: Sequence[str], internal: bool
) -> list[str]:
    """The ids a comment may take: files of this ticket, uploaded by the caller, not yet on a comment,
    with the comment's visibility. `InvalidInput` otherwise."""
    ids = list(dict.fromkeys(file_ids))
    if len(ids) > MAX_FILES_PER_TICKET:
        raise InvalidInput(f"at most {MAX_FILES_PER_TICKET} files per message")
    wanted = Visibility.INTERNAL if internal else Visibility.PUBLIC
    for file_id in ids:
        f = store.get_file(file_id)
        if (
            f is None
            or f.ticket_id != ticket_id
            or f.uploader_alias != actor.alias
            or f.uploader_role != actor.role
            or f.activity_id is not None
            or f.visibility != wanted
        ):
            raise InvalidInput(f"file {file_id} cannot be attached to this message")
    return ids


@dataclass(frozen=True, slots=True)
class FileLink:
    url: str
    expires_in: int


class TicketFilesUseCase:
    def __init__(
        self, repo: Repository, files: FileStore, blobs: BlobStore, journey: JourneyStore, clock: Clock
    ) -> None:
        self._repo = repo
        self._files = files
        self._blobs = blobs
        self._journey = journey
        self._clock = clock

    def upload(
        self,
        ticket_id: str,
        actor: Actor,
        data: bytes,
        internal: bool = False,
        activity_id: str | None = None,
        claimed_name: str | None = None,
        claimed_mime: str | None = None,
    ) -> TicketFile:
        """Check the caller, the bytes and the caps, store the bytes, save the row."""
        ticket = self._repo.get_ticket(ticket_id)
        request = self._repo.get_request(ticket.request_id)
        role = _role(actor, request.alias, ticket.office)
        if ticket.status == TicketStatus.MERGED:
            raise InvalidInput("a merged ticket accepts no files")
        if role == "requester" and internal:
            raise Unauthorized("a requester can only add public files")
        if not data:
            raise InvalidInput("the file is empty")
        if len(data) > MAX_FILE_BYTES:
            raise InvalidInput(f"the file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
        found = sniff(data)
        if found is None:
            raise InvalidInput("this file type is not allowed (images, PDF, Office documents, plain text)")
        mime, ext = found
        claim = claimed_ext(claimed_name)
        if claim is not None and claim != ext:
            raise InvalidInput("the file does not match its name; it was refused")
        if claimed_mime and claimed_mime not in (mime, "application/octet-stream"):
            raise InvalidInput("the file does not match its declared type; it was refused")
        visibility = Visibility.INTERNAL if internal else Visibility.PUBLIC
        if activity_id is not None:
            self._check_activity(ticket_id, actor, activity_id, visibility)
        existing = self._files.files_for_ticket(ticket_id)
        if len(existing) >= MAX_FILES_PER_TICKET:
            raise InvalidInput(f"a ticket holds at most {MAX_FILES_PER_TICKET} files")
        if sum(f.size_bytes for f in existing) + len(data) > MAX_BYTES_PER_TICKET:
            raise InvalidInput(f"a ticket holds at most {MAX_BYTES_PER_TICKET // (1024 * 1024)} MB of files")
        path = storage_path(ticket_id, ext)
        self._blobs.put(path, data, mime)
        return self._files.add_file(
            TicketFile(
                ticket_id=ticket_id,
                uploader_alias=actor.alias,
                uploader_role=actor.role,
                visibility=visibility,
                activity_id=activity_id,
                storage_path=path,
                mime=mime,
                size_bytes=len(data),
                ext=ext,
                created_at=self._clock.now(),
            )
        )

    def link(self, file_id: str, actor: Actor) -> FileLink:
        """A 60-second signed link for a file the caller may read."""
        f = self._files.get_file(file_id)
        if f is None:
            raise NotFound(f"file {file_id} not found")
        ticket = self._repo.get_ticket(f.ticket_id)
        request = self._repo.get_request(ticket.request_id)
        role = _role(actor, request.alias, ticket.office)
        if role == "requester" and f.visibility == Visibility.INTERNAL:
            raise Unauthorized("this file is for staff only")
        download = None if f.ext in INLINE_EXT else f"{f.id}.{f.ext}"
        return FileLink(self._blobs.sign(f.storage_path, LINK_EXPIRES_S, download), LINK_EXPIRES_S)

    def _check_activity(self, ticket_id: str, actor: Actor, activity_id: str, visibility: Visibility) -> None:
        for a in self._journey.activity_for(ticket_id):
            if a.id == activity_id:
                if a.actor_alias != actor.alias or a.visibility != visibility:
                    raise InvalidInput("the file does not fit that message")
                return
        raise InvalidInput(f"message {activity_id} not found on this ticket")
