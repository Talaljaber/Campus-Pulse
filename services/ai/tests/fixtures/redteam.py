"""Red-team test helpers (P4.11): hand-made seed rows and a keyword-driven `TriageClassifier`.

- `ROWS`: eight labelled seed rows (EN and AR, five categories, all priorities).
- `KeywordCore`: classifies the generated texts by looking for a seed row's text inside them, with
  switches that make it fall for fake urgency (`gullible`) or miss injections (`blind`).
- `redteam_use_case(...)`: a `RunRedTeamUseCase` over these, the real scorer and an InMemoryRepository.
- `seed_csv(tmp_path)`: `ROWS` written as a seed CSV (for the CLI and composition tests).
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from campuspulse_ai.adapters.guards.bank import load_texts
from campuspulse_ai.adapters.redteam.config import RedTeamConfig
from campuspulse_ai.adapters.redteam.perturbation import PerturbationGenerator, SeedRow
from campuspulse_ai.adapters.redteam.scorer import RedTeamScorer
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.application.use_cases.run_redteam import RunRedTeamUseCase
from campuspulse_ai.config.paths import CONFIG_DIR, LEXICONS
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.values import ClarificationConstraint, Lang, Location, NormalizedRequest
from fixtures.backend_fakes import FrozenClock, make_core, make_request

ROWS: tuple[SeedRow, ...] = (
    SeedRow("TR-1", "The wifi in the library keeps dropping", Lang.EN, Category.IT_SUPPORT, Priority.MEDIUM),
    SeedRow("TR-2", "Where can I find the bus timetable for next week", Lang.EN, Category.TRANSPORTATION,
            Priority.LOW),
    SeedRow("TR-3", "I was charged twice for the summer course fees", Lang.EN, Category.FINANCE,
            Priority.MEDIUM),
    SeedRow("TR-4", "The projector in lecture room 204 is broken", Lang.EN, Category.FACILITIES,
            Priority.LOW),
    SeedRow("TR-5", "My registration was cancelled and the add-drop period closes tonight", Lang.EN,
            Category.REGISTRATION, Priority.HIGH),
    SeedRow("TR-6", "الانترنت بالمكتبة بقطع كل شوي", Lang.AR, Category.IT_SUPPORT, Priority.MEDIUM),
    SeedRow("TR-7", "وين بلاقي جدول الباصات", Lang.AR, Category.TRANSPORTATION, Priority.LOW),
    SeedRow("TR-8", "انخصم مني القسط مرتين", Lang.AR, Category.FINANCE, Priority.MEDIUM),
)  # fmt: skip

POLICY = DefaultDecisionPolicy(tau_ood=0.5)
MAX_N = 200


def redteam_config() -> RedTeamConfig:
    return RedTeamConfig.load(CONFIG_DIR / "redteam.yaml", LEXICONS)


def injection_exemplars() -> list[str]:
    return load_texts(LEXICONS / "injection.yaml", "exemplars")


@dataclass
class KeywordCore:
    """A `TriageClassifier` driven by the generated texts.

    - labels: those of the first seed row whose text appears in the input, else Academic Support/low;
      `gullible=True` lifts the priority to high on "!!" or "عاجل" (every fake-urgency prefix);
    - flags: `injection_attempt` when an injection exemplar appears (unless `blind`), `distress` for
      the distress list, `gibberish` (-> out_of_scope) for the off-topic list.
    """

    cfg: RedTeamConfig = field(default_factory=redteam_config)
    exemplars: Sequence[str] = field(default_factory=injection_exemplars)
    gullible: bool = False
    blind: bool = False
    calls: list[tuple[str, bool]] = field(default_factory=list)

    def classify(
        self,
        raw: str,
        picked_location: Location | None = None,
        constraints: Sequence[ClarificationConstraint] = (),
        memory: bool = True,
    ) -> tuple[NormalizedRequest, CoreResult]:
        self.calls.append((raw, memory))
        flags: set[str] = set()
        if not self.blind and any(e in raw for e in self.exemplars):
            flags.add("injection_attempt")
        if raw in {t.text for t in self.cfg.distress_adjacent}:
            flags.add("distress")
        if raw in {t.text for t in self.cfg.off_topic}:
            flags.add("gibberish")
        row = next((r for r in ROWS if r.text in raw), None)
        category = row.category if row else Category.ACADEMIC_SUPPORT
        priority = row.priority if row else Priority.LOW
        if self.gullible and ("!!" in raw or "عاجل" in raw):
            priority = Priority.HIGH
        core = make_core({category.value: 0.9}, {priority.value: 0.9}, flags=frozenset(flags))
        return make_request(raw), core


def redteam_use_case(
    core: KeywordCore | None = None,
    *,
    repo: InMemoryRepository | None = None,
    memory: bool = False,
    clock: FrozenClock | None = None,
) -> RunRedTeamUseCase:
    clock = clock or FrozenClock()
    core = core or KeywordCore()
    return RunRedTeamUseCase(
        PerturbationGenerator(ROWS, core.cfg),
        core,
        POLICY,
        RedTeamScorer(),
        repo or InMemoryRepository(clock),
        clock,
        max_n=MAX_N,
        memory=memory,
    )


def seed_csv(directory: Path) -> Path:
    """`ROWS` as a seed CSV with the `data/clean` columns that matter."""
    path = directory / "seeds.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["request_id", "core", "lang", "category", "priority"])
        writer.writerows(
            [r.request_id, r.text, r.lang.value, r.category.value, r.priority.value] for r in ROWS
        )
    return path
