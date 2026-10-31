"""Red-team wiring (P4.11): the use case for the API and the offline run for the CLI.

- `build_redteam(core, policy, repo, clock, settings, *, memory)` -> `RunRedTeamUseCase` over the
  rule-based `PerturbationGenerator` (seeds from `REDTEAM_SEED_CSV`, lists from `config/redteam.yaml`
  and the lexicons) and `RedTeamScorer`. `build_online` (lead) calls it with the online core, its
  policy, the Supabase repository and `memory=True`, then sets `ApiServices.redteam`.
- `run_offline_redteam(...)` is what `python services/ai/evaluate.py --redteam` runs: the frozen
  offline core (`build_offline`, memory off), an `InMemoryRepository`, and the report plus failure
  candidates written to `reports/redteam/`.

Seeds are never holdout rows: `load_seed_rows` refuses `data/our_test` and `data/robustness` (D-013).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from campuspulse_ai.adapters.redteam.config import RedTeamConfig
from campuspulse_ai.adapters.redteam.perturbation import PerturbationGenerator
from campuspulse_ai.adapters.redteam.report import write_candidates, write_report
from campuspulse_ai.adapters.redteam.scorer import RedTeamScorer
from campuspulse_ai.adapters.redteam.seeds import load_seed_rows
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.application.use_cases.ports import TriageClassifier
from campuspulse_ai.application.use_cases.run_redteam import RunRedTeamUseCase
from campuspulse_ai.config.paths import CONFIG_DIR, LEXICONS, REPO_ROOT, REPORTS
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactMissing
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.ports import Clock, DecisionPolicy, Repository

REDTEAM_YAML = CONFIG_DIR / "redteam.yaml"
REDTEAM_REPORTS = REPORTS / "redteam"
OFFLINE_MODULE = "campuspulse_ai.composition.offline"
"""The ML stream's offline container (P1.15), imported lazily: it is not on main yet."""

CoreFactory = Callable[[Path], tuple[TriageClassifier, DecisionPolicy]]
"""Builds the classifier and the decision policy from a model directory."""


class UtcClock:
    """`Clock` for the offline run (tz-aware UTC). Swap for `adapters.clock.SystemClock` once P1.15
    is merged."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def resolve(path: Path) -> Path:
    """A relative path is relative to the repo root (Settings paths), not the working directory."""
    return path if path.is_absolute() else REPO_ROOT / path


def build_redteam(
    core: TriageClassifier,
    policy: DecisionPolicy,
    repo: Repository,
    clock: Clock,
    settings: Settings,
    *,
    memory: bool,
    seed_csv: Path | None = None,
    config: RedTeamConfig | None = None,
) -> RunRedTeamUseCase:
    """The red-team use case (module docstring). Raises `InvalidInput` for a bad or holdout seed file,
    `KeyError`/`ValueError` for a bad `config/redteam.yaml`."""
    rows = load_seed_rows(resolve(seed_csv or settings.redteam_seed_csv))
    cfg = config or RedTeamConfig.load(REDTEAM_YAML, LEXICONS)
    return RunRedTeamUseCase(
        PerturbationGenerator(rows, cfg),
        core,
        policy,
        RedTeamScorer(),
        repo,
        clock,
        max_n=settings.redteam_max_n,
        memory=memory,
    )


def load_offline_core(model_dir: Path) -> tuple[TriageClassifier, DecisionPolicy]:
    """`build_offline(model_dir).core` and the policy over its frozen `tau_ood`.

    Raises `ArtifactMissing` while `composition.offline` is not merged, and whatever `build_offline`
    raises for an unusable model directory (`ArtifactError`).
    """
    try:
        offline: Any = importlib.import_module(OFFLINE_MODULE)
    except ModuleNotFoundError as exc:
        raise ArtifactMissing(
            f"{OFFLINE_MODULE} (build_offline, ML P1.15) is not available in this checkout"
        ) from exc
    container = offline.build_offline(model_dir)
    core: TriageClassifier = container.core
    return core, DefaultDecisionPolicy(float(container.config.thresholds.tau_ood))


@dataclass(frozen=True, slots=True)
class OfflineRedTeam:
    """What the CLI prints: the stored run id, its size and pass rate, and the files written."""

    run_id: str
    n: int
    overall: float
    properties: Mapping[str, float | None]
    report: Path
    candidates: Path | None


def run_offline_redteam(
    *,
    n: int,
    styles: Sequence[str],
    seed: int,
    settings: Settings,
    model_dir: Path | None = None,
    seed_csv: Path | None = None,
    out_dir: Path = REDTEAM_REPORTS,
    core_factory: CoreFactory = load_offline_core,
    clock: Clock | None = None,
) -> OfflineRedTeam:
    """Run the red team offline and write `<out_dir>/<stamp>.json` (+ `candidates_<stamp>.csv`).

    Raises `InvalidInput` (bad n, style or seed file), `ArtifactError` (no usable model), `OSError`.
    """
    resolved_model_dir = resolve(model_dir or settings.artifact_dir)
    resolved_seeds = resolve(seed_csv or settings.redteam_seed_csv)
    core, policy = core_factory(resolved_model_dir)
    used_clock = clock or UtcClock()
    use_case = build_redteam(
        core,
        policy,
        InMemoryRepository(used_clock),
        used_clock,
        settings,
        memory=False,
        seed_csv=resolved_seeds,
    )
    run = use_case.run_detailed(n, styles, seed)
    source = {
        "model_dir": _display(resolved_model_dir),
        "seed_csv": _display(resolved_seeds),
        "styles": list(styles) or "all",
        "generator": "rule-based PerturbationGenerator (config/redteam.yaml)",
        "memory": False,
    }
    report = write_report(run, out_dir, source)
    candidates = write_candidates(run, out_dir)
    s = run.scorecard
    return OfflineRedTeam(
        run_id=s.run_id,
        n=s.n,
        overall=s.overall,
        properties=run.properties,
        report=report,
        candidates=candidates,
    )


def _display(path: Path) -> str:
    """Repo-relative POSIX path when possible (reports stay machine-independent)."""
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
