"""`composition.online` (P4.3): the production wiring over in-memory adapters and the tiny real model.

`wire_online` is exactly what `build_online` runs after building the Supabase adapters, so these tests
drive the real `TriageCore` (trained by `train.py` on the tiny fixture, hashing encoder) through the
real app over HTTP, with `InMemoryRepository`, `LocalNumpyVectorStore`, `InMemoryMemoryStore` and
fakes for Linear and email. No network.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fixtures.api import api_client, api_settings, auth
from fixtures.backend_fakes import FakeNotifier, FakeSink, FrozenClock
from fixtures.fakes import HashingEncoder
from pydantic import SecretStr

from campuspulse_ai.adapters.calendar.slots_table import SlotsTableCalendar
from campuspulse_ai.adapters.integrations.retrying import RetryingSink
from campuspulse_ai.adapters.integrations.supabase_sink import SupabaseSink
from campuspulse_ai.adapters.memory.inmemory import InMemoryMemoryStore
from campuspulse_ai.adapters.notify.inapp import InAppNotifier
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.composition import online
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.composition.offline import OfflineContainer, build_offline
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactMissing, StoreError
from campuspulse_ai.domain.policy import RecipientPolicy

INBOX = "student-inbox@campuspulse.invalid"


@dataclass
class Wired:
    services: ApiServices
    repo: InMemoryRepository
    vectors: LocalNumpyVectorStore
    memory: InMemoryMemoryStore
    linear: FakeSink
    email: FakeNotifier
    client: TestClient


@pytest.fixture(scope="module")
def offline(tiny_model_dir: Path) -> OfflineContainer:
    return build_offline(tiny_model_dir, encoder_override=HashingEncoder())


def wire(offline: OfflineContainer, **settings: Any) -> Wired:
    clock = FrozenClock()
    repo = InMemoryRepository(clock)
    vectors = LocalNumpyVectorStore(offline.config.encoder.dim, collections=("requests", "faq"))
    memory = InMemoryMemoryStore()
    linear, email = FakeSink(name="linear"), FakeNotifier()
    cfg = api_settings(demo_email_allowlist=frozenset({INBOX}), **settings)
    adapters = online.OnlineAdapters(
        repo=repo,
        vectors=vectors,
        memory=memory,
        sinks=(SupabaseSink(repo), linear),
        channels={"in_app": InAppNotifier(repo), "email": email},
        calendars=(SlotsTableCalendar(repo, clock, RecipientPolicy(cfg.demo_email_allowlist)),),
        vector_store="local",
    )
    services = online.wire_online(cfg, offline, adapters, clock)
    return Wired(services, repo, vectors, memory, linear, email, api_client(services=services, settings=cfg))


def test_every_route_use_case_is_wired_and_health_is_ok(offline: OfflineContainer) -> None:
    w = wire(offline)
    s = w.services
    assert None not in (s.triage, s.clarify, s.tickets, s.sla, s.clock, s.batch, s.metrics, s.redteam)
    body = w.client.get("/health").json()
    assert body["status"] == "ok" and body["artifact"] == offline.manifest.artifact_version
    assert body["sha"] == offline.manifest.sha and body["encoder_loaded"] is True
    assert body["sinks"] == ["supabase", "linear"] and body["llm_tiers"] == []
    assert body["vector_store"] == "local"


def test_online_core_is_the_frozen_model_with_live_memory(offline: OfflineContainer) -> None:
    w = wire(offline)
    assert w.services.triage is not None
    core = w.services.triage._core  # noqa: SLF001 - the wiring under test
    assert core is not offline.core and core.memory is w.memory
    assert core.ensemble is offline.core.ensemble and core.artifact == offline.core.artifact


def test_triage_over_http_classifies_with_the_real_core(offline: OfflineContainer) -> None:
    w = wire(offline)
    r = w.client.post(
        "/v1/triage",
        json={"text": "The Wi-Fi in building M keeps dropping", "location": {"building": "M"}},
        headers=auth("student", "demo-17"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in {"decided", "needs_clarification", "human_review", "out_of_scope"}
    assert w.repo.tables["requests"] and w.repo.tables["predictions"]
    stored = next(iter(w.repo.tables["predictions"].values()))
    assert stored["artifact_version"] == offline.manifest.artifact_version
    # [12b]: the request embedding is the core's own vector, stored with its building
    hits = w.vectors.search("requests", [1.0] * offline.config.encoder.dim, 5, -1.0)
    assert [h.id for h in hits] == [body["request_id"]] and hits[0].meta["building_id"] == "M"


def test_a_decided_ticket_reaches_the_record_and_the_mirror(offline: OfflineContainer) -> None:
    w = wire(offline)
    # a training sentence: singleton sets on the tiny model -> decided; the empty FAQ -> a ticket
    text = "I need a copy of my payment receipt Please respond when possible."
    body = w.client.post("/v1/triage", json={"text": text}, headers=auth("service")).json()
    assert body["status"] == "decided" and body["category"]["label"] == "Finance"
    assert body["action"]["ticket_id"] in w.repo.tables["tickets"]
    assert [c[0] for c in w.linear.calls] == ["create"]


def test_batch_uses_the_offline_labeler(offline: OfflineContainer) -> None:
    w = wire(offline)
    r = w.client.post(
        "/v1/batch",
        files={"file": ("in.csv", b"request_id,text\nA,The bus is late\n", "text/csv")},
        headers=auth("admin"),
    )
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"request_id,category,priority\nA,")


def test_llm_is_off_by_default_and_without_a_key(offline: OfflineContainer) -> None:
    clock = FrozenClock()
    assert online.llm_wiring(api_settings(), offline, clock) == online.LLMWiring()
    no_key = api_settings(enable_llm=True, openrouter_tier1_model="pinned/model")
    assert online.llm_wiring(no_key, offline, clock).oracles == ()


def test_llm_tier_is_wired_when_enabled_and_configured(offline: OfflineContainer, tmp_path: Path) -> None:
    cfg = api_settings(enable_llm=True, openrouter_api_key=SecretStr("k"),
                       openrouter_tier1_model="pinned/model", llm_cache_path=tmp_path / "llm.sqlite")  # fmt: skip
    wiring = online.llm_wiring(cfg, offline, FrozenClock())
    assert len(wiring.oracles) == 1 and wiring.understander is not None and wiring.tiers == ("tier1",)


def test_missing_artifacts_fail_startup_with_the_fetch_command(tmp_path: Path) -> None:
    with pytest.raises(ArtifactMissing, match="fetch_models.py"):
        online.load_offline(api_settings(artifact_dir=tmp_path / "nothing"))


def test_supabase_must_be_configured() -> None:
    with pytest.raises(StoreError, match="SUPABASE_URL"):
        online.supabase_client(Settings(_env_file=None))  # type: ignore[call-arg]


def test_linear_mirror_needs_sinks_enabled_and_a_key() -> None:
    clock = FrozenClock()
    assert online.mirror_sinks(api_settings(enable_sinks=True), clock) == []
    assert online.mirror_sinks(api_settings(enable_sinks=False, linear_api_key=SecretStr("k")), clock) == []
    [sink] = online.mirror_sinks(api_settings(enable_sinks=True, linear_api_key=SecretStr("k")), clock)
    assert isinstance(sink, RetryingSink) and sink.name == "linear"


def test_email_channel_only_with_smtp_credentials() -> None:
    repo, clock, policy = InMemoryRepository(), FrozenClock(), RecipientPolicy(frozenset({INBOX}))
    assert set(online.notifier_channels(api_settings(), repo, policy, clock)) == {"in_app"}
    cfg = api_settings(gmail_smtp_user="sender@campuspulse.invalid", gmail_app_password=SecretStr("p"))
    assert set(online.notifier_channels(cfg, repo, policy, clock)) == {"in_app", "email"}
