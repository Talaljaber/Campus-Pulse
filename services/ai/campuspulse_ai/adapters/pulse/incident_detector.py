"""WindowedCentroidDetector: incident detection on the live Pulse (P4.10, ARCHITECTURE §2.1 [13]).

Several similar reports from one building inside a short window are one incident (e.g. "Wi-Fi down in
M" from many students). Runs on the request embedding the classifier already computed, over the
VectorStore "requests" collection. Grouping is by building only (D-017): similarity to the incident
centroid (D-015) separates different problems, not the predicted label, which can scatter one outage
across categories.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy as np

from campuspulse_ai.domain.entities import Incident, IncidentDecision, Prediction, Request, Ticket
from campuspulse_ai.domain.labels import CATEGORY_ORDER, Category, Priority
from campuspulse_ai.domain.ports import Clock, Repository, VectorStore
from campuspulse_ai.domain.values import TicketStatus

SEARCH_K = 50
INCIDENT_TAG = "incident"  # same value as application/use_cases/mirror.INCIDENT_TAG
ANY_AGE = datetime(1970, 1, 1, tzinfo=UTC)  # open_incidents(since=...) for "whatever its age"


@dataclasses.dataclass
class _State:
    """An open incident with its recomputed centroid, member categories and member vectors."""

    incident: Incident
    centroid: np.ndarray
    categories: list[Category | None]
    vectors: list[np.ndarray]


class WindowedCentroidDetector:
    """IncidentDetector: windowed centroid clustering per building, D-007 + D-015 + D-017.

    `detect(req, pred, embedding)`:
    1. No location on the request → `none`.
    2. **Attach (D-007 amended by D-015, D-017).** For each open incident of that building, whatever
       its age and category, the centroid is the re-normalised mean of its members' unit embeddings
       (members = the requests whose tickets carry the incident id, `Repository.incident_members`;
       their vectors come from the "requests" collection). It is recomputed on every call, so it is
       the running mean of the reports attached so far. The request attaches to the open incident
       with the highest cosine to its centroid, if that cosine is >= `tau_inc`; members = [req.id].
       An incident whose members cannot be resolved (no linked tickets) takes no new reports.
    3. **Open.** Otherwise search "requests" for the same building (any predicted category) created in
       the last `window_min` minutes (k=50, embeddings included), dropping `req` itself and the members of
       open incidents. Centroid = normalised mean of those embeddings plus `embedding`; members = the
       rows, and the request itself, with cosine to the centroid >= `tau_inc` (the request must be a
       member).
    4. **Merge rule (D-021).** A new cluster whose centroid has cosine >= `tau_inc` to an open
       incident's centroid joins that incident (`attach`, members = the cluster, whatever its size)
       instead of opening a second one. Two open incidents of one building whose centroids reach
       `tau_inc` are merged first, the smaller into the larger (`_absorb_duplicates`).
       Otherwise at least `min_reports` members → `new`, else `none`. The window only bounds opening.
    5. **Category (D-017).** The incident's category is the majority of its reports' predicted
       categories. A tie keeps the incident's current category on an attach (no flip-flopping) and
       takes the newest report's category when an incident opens, then the label order. It is
       recomputed on every attach, and the title follows it ("<category> reports in building X").

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
        scope: dict[str, object] = {"building_id": location.building}
        open_members: set[str] = set()
        states: list[_State] = []
        for incident in self._repo.open_incidents(location.building, None, ANY_AGE):
            members = {r.id for _, r in self._repo.incident_members(incident.id)} - {req.id}
            open_members |= members
            found = self._centroid(embedding, scope, members)
            if found is not None:
                states.append(_State(incident, *found))
        states, absorbed = self._absorb_duplicates(states)

        best: tuple[float, _State] | None = None
        for state in states:
            sim = float(own @ state.centroid)
            if sim >= self.tau_inc and (best is None or sim > best[0]):
                best = (sim, state)
        if best is not None:
            return self._attach(
                best[1], [req.id], [pred.category], pred.priority, location.building, absorbed
            )

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
            return IncidentDecision(kind="none", incident=None, absorbed=absorbed)
        member_hits = [h for h, s in zip(hits, sims[:-1], strict=True) if s >= self.tau_inc]
        members_ids = [h.id for h in member_hits] + [req.id]
        member_priorities = [Priority(str(h.meta.get("priority") or pred.priority)) for h in member_hits]
        base = max([pred.priority, *member_priorities], key=_rank)
        reported = [_category(h.meta.get("category")) for h in member_hits]

        if len(members_ids) < self.min_reports:
            return IncidentDecision(kind="none", incident=None, members=members_ids, absorbed=absorbed)

        # Merge rule (D-021): a new cluster (min_reports or more) whose centroid is >= tau_inc of an
        # open incident joins it instead of opening a second one.
        cluster = _unit(np.vstack([rows[:-1][sims[:-1] >= self.tau_inc], own]).mean(axis=0))
        joined = [(float(cluster @ s.centroid), s) for s in states]
        joined = [(sim, s) for sim, s in joined if sim >= self.tau_inc]
        if joined:
            target = max(joined, key=lambda j: j[0])[1]
            return self._attach(
                target, members_ids, [*reported, pred.category], base, location.building, absorbed
            )

        category = majority([*reported, pred.category], pred.category)
        incident = Incident(
            id="",
            building=location.building,
            category=category,
            title=_title(category, location.building),
            priority=self._priority(base, 0, len(members_ids)),
            report_count=len(members_ids),
            status="open",
            member_ticket_ids=[],
            opened_at=self._clock.now(),
        )
        return IncidentDecision(
            kind="new", incident=self._repo.save_incident(incident), members=members_ids, absorbed=absorbed
        )

    def _attach(
        self,
        state: _State,
        member_ids: list[str],
        categories: list[Category | None],
        priority: Priority,
        building: str,
        absorbed: list[Ticket],
    ) -> IncidentDecision:
        current = state.incident
        count = current.report_count + len(member_ids)
        bumped = self._priority(max(current.priority, priority, key=_rank), current.report_count, count)
        category = majority([*state.categories, *categories], current.category)
        title = current.title if category == current.category else _title(category, building)
        saved = self._repo.save_incident(
            dataclasses.replace(
                current,
                category=category,
                title=title,
                report_count=count,
                priority=bumped,
                member_ticket_ids=[],
            )
        )
        return IncidentDecision(kind="attach", incident=saved, members=member_ids, absorbed=absorbed)

    def _absorb_duplicates(self, states: list[_State]) -> tuple[list[_State], list[Ticket]]:
        """Merge rule (D-021): two open incidents of one building whose centroids are >= `tau_inc` apart
        are one incident. The smaller (then the newer) folds into the larger: its member tickets move
        over, the count, majority category, priority and centroid are recomputed, its incident ticket
        becomes `merged` (no longer tagged as an incident ticket), the duplicate is resolved and an
        audit event is written. Returns the surviving states and the folded incident tickets."""
        absorbed: list[Ticket] = []
        while True:
            pair = next(
                (
                    (a, b)
                    for i, a in enumerate(states)
                    for b in states[i + 1 :]
                    if float(a.centroid @ b.centroid) >= self.tau_inc
                ),
                None,
            )
            if pair is None:
                return states, absorbed
            keep, drop = sorted(
                pair, key=lambda s: (-s.incident.report_count, s.incident.opened_at, s.incident.id)
            )
            saved, moved = self._fold(keep, drop)
            absorbed += moved
            vectors = [*keep.vectors, *drop.vectors]
            combined = _State(
                saved,
                _unit(np.mean(np.vstack(vectors), axis=0)),
                [*keep.categories, *drop.categories],
                vectors,
            )
            states = [combined if s is keep else s for s in states if s is not drop]

    def _fold(self, keep: _State, drop: _State) -> tuple[Incident, list[Ticket]]:
        moved: list[Ticket] = []
        for ticket, _ in self._repo.incident_members(drop.incident.id):
            if INCIDENT_TAG in ticket.tags:
                ticket = dataclasses.replace(
                    ticket,
                    incident_id=keep.incident.id,
                    status=TicketStatus.MERGED,
                    tags=tuple(t for t in ticket.tags if t != INCIDENT_TAG),
                )
                moved.append(ticket)
            else:
                ticket = dataclasses.replace(ticket, incident_id=keep.incident.id)
            self._repo.save_ticket(ticket)
        a, b = keep.incident, drop.incident
        count = a.report_count + b.report_count
        category = majority([*keep.categories, *drop.categories], a.category)
        priority = self._priority(max(a.priority, b.priority, key=_rank), a.report_count, count)
        saved = self._repo.save_incident(
            dataclasses.replace(
                a,
                category=category,
                title=a.title if category == a.category else _title(category, a.building),
                report_count=count,
                priority=priority,
                member_ticket_ids=[],
            )
        )
        self._repo.save_incident(
            dataclasses.replace(b, status="resolved", resolved_at=self._clock.now(), member_ticket_ids=[])
        )
        self._repo.append_event(
            "pulse", "incident.absorbed", f"incident:{a.id}", {"absorbed": b.id, "reports": b.report_count}
        )
        return saved, moved

    def _centroid(
        self, embedding: Sequence[float], scope: dict[str, object], members: set[str]
    ) -> tuple[np.ndarray, list[Category | None], list[np.ndarray]] | None:
        """Re-normalised mean of the members' unit embeddings, their predicted categories and their
        vectors (None when no member vector is stored)."""
        if not members:
            return None
        found = self._vectors.search(
            "requests", embedding, k=SEARCH_K, min_sim=-1.0, filters={**scope, "with_embedding": True}
        )
        hits = [h for h in found if h.id in members and h.embedding is not None]
        if not hits:
            return None
        vectors = [_unit(np.asarray(h.embedding, dtype=np.float64)) for h in hits]
        categories = [_category(h.meta.get("category")) for h in hits]
        return _unit(np.mean(np.vstack(vectors), axis=0)), categories, vectors

    def _priority(self, priority: Priority, before: int, after: int) -> Priority:
        """Bump once, at the moment report_count first reaches bump_at."""
        return priority.bump() if before < self.bump_at <= after else priority


def majority(categories: Sequence[Category | None], prefer: Category) -> Category:
    """The most frequent category (D-017); a tie goes to `prefer` (the incident's current category,
    or the opening report's), then the label order, so the result is deterministic."""
    counts = Counter(c for c in categories if c is not None)
    if not counts:
        return prefer
    top = max(counts.values())
    tied = [c for c in CATEGORY_ORDER if counts.get(c) == top]
    return prefer if prefer in tied else tied[0]


def _category(value: object) -> Category | None:
    try:
        return Category(str(value)) if value else None
    except ValueError:
        return None


def _title(category: Category, building: str) -> str:
    return f"{category} reports in building {building}"


def _rank(p: Priority) -> int:
    return p.rank


def _unit(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 else v
