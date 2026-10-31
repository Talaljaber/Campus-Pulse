"""WindowedCentroidDetector: incident detection on the live Pulse (P4.10, ARCHITECTURE §2.1 [13]).

Several similar reports from one building and category inside a short window are one incident
(e.g. "Wi-Fi down in M" from many students). Runs on the request embedding the classifier already
computed, over the VectorStore "requests" collection.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import timedelta

import numpy as np

from campuspulse_ai.domain.entities import Incident, IncidentDecision, Prediction, Request
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.ports import Clock, Repository, VectorStore

SEARCH_K = 50


class WindowedCentroidDetector:
    """IncidentDetector: windowed centroid clustering per (building, category).

    `detect(req, pred, embedding)`:
    1. No location on the request → `none`.
    2. Search "requests" for the same building and category created in the last `window_min`
       minutes (k=50, embeddings included), dropping `req` itself if it is already stored.
    3. Centroid = normalised mean of those embeddings plus `embedding`. Members = the rows, and
       the request itself, with cosine to the centroid >= `tau_inc`. The request must be a member.
    4. Fewer than `min_reports` members → `none`. Otherwise attach to the oldest open incident for
       that building and category opened inside the window, or open a new one.

    The incident is saved through the repository: a new one gets report_count = members and
    priority = max member priority; an attach adds one report and raises the priority to the
    request's if higher. Priority is bumped one level, once, when report_count reaches `bump_at`
    (capped at high). `IncidentDecision.members` lists the member request ids, `req` last. Merging
    member tickets, the single incident ticket and the broadcast belong to the action engine.

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
        since = self._clock.now() - self.window
        filters = {
            "building_id": location.building,
            "category": str(pred.category),
            "since": since,
            "with_embedding": True,
        }
        hits = [
            h
            for h in self._vectors.search("requests", embedding, k=SEARCH_K, min_sim=0.0, filters=filters)
            if h.id != req.id and h.embedding is not None
        ]
        own = _unit(np.asarray(embedding, dtype=np.float64))
        rows = np.vstack([_unit(np.asarray(h.embedding, dtype=np.float64)) for h in hits] + [own])
        centroid = _unit(rows.mean(axis=0))
        sims = rows @ centroid
        if sims[-1] < self.tau_inc:
            return IncidentDecision(kind="none", incident=None)
        member_hits = [h for h, s in zip(hits, sims[:-1], strict=True) if s >= self.tau_inc]
        members = [h.id for h in member_hits] + [req.id]
        if len(members) < self.min_reports:
            return IncidentDecision(kind="none", incident=None, members=members)

        open_ = self._repo.open_incidents(location.building, pred.category, since)
        if open_:
            current = open_[0]
            count = current.report_count + 1
            priority = self._priority(
                max(current.priority, pred.priority, key=_rank), current.report_count, count
            )
            saved = self._repo.save_incident(
                dataclasses.replace(current, report_count=count, priority=priority, member_ticket_ids=[])
            )
            return IncidentDecision(kind="attach", incident=saved, members=members)

        member_priorities = [Priority(str(h.meta.get("priority") or pred.priority)) for h in member_hits]
        base = max([pred.priority, *member_priorities], key=_rank)
        incident = Incident(
            id="",
            building=location.building,
            category=pred.category,
            title=f"{pred.category} reports in building {location.building}",
            priority=self._priority(base, 0, len(members)),
            report_count=len(members),
            status="open",
            member_ticket_ids=[],
            opened_at=self._clock.now(),
        )
        return IncidentDecision(kind="new", incident=self._repo.save_incident(incident), members=members)

    def _priority(self, priority: Priority, before: int, after: int) -> Priority:
        """Bump once, at the moment report_count first reaches bump_at."""
        return priority.bump() if before < self.bump_at <= after else priority


def _rank(p: Priority) -> int:
    return p.rank


def _unit(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 else v
