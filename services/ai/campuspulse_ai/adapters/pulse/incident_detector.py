"""WindowedCentroidDetector: incident detection on the live Pulse (P4.10, ARCHITECTURE §2.1 [13]).

Several similar reports from one building and category inside a short window are one incident
(e.g. "Wi-Fi down in M" from many students). Runs on the request embedding the classifier already
computed, over the VectorStore "requests" collection.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy as np

from campuspulse_ai.domain.entities import Incident, IncidentDecision, Prediction, Request
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.ports import Clock, Repository, VectorStore

SEARCH_K = 50
ANY_AGE = datetime(1970, 1, 1, tzinfo=UTC)  # open_incidents(since=...) for "whatever its age"


class WindowedCentroidDetector:
    """IncidentDetector: windowed centroid clustering per (building, category), D-007 + D-015.

    `detect(req, pred, embedding)`:
    1. No location on the request → `none`.
    2. **Attach (D-007 amended by D-015).** For each open incident of that building and category,
       whatever its age, the centroid is the re-normalised mean of its members' unit embeddings
       (members = the requests whose tickets carry the incident id, `Repository.incident_members`;
       their vectors come from the "requests" collection). It is recomputed on every call, so it is
       the running mean of the reports attached so far. The request attaches to the open incident
       with the highest cosine to its centroid, if that cosine is >= `tau_inc`; members = [req.id].
       An incident whose members cannot be resolved (no linked tickets) takes no new reports.
    3. **Open.** Otherwise search "requests" for the same building and category created in the last
       `window_min` minutes (k=50, embeddings included), dropping `req` itself and the members of
       open incidents. Centroid = normalised mean of those embeddings plus `embedding`; members = the
       rows, and the request itself, with cosine to the centroid >= `tau_inc` (the request must be a
       member).
    4. At least `min_reports` members → `new`, else `none`. The window only bounds opening.

    The incident is saved through the repository: a new one gets report_count = members and
    priority = max member priority; an attach adds one report and raises the priority to the
    request's if higher. Priority is bumped one level, once, when report_count reaches `bump_at`
    (capped at high). `IncidentDecision.members` lists the member request ids, `req` last. Merging
    member tickets, the single incident ticket and the broadcast belong to the action engine
    (`application/use_cases/incidents.IncidentActions`), which links member tickets to the incident.

    `tau_inc` comes from `config/hand_tuned.yaml` (D-015: 0.92 for the v1-rc1 encoder; the margin to
    unrelated same-building complaints is thin, so it is re-measured whenever the encoder changes).

    Raises StoreError from the repository or vector store; never changes request labels.
    """

    def __init__(
        self,
        repo: Repository,
        vectors: VectorStore,
        clock: Clock,
        tau_inc: float,
        window_min: int,
        min_reports: int = 3,
        bump_at: int = 6,
    ) -> None:
        self._repo = repo
        self._vectors = vectors
        self._clock = clock
        self.tau_inc = tau_inc
        self.window = timedelta(minutes=window_min)
        self.min_reports = min_reports
        self.bump_at = bump_at

    def detect(self, req: Request, pred: Prediction, embedding: Sequence[float]) -> IncidentDecision:
        location = req.normalized.location if req.normalized else None
        if location is None:
            return IncidentDecision(kind="none", incident=None)
        own = _unit(np.asarray(embedding, dtype=np.float64))
        scope: dict[str, object] = {"building_id": location.building, "category": str(pred.category)}
        open_members: set[str] = set()
        best: tuple[float, Incident] | None = None
        for incident in self._repo.open_incidents(location.building, pred.category, ANY_AGE):
            members = {r.id for _, r in self._repo.incident_members(incident.id)} - {req.id}
            open_members |= members
            centroid = self._centroid(embedding, scope, members)
            if centroid is None:
                continue
            sim = float(own @ centroid)
            if sim >= self.tau_inc and (best is None or sim > best[0]):
                best = (sim, incident)
        if best is not None:
            current = best[1]
            count = current.report_count + 1
            priority = self._priority(
                max(current.priority, pred.priority, key=_rank), current.report_count, count
            )
            saved = self._repo.save_incident(
                dataclasses.replace(current, report_count=count, priority=priority, member_ticket_ids=[])
            )
            return IncidentDecision(kind="attach", incident=saved, members=[req.id])

        filters = {**scope, "since": self._clock.now() - self.window, "with_embedding": True}
        hits = [
            h
            for h in self._vectors.search("requests", embedding, k=SEARCH_K, min_sim=0.0, filters=filters)
            if h.id != req.id and h.id not in open_members and h.embedding is not None
        ]
        rows = np.vstack([_unit(np.asarray(h.embedding, dtype=np.float64)) for h in hits] + [own])
        centroid = _unit(rows.mean(axis=0))
        sims = rows @ centroid
        if sims[-1] < self.tau_inc:
            return IncidentDecision(kind="none", incident=None)
        member_hits = [h for h, s in zip(hits, sims[:-1], strict=True) if s >= self.tau_inc]
        members_ids = [h.id for h in member_hits] + [req.id]
        if len(members_ids) < self.min_reports:
            return IncidentDecision(kind="none", incident=None, members=members_ids)

        member_priorities = [Priority(str(h.meta.get("priority") or pred.priority)) for h in member_hits]
        base = max([pred.priority, *member_priorities], key=_rank)
        incident = Incident(
            id="",
            building=location.building,
            category=pred.category,
            title=f"{pred.category} reports in building {location.building}",
            priority=self._priority(base, 0, len(members_ids)),
            report_count=len(members_ids),
            status="open",
            member_ticket_ids=[],
            opened_at=self._clock.now(),
        )
        return IncidentDecision(kind="new", incident=self._repo.save_incident(incident), members=members_ids)

    def _centroid(
        self, embedding: Sequence[float], scope: dict[str, object], members: set[str]
    ) -> np.ndarray | None:
        """Re-normalised mean of the members' unit embeddings (None when none is stored)."""
        if not members:
            return None
        hits = self._vectors.search(
            "requests", embedding, k=SEARCH_K, min_sim=-1.0, filters={**scope, "with_embedding": True}
        )
        vectors = [
            _unit(np.asarray(h.embedding, dtype=np.float64))
            for h in hits
            if h.id in members and h.embedding is not None
        ]
        return _unit(np.mean(np.vstack(vectors), axis=0)) if vectors else None

    def _priority(self, priority: Priority, before: int, after: int) -> Priority:
        """Bump once, at the moment report_count first reaches bump_at."""
        return priority.bump() if before < self.bump_at <= after else priority


def _rank(p: Priority) -> int:
    return p.rank


def _unit(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 else v
