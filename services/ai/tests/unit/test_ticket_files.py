"""P9.10 ticket files: the byte sniff, the caps, who may use a file, generated paths, 60-second links,
the email files line, the Supabase Storage adapter (mock transport) and the routes over HTTP.

Only tiny synthetic bytes; the blob store is an in-memory fake, nothing reaches a network.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fixtures.api import api_client, auth
from fixtures.containers import build_test
from fixtures.lifecycle import ALIAS, LifecycleHarness, build_lifecycle, seed_ticket

from campuspulse_ai.adapters.store.files_inmemory import InMemoryBlobStore, InMemoryFileStore
from campuspulse_ai.adapters.store.storage_supabase import SupabaseBlobStore
from campuspulse_ai.application.use_cases.ticket_files import (
    LINK_EXPIRES_S,
    MAX_BYTES_PER_TICKET,
    MAX_FILE_BYTES,
    TicketFilesUseCase,
    sniff,
)
from campuspulse_ai.domain.errors import InvalidInput, NotFound, StoreError, Unauthorized
from campuspulse_ai.domain.journey import Visibility
from campuspulse_ai.domain.values import TicketStatus

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
PDF = b"%PDF-1.4\n%sample\n"
TEXT = "Sample note, no real document. مثال".encode()
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00"
HTML = b"<html><script>alert(1)</script></html>"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def ooxml(folder: str, *, content_types: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if content_types:
            zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr(f"{folder}document.xml", "<x/>")
    return buf.getvalue()


@dataclass(frozen=True)
class Who:
    role: str
    office: str | None = None
    alias: str | None = None


STUDENT = Who("student", alias=ALIAS)
OTHER_STUDENT = Who("student", alias="demo-99")
REGISTRAR = Who("staff", "registrar", "staff-registrar")
IT = Who("staff", "it", "staff-it")
ADMIN = Who("admin", alias="admin")


@dataclass
class Rig:
    h: LifecycleHarness
    files: InMemoryFileStore
    blobs: InMemoryBlobStore
    use: TicketFilesUseCase
    ticket_id: str


@pytest.fixture
def rig() -> Rig:
    c = build_test()
    c.repo.add_profile(ALIAS, "student", display_name="Test Student")
    files, blobs = InMemoryFileStore(), InMemoryBlobStore()
    h = build_lifecycle(c, files=files)
    use = TicketFilesUseCase(c.repo, files, blobs, h.journey, c.clock)
    return Rig(h, files, blobs, use, seed_ticket(c).id)


# --------------------------------------------------------------------------- sniff


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PNG, ("image/png", "png")),
        (JPEG, ("image/jpeg", "jpg")),
        (WEBP, ("image/webp", "webp")),
        (PDF, ("application/pdf", "pdf")),
        (TEXT, ("text/plain", "txt")),
        (ooxml("word/"), (DOCX_MIME, "docx")),
        (ooxml("xl/"), (XLSX_MIME, "xlsx")),
        (ooxml("ppt/"), (PPTX_MIME, "pptx")),
        (HTML, ("text/plain", "txt")),  # valid text; only ever served as a download
        (b"", None),
        (EXE, None),
        (b"plain\x00with a NUL byte", None),
        (b"\xff\xfe not utf-8 \x80", None),
        (ooxml("word/", content_types=False), None),
        (ooxml("other/"), None),
        (b"PK\x03\x04 not really a zip", None),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", None),
    ],
)
def test_sniff_table(data: bytes, expected: tuple[str, str] | None) -> None:
    assert sniff(data) == expected


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("evidence.png", EXE),  # an executable renamed to .png
        ("evidence.png", HTML),  # html renamed to .png: text, not a PNG
        ("page.html", HTML),  # claims a type that is not allowed
        ("run.exe", PNG),
        ("photo.png", PDF),
        ("note.txt", b"text\x00nul"),
    ],
)
def test_renamed_or_disallowed_files_are_refused(rig: Rig, name: str, data: bytes) -> None:
    with pytest.raises(InvalidInput):
        rig.use.upload(rig.ticket_id, STUDENT, data, claimed_name=name)
    assert rig.files.files_for_ticket(rig.ticket_id) == [] and rig.blobs.blobs == {}


def test_a_matching_name_or_no_name_is_accepted(rig: Rig) -> None:
    for name in ("shot.PNG", "shot.png", None, "no-extension"):
        rig.use.upload(rig.ticket_id, STUDENT, PNG, claimed_name=name)
    with pytest.raises(InvalidInput):  # a declared content type that contradicts the bytes
        rig.use.upload(rig.ticket_id, STUDENT, PNG, claimed_mime="application/pdf")
    other = seed_ticket(rig.h.c)
    rig.use.upload(other.id, STUDENT, JPEG, claimed_name="a.jpeg", claimed_mime="application/octet-stream")


# --------------------------------------------------------------------------- caps


def test_per_file_cap(rig: Rig) -> None:
    ok = PNG + b"a" * (MAX_FILE_BYTES - len(PNG))
    assert len(ok) == MAX_FILE_BYTES
    rig.use.upload(rig.ticket_id, STUDENT, ok)
    with pytest.raises(InvalidInput, match="larger"):
        rig.use.upload(rig.ticket_id, STUDENT, ok + b"a")
    with pytest.raises(InvalidInput, match="empty"):
        rig.use.upload(rig.ticket_id, STUDENT, b"")


def test_count_cap(rig: Rig) -> None:
    for _ in range(5):
        rig.use.upload(rig.ticket_id, STUDENT, PNG)
    with pytest.raises(InvalidInput, match="at most 5 files"):
        rig.use.upload(rig.ticket_id, STUDENT, PNG)
    other = seed_ticket(rig.h.c)  # another ticket has its own budget
    rig.use.upload(other.id, STUDENT, PNG)


def test_total_cap(rig: Rig) -> None:
    big = PNG + b"a" * (MAX_FILE_BYTES - len(PNG))
    for _ in range(MAX_BYTES_PER_TICKET // MAX_FILE_BYTES):
        rig.use.upload(rig.ticket_id, STUDENT, big)
    with pytest.raises(InvalidInput, match="15 MB"):
        rig.use.upload(rig.ticket_id, STUDENT, PNG)


# --------------------------------------------------------------------------- paths


def test_storage_path_is_generated_and_never_uses_the_original_name(rig: Rig) -> None:
    f = rig.use.upload(rig.ticket_id, STUDENT, PNG, claimed_name="My Receipt (Private).png")
    assert re.fullmatch(rf"tickets/{rig.ticket_id}/[0-9a-f-]{{36}}\.png", f.storage_path)
    assert "receipt" not in f.storage_path.lower() and f.storage_path in rig.blobs.blobs
    assert not any("receipt" in str(v).lower() for v in vars(f).values())
    paths = {rig.use.upload(rig.ticket_id, STUDENT, PNG).storage_path for _ in range(3)}
    assert len(paths) == 3


# --------------------------------------------------------------------------- access matrix


def test_access_matrix(rig: Rig) -> None:
    pub = rig.use.upload(rig.ticket_id, STUDENT, PNG)
    internal = rig.use.upload(rig.ticket_id, REGISTRAR, PDF, internal=True)
    staff_public = rig.use.upload(rig.ticket_id, REGISTRAR, TEXT)
    assert (pub.visibility, internal.visibility) == (Visibility.PUBLIC, Visibility.INTERNAL)
    # requester: public files (their own and staff's), never the internal one
    for f in (pub, staff_public):
        assert rig.use.link(f.id, STUDENT).expires_in == LINK_EXPIRES_S
    with pytest.raises(Unauthorized, match="staff only"):
        rig.use.link(internal.id, STUDENT)
    # office staff and admin: everything
    for who in (REGISTRAR, ADMIN):
        for f in (pub, internal, staff_public):
            assert rig.use.link(f.id, who).url
    # other office, other student, anonymous: 403
    for who in (IT, OTHER_STUDENT, Who("student")):
        for f in (pub, internal):
            with pytest.raises(Unauthorized):
                rig.use.link(f.id, who)
    with pytest.raises(NotFound):
        rig.use.link("00000000-0000-4000-8000-000000000000", ADMIN)


def test_upload_rules_by_role(rig: Rig) -> None:
    with pytest.raises(Unauthorized, match="public"):
        rig.use.upload(rig.ticket_id, STUDENT, PNG, internal=True)
    for who in (IT, OTHER_STUDENT):
        with pytest.raises(Unauthorized):
            rig.use.upload(rig.ticket_id, who, PNG)
    rig.use.upload(rig.ticket_id, ADMIN, PNG, internal=True)
    merged = seed_ticket(rig.h.c, status=TicketStatus.MERGED)
    with pytest.raises(InvalidInput, match="merged"):
        rig.use.upload(merged.id, ADMIN, PNG)
    with pytest.raises(NotFound):
        rig.use.upload("00000000-0000-4000-8000-000000000000", ADMIN, PNG)


def test_links_expire_in_60_seconds_and_non_inline_types_download(rig: Rig) -> None:
    img = rig.use.upload(rig.ticket_id, STUDENT, PNG)
    doc = rig.use.upload(rig.ticket_id, STUDENT, ooxml("word/"), claimed_name="CV.docx")
    link = rig.use.link(img.id, REGISTRAR)
    assert link.expires_in == 60 and "expires_in=60" in link.url
    rig.use.link(doc.id, REGISTRAR)
    assert rig.blobs.signed == [
        (img.storage_path, 60, None),  # images and PDFs open in a tab
        (doc.storage_path, 60, f"{doc.id}.docx"),  # everything else downloads under a generated name
    ]


def test_activity_link_must_fit_the_caller_and_the_visibility(rig: Rig) -> None:
    rig.h.lifecycle.on_created(rig.ticket_id)
    reply = rig.h.lifecycle.comment(rig.ticket_id, REGISTRAR, "Please send a screenshot.").activity
    assert reply is not None
    with pytest.raises(InvalidInput):  # not the author
        rig.use.upload(rig.ticket_id, ADMIN, PNG, activity_id=reply.id)
    with pytest.raises(InvalidInput):  # internal file on a public message
        rig.use.upload(rig.ticket_id, REGISTRAR, PNG, internal=True, activity_id=reply.id)
    with pytest.raises(InvalidInput):
        rig.use.upload(rig.ticket_id, REGISTRAR, PNG, activity_id="nope")
    f = rig.use.upload(rig.ticket_id, REGISTRAR, PNG, activity_id=reply.id)
    assert f.activity_id == reply.id


# --------------------------------------------------------------------------- comments with files


def test_comment_with_files_attaches_them_and_counts_them_in_the_email(rig: Rig) -> None:
    a = rig.use.upload(rig.ticket_id, REGISTRAR, PNG)
    b = rig.use.upload(rig.ticket_id, REGISTRAR, PDF)
    change = rig.h.lifecycle.comment(rig.ticket_id, REGISTRAR, "See the attached.", file_ids=[a.id, b.id])
    assert change.activity is not None
    assert {f.activity_id for f in rig.files.files_for_ticket(rig.ticket_id)} == {change.activity.id}
    assert [e.ctx.files for e in change.emails] == [2]
    rig.h.lifecycle.deliver(change)
    [mail] = rig.h.mail.sent
    assert "2 file(s) attached; open them in the app." in mail.body
    assert "file(s) attached" in mail.html


def test_comment_without_files_has_no_files_line(rig: Rig) -> None:
    change = rig.h.lifecycle.comment(rig.ticket_id, REGISTRAR, "Hello.")
    rig.h.lifecycle.deliver(change)
    assert "file(s) attached" not in rig.h.mail.sent[0].body


def test_attachments_are_checked_before_anything_is_written(rig: Rig) -> None:
    theirs = rig.use.upload(rig.ticket_id, STUDENT, PNG)
    internal = rig.use.upload(rig.ticket_id, REGISTRAR, PNG, internal=True)
    other = seed_ticket(rig.h.c)
    elsewhere = rig.use.upload(other.id, REGISTRAR, PNG)
    before = len(rig.h.journey.activity_for(rig.ticket_id))
    for who, ids in (
        (REGISTRAR, [theirs.id]),  # someone else's file
        (REGISTRAR, [internal.id]),  # internal file on a public reply
        (REGISTRAR, [elsewhere.id]),  # a file of another ticket
        (REGISTRAR, ["missing"]),
        (STUDENT, [theirs.id, "missing"]),
    ):
        with pytest.raises(InvalidInput):
            rig.h.lifecycle.comment(rig.ticket_id, who, "x", False, file_ids=ids)
    assert len(rig.h.journey.activity_for(rig.ticket_id)) == before
    note = rig.h.lifecycle.comment(rig.ticket_id, REGISTRAR, "Note.", True, file_ids=[internal.id])
    saved = rig.files.get_file(internal.id)
    assert note.activity is not None and saved is not None and saved.activity_id == note.activity.id
    with pytest.raises(InvalidInput):  # already on a message
        rig.h.lifecycle.comment(rig.ticket_id, REGISTRAR, "again", True, file_ids=[internal.id])


# --------------------------------------------------------------------------- Supabase Storage adapter


def test_supabase_blob_store_calls_and_never_leaks_the_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "/object/sign/" in request.url.path:
            signed = "/object/sign/ticket-files/tickets/t/x.png?token=abc"
            return httpx.Response(200, json={"signedURL": signed})
        return httpx.Response(200, json={"Key": "ticket-files/tickets/t/x.png"})

    store = SupabaseBlobStore(
        "https://proj.supabase.test/", "service-key-123", httpx.Client(transport=httpx.MockTransport(handler))
    )
    store.put("tickets/t/x.png", PNG, "image/png")
    url = store.sign("tickets/t/x.png", 60)
    assert url == "https://proj.supabase.test/storage/v1/object/sign/ticket-files/tickets/t/x.png?token=abc"
    assert "service-key" not in url
    assert store.sign("tickets/t/x.png", 60, "abc.docx").endswith("&download=abc.docx")
    put, sign, _ = seen
    assert put.url.path == "/storage/v1/object/ticket-files/tickets/t/x.png"
    assert put.headers["x-upsert"] == "false" and put.headers["content-type"] == "image/png"
    assert json.loads(sign.content) == {"expiresIn": 60}
    assert sign.headers["authorization"] == "Bearer service-key-123"


def test_supabase_blob_store_errors_carry_no_secret() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "service-key-123 is bad"})

    store = SupabaseBlobStore(
        "https://proj.supabase.test", "service-key-123", httpx.Client(transport=httpx.MockTransport(refuse))
    )
    for call in (lambda: store.put("a/b.png", PNG, "image/png"), lambda: store.sign("a/b.png", 60)):
        with pytest.raises(StoreError) as err:
            call()
        assert "service-key" not in str(err.value) and "HTTP 400" in str(err.value)
    with pytest.raises(ValueError):
        SupabaseBlobStore("ftp://x", "k", httpx.Client())


# --------------------------------------------------------------------------- HTTP


def files_api(rig: Rig) -> Any:
    return api_client(rig.h.c, lifecycle=rig.h.lifecycle, files=rig.use)


def upload(client: Any, ticket_id: str, name: str, data: bytes, headers: dict[str, str], **form: str) -> Any:
    return client.post(
        f"/v1/tickets/{ticket_id}/files",
        files={"file": (name, data, "application/octet-stream")},
        data=form,
        headers=headers,
    )


def test_routes_upload_link_and_errors(rig: Rig) -> None:
    client = files_api(rig)
    student = auth("student", ALIAS)
    r = upload(client, rig.ticket_id, "Secret Name.png", PNG, student)
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"id", "ticket_id", "mime", "size_bytes", "ext", "visibility", "created_at"}
    assert (out["mime"], out["ext"], out["visibility"]) == ("image/png", "png", "public")
    assert out["size_bytes"] == len(PNG) and "Secret" not in r.text

    registrar = auth("staff", office="registrar")
    staff_only = upload(client, rig.ticket_id, "n.pdf", PDF, registrar, internal="true")
    assert staff_only.status_code == 200 and staff_only.json()["visibility"] == "internal"

    assert upload(client, rig.ticket_id, "x.png", EXE, student).status_code == 422
    assert upload(client, rig.ticket_id, "x.png", PNG, auth("staff", office="it")).status_code == 403
    assert upload(client, rig.ticket_id, "x.png", PNG, student, internal="true").status_code == 403
    assert client.post(f"/v1/tickets/{rig.ticket_id}/files", headers=student).status_code == 422  # no file

    link = client.get(f"/v1/files/{out['id']}/link", headers=student)
    assert link.status_code == 200 and link.json()["expires_in"] == 60
    hidden = staff_only.json()["id"]
    assert client.get(f"/v1/files/{hidden}/link", headers=student).status_code == 403
    assert client.get(f"/v1/files/{hidden}/link", headers=auth("admin")).status_code == 200
    assert client.get("/v1/files/nope/link", headers=auth("admin")).status_code == 404


def test_routes_refuse_a_file_over_the_cap_and_answer_501_when_not_wired(rig: Rig) -> None:
    big = PNG + b"a" * MAX_FILE_BYTES
    r = upload(files_api(rig), rig.ticket_id, "big.png", big, auth("student", ALIAS))
    assert r.status_code == 422 and "larger" in r.json()["error"]["message"]
    bare = api_client(rig.h.c)
    assert upload(bare, rig.ticket_id, "a.png", PNG, auth("student", ALIAS)).status_code == 501
    assert bare.get("/v1/files/x/link", headers=auth("admin")).status_code == 501


def test_comment_route_takes_file_ids(rig: Rig) -> None:
    client = files_api(rig)
    staff = auth("staff", office="registrar", alias="staff-registrar")
    f = upload(client, rig.ticket_id, "a.png", PNG, staff).json()
    body = {"body": "Here.", "file_ids": [f["id"]]}
    r = client.post(f"/v1/tickets/{rig.ticket_id}/comments", json=body, headers=staff)
    assert r.status_code == 200, r.text
    saved = rig.files.get_file(f["id"])
    assert saved is not None and saved.activity_id == r.json()["activity"]["id"]
    many = {"body": "x", "file_ids": ["a"] * 6}
    assert client.post(f"/v1/tickets/{rig.ticket_id}/comments", json=many, headers=staff).status_code == 422
