"""MetricsUseCase: `GET /v1/metrics`, the model lab (SPEC §6, P4.12).

Offline numbers come from the report `evaluate.py` writes (`REPORTS_DIR/model_lab.json`, the
`MetricsResponse` sections below); live numbers come from the repository (router stats and the stored
red-team runs) and the memory store. A missing report gives empty sections; a malformed section
is logged and left empty, so the page always renders.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, TypeVar

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.ports import ReportsSource
from campuspulse_ai.application.use_cases.responses import scorecard_out
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.ports import MemoryStore, Repository
from campuspulse_ai.domain.values import ArtifactVersion

log = logging.getLogger(__name__)

PER_THOUSAND = 1000
REDTEAM_HISTORY = 20
"""Red-team runs listed by `/v1/metrics` (the Repository default)."""
NO_ARTIFACT = dto.ArtifactOut(version="none", sha="")
"""Reported while no model artifact is loaded."""

M = TypeVar("M")


class MetricsUseCase:
    """`run() -> MetricsResponse`. Read-only.

    - `artifact`: the loaded artifact (`version: "none"`, `sha: ""` before models exist).
    - `generated_at`, `benchmark`, `coverage`, `ask_rate`, `ask_rate_is_proxy` (true unless the
      report says otherwise, LD-24), `calibration`, `fairness`, `ablations`, `confusions`: from the
      report.
    - `router`: `Repository.router_stats()` plus `cost_per_1k_usd`; `memory`: `MemoryStore.stats()`.
    - `redteam`: the newest `redteam_history` stored red-team scorecards (`Repository.redteam_history`,
      newest first; P4.11). A stored scorecard that no longer fits the contract is logged and skipped.

    Errors: `StoreError` from the repository or memory store (503). A bad report never fails it.
    """

    def __init__(
        self,
        reports: ReportsSource,
        repo: Repository,
        memory: MemoryStore,
        artifact: ArtifactVersion | None,
        *,
        redteam_history: int = REDTEAM_HISTORY,
    ) -> None:
        self._reports = reports
        self._repo = repo
        self._memory = memory
        self._artifact = artifact
        self._redteam_history = redteam_history

    def run(self) -> dto.MetricsResponse:
        report = self._load()
        router = self._repo.router_stats()
        memory = self._memory.stats()
        artifact = (
            dto.ArtifactOut(version=self._artifact.name, sha=self._artifact.sha256)
            if self._artifact
            else NO_ARTIFACT
        )
        return dto.MetricsResponse(
            artifact=artifact,
            generated_at=_datetime(report.get("generated_at")),
            benchmark=_rows(report, "benchmark", dto.BenchmarkRowOut.model_validate),
            coverage=_rows(report, "coverage", dto.CoverageRowOut.model_validate),
            ask_rate=_probability(report.get("ask_rate")),
            ask_rate_is_proxy=report.get("ask_rate_is_proxy") is not False,
            calibration=_rows(report, "calibration", dto.CalibrationOut.model_validate),
            fairness=_rows(report, "fairness", dto.FairnessSliceOut.model_validate),
            ablations=_rows(report, "ablations", dto.AblationRowOut.model_validate),
            confusions=_rows(report, "confusions", dto.ConfusionOut.model_validate),
            router=dto.RouterStatsOut(
                total=router.total,
                by_tier=dict(router.by_tier),
                resolved_tier0_pct=router.resolved_tier0_pct,
                cost_usd=router.cost_usd,
                cost_per_1k_usd=router.cost_usd / router.total * PER_THOUSAND if router.total else 0.0,
                cached_calls=router.cached_calls,
            ),
            memory=dto.MemoryStatsOut(
                active=memory.active,
                total=memory.total,
                by_category=dict(memory.by_category),
                last_added_at=memory.last_added_at,
            ),
            redteam=self._redteam(),
        )

    def _redteam(self) -> list[dto.ScorecardOut]:
        out = []
        for s in self._repo.redteam_history(limit=self._redteam_history):
            try:
                out.append(scorecard_out(s))
            except ValueError as exc:  # pydantic.ValidationError is a ValueError
                log.warning("red-team run %s skipped: it does not fit the contract: %s", s.run_id, exc)
        return out

    def _load(self) -> Mapping[str, object]:
        try:
            return self._reports.load() or {}
        except InvalidInput as exc:
            log.warning("model-lab report unreadable, metrics shown without it: %s", exc)
            return {}


def _rows(report: Mapping[str, object], key: str, validate: Callable[[Any], M]) -> list[M]:
    """The rows of one list section, each validated by its DTO; [] when absent or invalid."""
    raw = report.get(key)
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        log.warning("model-lab report: %s is not a list", key)
        return []
    try:
        return [validate(item) for item in raw]
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        log.warning("model-lab report: section %s is invalid and was skipped: %s", key, exc)
        return []


def _probability(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 <= float(value) <= 1.0:
        return None
    return float(value)


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
