"""P4.13 memory and latency budget: the pieces that cut RSS and round trips without changing labels.

- `OnnxEncoder(low_memory=True)` gives the same vectors (artifacts);
- `QueryCachingMemoryStore` answers the second identical neighbour query from memory;
- `ActUseCase.open_ticket` writes the ticket row once (the record sink is skipped after the save);
- `PostgrestRest` sends the same PostgREST requests as supabase-py;
- `trim_heap` never raises;
- `scripts/measure_rss.py` and `scripts/env_for_docker.py` helpers.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import httpx
import numpy as np
import pytest
import respx
import yaml
from fixtures.backend_fakes import FakeCore, FakeSink, make_core
from fixtures.containers import build_test

from campuspulse_ai.adapters.memory.cached import QueryCachingMemoryStore
from campuspulse_ai.adapters.memory.inmemory import InMemoryMemoryStore
from campuspulse_ai.adapters.models.encoder import ENCODER_META, OnnxEncoder
from campuspulse_ai.adapters.store.rest import PostgrestRest
from campuspulse_ai.application.dto import TriageRequest
from campuspulse_ai.config.paths import CONFIG_DIR, MODELS_FROZEN, REPO_ROOT
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang
from campuspulse_ai.frameworks.heap import trim_heap

TRAIN = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
ENCODER_DIR = MODELS_FROZEN / TRAIN["artifact_version"] / "encoder"
URL = "https://project.supabase.example"
KEY = "service-role-test-key"


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.artifacts
def test_low_memory_onnx_gives_identical_vectors() -> None:
    if not (ENCODER_DIR / ENCODER_META).is_file():
        pytest.skip("no encoder: run scripts/fetch_models.py")
    texts = ["The campus Wi-Fi disconnects", "وين جدول الباصات", "mesh 3arif wein el bus", "x"]
    plain = OnnxEncoder(ENCODER_DIR, intra_op_threads=1).encode_array(texts)
    lean = OnnxEncoder(ENCODER_DIR, intra_op_threads=1, low_memory=True).encode_array(texts)
    assert np.array_equal(plain, lean)  # bit for bit, not just close


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.t


class CountingMemory(InMemoryMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.queries = 0

    def neighbors(self, embedding, k, min_sim):  # type: ignore[no-untyped-def]
        self.queries += 1
        return super().neighbors(embedding, k, min_sim)


def _example(vec: tuple[float, ...]) -> MemoryExample:
    now = datetime.now(UTC)
    return MemoryExample("", "wifi down", Lang.EN, vec, Category.IT_SUPPORT, Priority.HIGH, "u", now)


def test_the_second_identical_memory_query_is_cached() -> None:
    inner, clock = CountingMemory(), Clock()
    memory = QueryCachingMemoryStore(inner, clock, ttl_s=2.0)
    memory.add(_example((1.0, 0.0, 0.0)))
    first = memory.neighbors((1.0, 0.0, 0.0), 5, 0.5)
    assert memory.neighbors((1.0, 0.0, 0.0), 5, 0.5) == first and inner.queries == 1
    memory.neighbors((1.0, 0.0, 0.0), 3, 0.5)  # another question
    assert inner.queries == 2
    clock.t += timedelta(seconds=3)  # expired
    memory.neighbors((1.0, 0.0, 0.0), 3, 0.5)
    assert inner.queries == 3
    memory.add(_example((0.0, 1.0, 0.0)))  # a correction clears the cache: the next request sees it
    memory.neighbors((1.0, 0.0, 0.0), 3, 0.5)
    assert inner.queries == 4 and memory.stats().active == 2
    off = QueryCachingMemoryStore(inner, clock, ttl_s=0)
    off.neighbors((1.0, 0.0, 0.0), 3, 0.5)
    off.neighbors((1.0, 0.0, 0.0), 3, 0.5)
    assert inner.queries == 6


def test_a_ticket_row_is_written_once() -> None:
    text = "the shuttle bus is late again"
    record, linear = FakeSink(name="supabase"), FakeSink(name="linear")
    c = build_test(core=FakeCore().add(text, make_core({"Transportation": 0.9}, {"medium": 0.9})),
                   sinks=[record, linear])  # fmt: skip
    r = c.triage.run(TriageRequest(text=text, student_alias="demo-17"))
    assert r.action is not None and r.action.ticket_id in c.repo.tables["tickets"]
    assert record.calls == [] and linear.calls == [("create", r.action.ticket_id)]


@respx.mock
def test_postgrest_rest_sends_what_supabase_py_sends() -> None:
    select = respx.get(f"{URL}/rest/v1/buildings").mock(return_value=httpx.Response(200, json=[{"id": "M"}]))
    rpc = respx.post(f"{URL}/rest/v1/rpc/vector_dim").mock(return_value=httpx.Response(200, json=384))
    rest = PostgrestRest(f"{URL}/", KEY, timeout_s=5)
    assert rest.table("buildings").select("id").limit(1).execute().data == [{"id": "M"}]
    assert rest.rpc("vector_dim").execute().data == 384
    sent = select.calls.last.request
    assert sent.headers["apikey"] == KEY and sent.headers["authorization"] == f"Bearer {KEY}"
    assert sent.url.params["select"] == "id" and sent.url.params["limit"] == "1"
    assert json.loads(rpc.calls.last.request.content) == {}
    with pytest.raises(ValueError):
        PostgrestRest("project.supabase.co", KEY, timeout_s=5)


def test_trim_heap_never_raises() -> None:
    assert trim_heap() in (True, False)
    if not sys.platform.startswith("linux"):
        assert trim_heap() is False


def test_measure_rss_helpers(tmp_path: Path) -> None:
    m = _script("measure_rss")
    assert m.percentile(list(range(1, 101)), 95) == 95 and m.percentile([5.0], 95) == 5.0
    with pytest.raises(ValueError, match="holdout"):
        m.load_texts(Path("data/our_test/our_test.csv"))
    csv_path = tmp_path / "v.csv"
    csv_path.write_text("request_id,text\nA,hello there\nB,مرحبا\n", encoding="utf-8")
    texts = m.load_texts(csv_path)
    assert texts[0] == "hello there" and texts[1] in m.ARABIZI and "مرحبا" in texts


def test_env_for_docker_strips_comments_and_refuses_the_repo(tmp_path: Path) -> None:
    e = _script("env_for_docker")
    src = tmp_path / ".env"
    src.write_text('A=1            # scope: ai\nB="two words"  # c\nEMPTY=     # x\nC=3\n', encoding="utf-8")
    values = e.clean_env(src, ["D=4", "C=9"], ["A"])
    assert values == {"B": "two words", "C": "9", "D": "4"}
    out = e.write_env(values, tmp_path / "docker.env")
    assert out.read_bytes() == b"B=two words\nC=9\nD=4\n"
    with pytest.raises(ValueError):
        e.clean_env(src, ["no-equals"], [])
    assert e.main(["--env", str(src), "--out", str(REPO_ROOT / "x.env")]) == 2
