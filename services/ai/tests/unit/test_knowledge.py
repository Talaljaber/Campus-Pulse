"""P10.19: the admin knowledge base (upload, list, delete, search), its chat grounding and its routes.

A keyword encoder stands in for e5 so similarities are exact and offline; the vector store is the local numpy
store (the same `knowledge` collection `PgVectorStore` serves online). Small PDFs are built in the test.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fixtures.api import api_client, auth
from fixtures.chat import Caller, ChatHarness, ScriptedAgent, build_chat, turn_of, user

from campuspulse_ai.adapters.knowledge.pdf_text import PypdfText
from campuspulse_ai.adapters.store.knowledge_inmemory import InMemoryKnowledgeStore
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.chat_ports import AgentReply
from campuspulse_ai.application.use_cases.knowledge import (
    COLLECTION,
    MAX_FILE_BYTES,
    MAX_PASSAGES,
    KnowledgeUseCase,
    chunk,
    normalise,
    passage_id,
)
from campuspulse_ai.application.use_cases.knowledge_ports import KnowledgeHit, KnowledgeSearch
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.domain.announcements import Announcement
from campuspulse_ai.domain.errors import InvalidInput, NotFound, StoreError, Unauthorized
from campuspulse_ai.domain.values import Lang, VectorItem

ADMIN = Caller(role="admin", alias="admin-1")
STUDENT = Caller(role="student", alias="stu-1")
STAFF = Caller(role="staff", alias="staff-it", office="it")
TOPICS = ("refund", "library", "password", "parking")
HANDBOOK = (
    "Tuition refunds\n\nA student who withdraws in the first week gets a full refund. No refund is given "
    "after the second week.\n\n"
    "Library hours\n\nThe library opens Sunday to Thursday from 8:00 to 20:00 and is closed on Friday."
)


class TopicEncoder:
    """One dimension per topic word, plus a small constant one: texts about the same topic have a cosine
    near 1, texts about different topics near 0."""

    dim = len(TOPICS) + 1
    model_id = "topic-test"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            low = text.lower()
            out.append([float(low.count(t)) for t in TOPICS] + [0.1])
        return out


@dataclass
class Clock:
    t: datetime = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


def make_pdf(*lines: str) -> bytes:
    """A one-page PDF with these lines in its text layer (no lines = a page without text, like a scan)."""
    ops = " ".join(f"({line}) Tj 0 -14 Td" for line in lines)
    content = f"BT /F1 12 Tf 72 720 Td {ops} ET".encode() if lines else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


@dataclass
class Rig:
    use: KnowledgeUseCase
    docs: InMemoryKnowledgeStore
    vectors: LocalNumpyVectorStore


def rig(*, pdf: bool = True, vectors: LocalNumpyVectorStore | None = None) -> Rig:
    docs = InMemoryKnowledgeStore()
    store = vectors or LocalNumpyVectorStore(TopicEncoder.dim, collections=(COLLECTION,))
    use = KnowledgeUseCase(
        docs, store, TopicEncoder(), Clock(), pdf=PypdfText() if pdf else None, min_sim=0.5
    )
    return Rig(use, docs, store)


# ---------------------------------------------------------------- text and passages


def test_normalise_collapses_spaces_and_blank_lines() -> None:
    raw = "Title\r\n\r\n\r\n  Line   one\t\x07here  \n\n\n\nLine two  "
    assert normalise(raw) == "Title\n\nLine one here\n\nLine two"


def test_chunk_packs_paragraphs_with_overlap_and_splits_long_ones() -> None:
    sentence = "The add drop period lasts one week and needs the advisor's approval. "
    text = "\n\n".join(["Short heading", sentence * 30, "Closing paragraph about refunds."])
    passages = chunk(text, size=800, overlap=100)
    assert len(passages) >= 3
    assert all(len(p) <= 800 + 100 + 1 for p in passages)
    assert passages[0].startswith("Short heading") and passages[-1].endswith("about refunds.")
    for before, after in zip(passages, passages[1:], strict=False):
        head = after.split("\n", 1)[0]
        assert before.endswith(head) and 0 < len(head) <= 100  # the overlap is the end of the one before
    assert chunk("") == [] and chunk("one line") == ["one line"]


# ---------------------------------------------------------------- upload


def test_upload_pasted_text_stores_the_row_and_its_passages() -> None:
    r = rig()
    doc = r.use.upload(ADMIN, "  Student   handbook ", "registrar", text=HANDBOOK)
    assert (doc.title, doc.office, doc.filename, doc.uploaded_by) == (
        "Student handbook",
        "registrar",
        None,
        "admin-1",
    )
    assert doc.char_count == len(normalise(HANDBOOK)) and doc.chunk_count == 1
    assert r.docs.list_all() == [doc]
    assert r.vectors.count(COLLECTION) == 1
    [hit] = r.vectors.search(COLLECTION, TopicEncoder().encode(["refund"])[0], k=5)
    assert hit.id == passage_id(doc.id, 0) and hit.meta["document_id"] == doc.id
    assert hit.meta["title"] == "Student handbook" and "full refund" in hit.text


def test_upload_txt_md_and_pdf_files() -> None:
    r = rig()
    txt = r.use.upload(ADMIN, "Refunds", data="﻿No refund after week two.".encode(), filename="r.txt")
    md = r.use.upload(ADMIN, "Library", data=b"# Library\n\nOpen until 20:00.", filename="dir/lib.md")
    pdf = r.use.upload(ADMIN, "Parking", data=make_pdf("Parking permits cost 20 JOD."), filename="p.pdf")
    assert (txt.filename, md.filename, pdf.filename) == ("r.txt", "lib.md", "p.pdf")
    assert txt.char_count == len("No refund after week two.")
    hits = r.use.search("how much is a parking permit?")
    assert [h.document_id for h in hits] == [pdf.id] and "20 JOD" in hits[0].text
    assert [d.id for d in r.use.list_documents(ADMIN)] == [pdf.id, md.id, txt.id]  # newest first


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"data": b""}, "empty"),
        ({"data": b"x" * (MAX_FILE_BYTES + 1)}, "larger than 5 MB"),
        ({"data": b"\x89PNG\r\n\x1a\n\x00\x00"}, "not allowed"),
        ({"data": b"\xff\xfe\xfa bad utf-8"}, "not a PDF or UTF-8"),
        ({"data": b"plain words", "filename": "notes.docx"}, "not allowed"),
        ({"data": b"plain words", "filename": "fake.pdf"}, "not allowed"),
        ({"data": make_pdf("x"), "filename": "real.txt"}, "does not match its name"),
        ({"data": make_pdf()}, "no text found"),
        ({"data": b"%PDF-1.4 broken"}, "could not be read"),
        ({"text": "   "}, "either a file or pasted text"),
        ({}, "either a file or pasted text"),
        ({"text": "words", "data": b"words"}, "either a file or pasted text"),
        ({"text": "x" * 200_001}, "longer than 200,000"),
        ({"text": "\n\n".join("w" * 401 for _ in range(MAX_PASSAGES + 1))}, "too long"),
    ],
)
def test_upload_refusals_are_invalid_input_and_write_nothing(kwargs: dict[str, object], message: str) -> None:
    r = rig()
    with pytest.raises(InvalidInput, match=message):
        r.use.upload(ADMIN, "Doc", **kwargs)  # type: ignore[arg-type]
    assert r.docs.list_all() == [] and r.vectors.count(COLLECTION) == 0


def test_upload_refuses_a_bad_title_or_office_and_a_pdf_without_extractor() -> None:
    r = rig(pdf=False)
    with pytest.raises(InvalidInput, match="title"):
        r.use.upload(ADMIN, "   ", text="words")
    with pytest.raises(InvalidInput, match="office"):
        r.use.upload(ADMIN, "Doc", "library", text="words")
    with pytest.raises(InvalidInput, match="PDF files cannot be read"):
        r.use.upload(ADMIN, "Doc", data=make_pdf("words"))


@pytest.mark.parametrize("caller", [STUDENT, STAFF, Caller(role="service", alias=None)])
def test_only_an_admin_may_manage_documents(caller: Caller) -> None:
    r = rig()
    doc = r.use.upload(ADMIN, "Doc", text=HANDBOOK)
    with pytest.raises(Unauthorized):
        r.use.upload(caller, "Doc", text="words")
    with pytest.raises(Unauthorized):
        r.use.list_documents(caller)
    with pytest.raises(Unauthorized):
        r.use.delete(caller, doc.id)
    assert r.docs.list_all() == [doc]


class FailingSecondBatch(LocalNumpyVectorStore):
    def __init__(self) -> None:
        super().__init__(TopicEncoder.dim, collections=(COLLECTION,))
        self.calls = 0

    def upsert(self, collection: str, items: Sequence[VectorItem]) -> None:
        self.calls += 1
        if self.calls == 2:
            raise StoreError("pgvector upsert knowledge failed: timeout")
        super().upsert(collection, items)


def test_a_failed_passage_write_removes_the_document_and_its_passages() -> None:
    r = rig(vectors=FailingSecondBatch())
    text = "\n\n".join(f"refund rule {i} " + "w" * 700 for i in range(60))  # 60 passages = 2 batches
    with pytest.raises(StoreError, match="timeout"):
        r.use.upload(ADMIN, "Long", text=text)
    assert r.docs.list_all() == [] and r.vectors.count(COLLECTION) == 0


# ---------------------------------------------------------------- list, delete, search


def test_delete_removes_the_document_and_every_passage() -> None:
    r = rig()
    keep = r.use.upload(ADMIN, "Library", text="The library opens at 8:00.")
    gone = r.use.upload(ADMIN, "Refunds", text="\n\n".join(f"refund {i} " + "w" * 500 for i in range(4)))
    assert gone.chunk_count >= 4 and r.vectors.count(COLLECTION) == gone.chunk_count + 1
    r.use.delete(ADMIN, gone.id)
    assert r.use.list_documents(ADMIN) == [keep] and r.vectors.count(COLLECTION) == 1
    assert r.use.search("refund policy") == []
    with pytest.raises(NotFound):
        r.use.delete(ADMIN, gone.id)
    with pytest.raises(NotFound):
        r.use.delete(ADMIN, "not-a-uuid")


def test_search_keeps_only_passages_at_or_above_the_floor() -> None:
    r = rig()
    doc = r.use.upload(ADMIN, "Handbook", "finance", text=HANDBOOK)
    [hit] = r.use.search("can I get a refund?")
    assert (hit.document_id, hit.title, hit.office) == (doc.id, "Handbook", "finance") and hit.sim >= 0.5
    assert r.use.search("the wifi is down") == [] and r.use.search("   ") == []


class Translator(TopicEncoder):
    """A stand-in for the translating encoder: Arabic topic words become English before embedding."""

    WORDS = {"استرداد": "refund", "المكتبة": "library"}

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            for ar, en in self.WORDS.items():
                text = text.replace(ar, en)
            out.extend(super().encode([text]))
        return out


class BrokenTranslator(TopicEncoder):
    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError("translator down")


def test_an_arabic_question_also_searches_translated_and_keeps_the_best_score() -> None:
    docs = InMemoryKnowledgeStore()
    store = LocalNumpyVectorStore(TopicEncoder.dim, collections=(COLLECTION,))
    plain = KnowledgeUseCase(docs, store, TopicEncoder(), Clock(), min_sim=0.5)
    doc = plain.upload(ADMIN, "Handbook", None, text=HANDBOOK)
    question = "بدي استرداد الرسوم"
    assert plain.search(question) == []  # the English handbook is out of reach as written
    both = KnowledgeUseCase(docs, store, TopicEncoder(), Clock(), min_sim=0.5, query_encoder=Translator())
    [hit] = both.search(question)
    assert hit.document_id == doc.id
    assert both.search("the wifi is down") == []  # an English question is never translated
    broken = KnowledgeUseCase(
        docs, store, TopicEncoder(), Clock(), min_sim=0.5, query_encoder=BrokenTranslator()
    )
    assert broken.search(question) == []  # a failing translation falls back to the direct search


# ---------------------------------------------------------------- chat grounding


@dataclass
class FailingSearch:
    calls: list[str] = field(default_factory=list)

    def search(self, text: str, k: int = 3) -> list[KnowledgeHit]:
        self.calls.append(text)
        raise StoreError("pgvector search knowledge failed: timeout")


def chat_with(knowledge: KnowledgeSearch, *replies: AgentReply) -> tuple[ScriptedAgent, ChatHarness]:
    agent = ScriptedAgent(replies=list(replies))
    return agent, build_chat(agent=agent, knowledge=knowledge)


def offered(agent: ScriptedAgent) -> Mapping[str, str]:
    ctx = agent.reply_calls[-1][0]
    return {s.id: s.text for s in ctx.sources if s.kind == "knowledge"}


def test_a_matching_question_gets_the_passage_and_the_cited_source() -> None:
    r = rig()
    doc = r.use.upload(ADMIN, "Student handbook", text=HANDBOOK)
    source_id = f"knowledge:{doc.id}"
    reply = AgentReply("The Student handbook says the library is closed on Friday.", "chat", (source_id,))
    agent, t = chat_with(r.use, reply)
    resp = t.uc.turn(turn_of(user("Is the library open on Friday?")), Caller())
    passage = offered(agent)[source_id]
    assert passage.startswith("Student handbook: ") and "closed on Friday" in passage
    assert resp.reply == reply.reply
    assert resp.sources == [dto.ChatSourceOut(id=source_id, kind="knowledge", title="Student handbook")]


def test_an_unrelated_question_gets_no_knowledge_source() -> None:
    r = rig()
    r.use.upload(ADMIN, "Student handbook", text=HANDBOOK)
    agent, t = chat_with(r.use, AgentReply("Hello! How can I help?", "chat"))
    resp = t.uc.turn(turn_of(user("hello there")), Caller())
    assert offered(agent) == {} and resp.sources == []


def test_only_offered_ids_are_cited_with_titles_and_announcements_count() -> None:
    r = rig()
    doc = r.use.upload(ADMIN, "Refund policy", text=HANDBOOK)
    real = f"knowledge:{doc.id}"
    agent = ScriptedAgent()
    t = build_chat(agent=agent, knowledge=r.use)
    notice = t.announcements.save_announcement(
        Announcement(
            "", "finance", "info", "Refund desk moved", "Upstairs.", datetime(2020, 1, 1, tzinfo=UTC)
        )
    )
    cited = ("knowledge:made-up", real, real, "announcement:missing", f"announcement:{notice.id}")
    agent.replies.append(AgentReply("The Refund policy gives a full refund in week one.", "chat", cited))
    resp = t.uc.turn(turn_of(user("when do I get a refund?")), Caller())
    assert [(s.id, s.kind, s.title) for s in resp.sources] == [
        (real, "knowledge", "Refund policy"),
        (f"announcement:{notice.id}", "announcement", "Refund desk moved"),
    ]


def test_a_template_reply_cites_nothing() -> None:
    r = rig()
    doc = r.use.upload(ADMIN, "Refund policy", text=HANDBOOK)
    reply = AgentReply("Request recorded, all done!", "confirm", (f"knowledge:{doc.id}",))
    _, t = chat_with(r.use, reply)
    resp = t.uc.turn(turn_of(user("yes, refund please")), Caller())
    assert resp.reply != reply.reply and resp.sources == []


def test_a_failing_knowledge_store_never_breaks_the_turn() -> None:
    failing = FailingSearch()
    agent, t = chat_with(failing, AgentReply("Sorry, I do not have that information.", "chat"))
    resp = t.uc.turn(turn_of(user("what is the refund policy?")), Caller())
    assert failing.calls == ["what is the refund policy?"]
    assert resp.mode == "agent" and resp.reply == "Sorry, I do not have that information."
    assert offered(agent) == {} and resp.sources == []


# ---------------------------------------------------------------- routes


def test_routes_upload_list_delete_and_errors() -> None:
    r = rig()
    client = api_client(services=ApiServices(knowledge=r.use))
    admin = auth("admin", "admin-1")
    up = client.post(
        "/v1/admin/knowledge",
        data={"title": "Handbook", "office": "finance", "text": HANDBOOK},
        headers=admin,
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["title"] == "Handbook" and body["office"] == "finance" and body["filename"] is None
    assert body["chunk_count"] == 1 and body["uploaded_by"] == "admin-1"
    files = {"file": ("lib.md", b"# Library\n\nOpen until 20:00.", "text/markdown")}
    up2 = client.post("/v1/admin/knowledge", data={"title": "Library"}, files=files, headers=admin)
    assert up2.status_code == 200 and up2.json()["filename"] == "lib.md" and up2.json()["office"] is None
    listed = client.get("/v1/admin/knowledge", headers=admin).json()["documents"]
    assert [d["title"] for d in listed] == ["Library", "Handbook"]
    bad = client.post(
        "/v1/admin/knowledge",
        data={"title": "Bin"},
        files={"file": ("x.bin", b"\x00\x01", "x")},
        headers=admin,
    )
    assert bad.status_code == 422 and "not allowed" in bad.text
    student = client.get("/v1/admin/knowledge", headers=auth("student", "stu-1"))
    assert student.status_code == 403
    gone = client.delete(f"/v1/admin/knowledge/{body['id']}", headers=admin)
    assert gone.status_code == 200 and gone.json() == {"id": body["id"], "deleted": True}
    assert client.delete(f"/v1/admin/knowledge/{body['id']}", headers=admin).status_code == 404
    assert [d["title"] for d in client.get("/v1/admin/knowledge", headers=admin).json()["documents"]] == [
        "Library"
    ]


def test_routes_answer_501_when_not_wired() -> None:
    client = api_client(None)
    admin = auth("admin", "admin-1")
    assert client.get("/v1/admin/knowledge", headers=admin).status_code == 501
    assert (
        client.post("/v1/admin/knowledge", data={"title": "T", "text": "x"}, headers=admin).status_code == 501
    )
    assert client.delete("/v1/admin/knowledge/x", headers=admin).status_code == 501


def test_local_store_delete_keeps_the_other_items() -> None:
    store = LocalNumpyVectorStore(2)
    store.upsert("c", [VectorItem(i, (1.0, float(n)), i, Lang.EN) for n, i in enumerate("abc")])
    store.delete("c", ["b", "zzz"])
    store.delete("missing", ["a"])
    assert [h.id for h in store.search("c", (1.0, 0.0), k=5)] == ["a", "c"] and store.count("c") == 2
    store.delete("c", ["a", "c"])
    assert store.count("c") == 0 and store.search("c", (1.0, 0.0), k=5) == []
