"""Offline isolation (ARCHITECTURE §3.18): the offline path never imports pgvector or supabase.

Covers part (a) of the §3.18 proof and the store-level half of (b): a loaded index exposes
exactly its frozen collections, read-only. The rest of (b) and (c)-(d) need build_offline /
BatchPredictUseCase; the build_offline check here activates once composition.offline exists.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PG_MODULES = ("campuspulse_ai.adapters.vectors.pgvector", "campuspulse_ai.adapters.memory.pgvector_memory")


def _imported_after(module: str) -> set[str]:
    code = f"import sys, {module}; print('\\n'.join(sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    return set(out.split())


@pytest.mark.parametrize("module", PG_MODULES)
def test_pgvector_adapters_do_not_import_the_sdk(module: str) -> None:
    loaded = _imported_after(module)
    assert not {"supabase", "postgrest"} & loaded


def test_local_store_imports_nothing_online() -> None:
    loaded = _imported_after("campuspulse_ai.adapters.vectors.local_numpy")
    assert not {"supabase", "postgrest", "httpx", *PG_MODULES} & loaded


def test_loaded_index_holds_only_its_own_collections(tmp_path: Path) -> None:
    from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore

    frozen = ("train", "injection_exemplars", "safety_exemplars")
    LocalNumpyVectorStore(8, collections=frozen).save(tmp_path)
    store = LocalNumpyVectorStore.load(tmp_path, expected_dim=8)
    assert store.collections() == frozenset(frozen)
    assert store.read_only


def test_offline_composition_never_imports_pgvector() -> None:
    if importlib.util.find_spec("campuspulse_ai.composition.offline") is None:
        pytest.skip("composition.offline not built yet (P1)")
    loaded = _imported_after("campuspulse_ai.composition.offline")
    assert not {"supabase", "postgrest", *PG_MODULES} & loaded


# --- P1.18: the rest of (b) and (d) on the real frozen v1 --------------------------------------------


@pytest.mark.artifacts
def test_offline_store_collections_exact() -> None:
    from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
    from campuspulse_ai.composition.offline import build_offline
    from campuspulse_ai.config.paths import MODELS_FROZEN

    container = build_offline(MODELS_FROZEN)
    assert isinstance(container.vectors, LocalNumpyVectorStore)
    assert container.vectors.collections() == {"train", "injection_exemplars", "safety_exemplars"}
    assert container.vectors.read_only


@pytest.mark.artifacts
def test_predict_succeeds_with_unreachable_supabase_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    from campuspulse_ai.config.paths import DATA_RAW
    from campuspulse_ai.frameworks.cli.predict import main

    def blocked(*_a: object, **_k: object) -> None:
        raise OSError("network disabled in test")

    monkeypatch.setenv("SUPABASE_URL", "https://unreachable.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "not-a-key")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    out = tmp_path / "pred.csv"
    assert main(["--input", str(DATA_RAW / "validation.csv"), "--output", str(out)]) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 63
