"""`LifecycleReads` contract (P3.11, P4.10): InMemoryRepository always, SupabaseRepository with keys.

The reads feedback and Pulse need beyond the Repository port. Same harness (and per-run cleanup) as
`test_repository_contract.py`.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from campuspulse_ai.application.use_cases.ports import LifecycleReads
from campuspulse_ai.domain.entities import Incident, ReviewItem
from campuspulse_ai.domain.errors import NotFound
from campuspulse_ai.domain.labels import Category, Priority
from contracts import test_repository_contract as base
from contracts.test_repository_contract import (
    BUILDING,
    T0,
    Harness,
    make_prediction,
    make_request,
    make_ticket,
)

h = base.h  # the shared harness fixture (InMemory always; Supabase with keys), with its cleanup


def reads(h: Harness) -> LifecycleReads:
    assert isinstance(h.repo, LifecycleReads)
    return h.repo


def test_get_prediction_round_trip_and_not_found(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))
    got = reads(h).get_prediction(pred.id)
    assert (got.id, got.request_id, got.category) == (pred.id, req.id, pred.category)
    assert got.priority == pred.priority
    with pytest.raises(NotFound):
        reads(h).get_prediction(str(uuid.uuid4()))


def test_open_review_for_returns_the_oldest_open_item(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))
    assert reads(h).open_review_for(pred.id) is None
    first = h.repo.enqueue_review(ReviewItem("", pred.id, "needs_review", "open"))
    h.repo.enqueue_review(ReviewItem("", pred.id, "needs_review", "open"))
    got = reads(h).open_review_for(pred.id)
    assert got is not None and got.id == first.id and got.reason == "needs_review"
    h.repo.resolve_review(ReviewItem(first.id, pred.id, "needs_review", "corrected",
                                     corrected_category=Category.FINANCE))  # fmt: skip
    nxt = reads(h).open_review_for(pred.id)
    assert nxt is not None and nxt.id != first.id


def test_tickets_for_requests_lists_only_those_requests(h: Harness) -> None:
    a = h.repo.save_request(make_request(h))
    b = h.repo.save_request(make_request(h))
    other = h.repo.save_request(make_request(h))
    ta = h.repo.save_ticket(make_ticket(a.id, sla=T0 + timedelta(hours=1)))
    tb = h.repo.save_ticket(make_ticket(b.id, sla=T0 + timedelta(hours=2)))
    h.repo.save_ticket(make_ticket(other.id, sla=T0))
    got = reads(h).tickets_for_requests([a.id, b.id, a.id])
    assert sorted(t.id for t in got) == sorted([ta.id, tb.id])
    assert reads(h).tickets_for_requests([]) == []


def test_incidents_by_id_and_newest_first(h: Harness) -> None:
    def incident(hours: int, status: str) -> Incident:
        return h.repo.save_incident(Incident("", BUILDING, Category.IT_SUPPORT, f"t{hours}", Priority.MEDIUM,
                                             3, status, [], T0 + timedelta(hours=hours)))  # type: ignore[arg-type]  # fmt: skip

    old, new, closed = incident(0, "open"), incident(1, "open"), incident(2, "resolved")
    assert reads(h).get_incident(old.id).title == "t0"
    with pytest.raises(NotFound):
        reads(h).get_incident(str(uuid.uuid4()))
    mine = {old.id, new.id, closed.id}
    open_ids = [i.id for i in reads(h).list_incidents(open_only=True, limit=500) if i.id in mine]
    all_ids = [i.id for i in reads(h).list_incidents(open_only=False, limit=500) if i.id in mine]
    assert open_ids == [new.id, old.id] and all_ids == [closed.id, new.id, old.id]
