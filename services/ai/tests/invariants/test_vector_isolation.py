"""Offline isolation (ARCHITECTURE §3.18): the offline path never imports pgvector or supabase.

Covers part (a) of the §3.18 proof. Parts (b)-(d) need build_offline / BatchPredictUseCase and
belong with those tasks; the build_offline check here activates once composition.offline exists.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

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


def test_offline_composition_never_imports_pgvector() -> None:
    if importlib.util.find_spec("campuspulse_ai.composition.offline") is None:
        pytest.skip("composition.offline not built yet (P1)")
    loaded = _imported_after("campuspulse_ai.composition.offline")
    assert not {"supabase", "postgrest", *PG_MODULES} & loaded
