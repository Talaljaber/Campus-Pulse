"""UD-13 store contract: `ReviewReads` + `AdvisorDirectory` and the `ReviewItem` assignee/office (D-019).

InMemoryRepository always, SupabaseRepository with keys (`-m supabase`), on the shared harness of
`test_repository_contract.py`. Live, the student -> advisor link is the seeded demo
(`seed_demo_users.py`: `talal` -> Dr. Rana Haddad (fictional) -> login `advisor`, office `academic`);
in memory the same link is seeded here. Profiles need an auth user, so the tests never create one live.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.application.use_cases.ports import AdvisorDirectory, ReviewReads
from campuspulse_ai.domain.entities import ReviewItem
from campuspulse_ai.domain.errors import NotFound
from contracts import test_repository_contract as base
from contracts.test_repository_contract import Harness, make_prediction, make_request

h = base.h

DEMO_STUDENT = "talal"
DEMO_ADVISOR = "advisor"
DEMO_OFFICE = "academic"


@dataclass(frozen=True)
class Demo:
    advisor_profile: str
    advisor_id: str


def demo(h: Harness) -> Demo:
    """The demo student -> advisor link (seeded in memory; read live, skip if not seeded)."""
    repo = h.repo
    if isinstance(repo, InMemoryRepository):
        profile = repo.add_profile(DEMO_ADVISOR, "staff", DEMO_OFFICE)
        advisor = repo.add_advisor(
            "Dr. Test (fictional)", DEMO_OFFICE, "adv@example.invalid", profile_id=profile
        )
        repo.add_profile(DEMO_STUDENT, "student", advisor_id=advisor.id)
        return Demo(profile, advisor.id)
    directory = directory_of(h)
    contact = directory.advisor_of(DEMO_STUDENT)
    if contact is None:
        pytest.skip("demo users not seeded (run scripts/seed_demo_users.py)")
    return Demo(contact.profile_id, contact.advisor_id)


def reads(h: Harness) -> ReviewReads:
    assert isinstance(h.repo, ReviewReads)
    return h.repo


def directory_of(h: Harness) -> AdvisorDirectory:
    assert isinstance(h.repo, AdvisorDirectory)
    return h.repo


def test_assignee_and_office_round_trip(h: Harness) -> None:
    d = demo(h)
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))
    saved = h.repo.enqueue_review(
        ReviewItem("", pred.id, "needs_review", "open", assignee=d.advisor_profile, office=DEMO_OFFICE)
    )
    got = reads(h).get_review(saved.id)
    assert (got.assignee, got.office, got.status) == (d.advisor_profile, DEMO_OFFICE, "open")
    with pytest.raises(NotFound):
        reads(h).get_review(str(uuid.uuid4()))


def test_a_missing_office_is_filled_from_the_category(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))  # IT Support
    saved = h.repo.enqueue_review(ReviewItem("", pred.id, "needs_review", "open"))
    got = reads(h).get_review(saved.id)
    assert (got.office, got.assignee) == ("it", None)  # the 0012 trigger (modelled in memory)


def test_list_reviews_filters_by_status_and_office_newest_first(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))
    first = h.repo.enqueue_review(ReviewItem("", pred.id, "needs_review", "open", office=DEMO_OFFICE))
    second = h.repo.enqueue_review(ReviewItem("", pred.id, "needs_review", "open", office=DEMO_OFFICE))
    other = h.repo.enqueue_review(ReviewItem("", pred.id, "needs_review", "open", office="finance"))
    h.repo.resolve_review(ReviewItem(second.id, pred.id, "needs_review", "confirmed"))

    mine = {first.id, second.id, other.id}
    open_academic = [
        i.id for i in reads(h).list_reviews(status="open", office=DEMO_OFFICE, limit=200) if i.id in mine
    ]
    assert open_academic == [first.id]
    every = [i.id for i in reads(h).list_reviews(status=None, office=None, limit=200) if i.id in mine]
    assert set(every) == mine and every.index(other.id) < every.index(first.id)  # newest first


def test_batch_reads_skip_unknown_ids(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))
    unknown = str(uuid.uuid4())
    assert [p.id for p in reads(h).predictions_by_ids([pred.id, unknown, pred.id])] == [pred.id]
    assert [r.id for r in reads(h).requests_by_ids([req.id, unknown])] == [req.id]
    assert reads(h).predictions_by_ids([]) == [] and reads(h).requests_by_ids([]) == []


def test_advisor_of_follows_the_student_link(h: Harness) -> None:
    d = demo(h)
    contact = directory_of(h).advisor_of(DEMO_STUDENT)
    assert contact is not None
    assert (contact.profile_id, contact.advisor_id) == (d.advisor_profile, d.advisor_id)
    assert (contact.alias, contact.office) == (DEMO_ADVISOR, DEMO_OFFICE) and contact.email
    assert directory_of(h).advisor_of(f"{h.tag}-nobody") is None
    assert directory_of(h).advisor_of("  ") is None
    assert directory_of(h).profile_id_of(DEMO_ADVISOR) == d.advisor_profile
    assert directory_of(h).profile_id_of(f"{h.tag}-nobody") is None
