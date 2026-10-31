"""RunRedTeamUseCase: generate tricky requests, run the real pipeline, score, store (P4.11, §2.4).

Per run:
1. `RedTeamGenerator.generate(n, styles, seed)` (the rule-based `PerturbationGenerator`; the LLM
   generator is future work, UD-3, so `use_llm_generator=True` falls back to it with a log line).
2. Per item: `TriageClassifier.classify(text, memory=<memory>)` (batch semantics: no clarification,
   no LLM, no actions, no sinks, no notifier). The base text is classified once per distinct text.
3. Outcome: `distress` when the core flags it (the use case's [4'] step), else
   `DecisionPolicy.decide(core, one-question budget, llm_allowed=False)`.
4. `RedTeamJudge.score(item, core, outcome, base)`.
5. `Scorecard(by_style, by_lang, overall, failures, created_at, n, seed)` -> `Repository.save_redteam_run`
   (the repository assigns the run id).

Online the core runs with live memory ON so the demo shows learning; the offline CLI passes
`memory=False` and an `InMemoryRepository`.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from campuspulse_ai.application import dto
from campuspulse_ai.application.services.redteam_styles import DISTRESS_FLAG, FAKE_URGENCY, INJECTION
from campuspulse_ai.application.use_cases.ports import RedTeamJudge, TriageClassifier
from campuspulse_ai.application.use_cases.responses import decided_labels, scorecard_out
from campuspulse_ai.application.use_cases.triage import DEFAULT_MAX_QUESTIONS
from campuspulse_ai.domain.entities import CoreResult, RedTeamItem, Scorecard
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import Clock, DecisionPolicy, RedTeamGenerator, Repository
from campuspulse_ai.domain.values import ClarificationBudget, Outcome

log = logging.getLogger(__name__)

NO_DECISION = frozenset({Outcome.OUT_OF_SCOPE, Outcome.DISTRESS})
"""Outcomes without labels for the student; failures show `got_*` as null for them."""
PENDING_RUN_ID = ""
"""The repository replaces a non-UUID run id with a fresh UUID."""


@dataclass(frozen=True, slots=True)
class RedTeamResult:
    """One scored item. `category`/`priority` are the decided labels (None for `NO_DECISION`
    outcomes); `stable` says whether they equal the base text's (None without a base)."""

    item: RedTeamItem
    outcome: Outcome
    category: Category | None
    priority: Priority | None
    flags: frozenset[str]
    base_category: Category | None
    base_priority: Priority | None
    passed: bool
    reason: str

    @property
    def stable(self) -> bool | None:
        if self.base_category is None:
            return None
        return (self.category, self.priority) == (self.base_category, self.base_priority)

    def failure(self) -> dict[str, object]:
        """The `dto.RedTeamFailureOut` shape (JSON-safe values)."""
        return {
            "text": self.item.text,
            "style": self.item.style,
            "lang": self.item.lang.value,
            "intended_category": self.item.intended_category.value,
            "intended_priority": self.item.intended_priority.value,
            "got_category": self.category.value if self.category else None,
            "got_priority": self.priority.value if self.priority else None,
            "outcome": self.outcome.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RedTeamRun:
    """A stored scorecard plus every scored item (the CLI report and the failure candidates)."""

    scorecard: Scorecard
    results: tuple[RedTeamResult, ...]

    @property
    def label_stability(self) -> float | None:
        """Share of items with a base text whose decided labels equal the base's (any style)."""
        checked = [r.stable for r in self.results if r.stable is not None]
        return sum(checked) / len(checked) if checked else None

    @property
    def properties(self) -> Mapping[str, float | None]:
        """The three robustness properties: label stability, priority-gaming resistance (the
        fake_urgency pass rate) and injection resistance (the injection pass rate); None when the run
        had no such item."""
        return {
            "label_stability": self.label_stability,
            "priority_gaming_resistance": self.scorecard.by_style.get(FAKE_URGENCY),
            "injection_resistance": self.scorecard.by_style.get(INJECTION),
        }


class RunRedTeamUseCase:
    """`POST /v1/redteam/run` (admin) and the offline CLI (module docstring).

    - `run(n, styles, seed, use_llm_generator=False) -> Scorecard` (the stored scorecard).
    - `run_detailed(...) -> RedTeamRun` (the scorecard plus every item; the CLI writes it).
    - `api(cmd) -> dto.ScorecardOut` for the route.

    `styles` empty = every style the generator can feed. Errors: `InvalidInput` when `n` is outside
    `1..max_n` (Settings `REDTEAM_MAX_N`) or a style is unknown or cannot be fed (422);
    `ArtifactError` from the core (503); `StoreError` when the run cannot be saved (503).
    Writes one `redteam_runs` row; no tickets, notifications, LLM calls or memory writes.
    """

    def __init__(
        self,
        generator: RedTeamGenerator,
        core: TriageClassifier,
        policy: DecisionPolicy,
        judge: RedTeamJudge,
        repo: Repository,
        clock: Clock,
        *,
        max_n: int,
        memory: bool,
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        llm_generator: RedTeamGenerator | None = None,
    ) -> None:
        self._generator = generator
        self._core = core
        self._policy = policy
        self._judge = judge
        self._repo = repo
        self._clock = clock
        self._max_n = max_n
        self._memory = memory
        self._max_questions = max_questions
        self._llm_generator = llm_generator

    def api(self, cmd: dto.RedTeamRunRequest) -> dto.ScorecardOut:
        return scorecard_out(self.run(cmd.n, cmd.styles or (), cmd.seed))

    def run(self, n: int, styles: Sequence[str], seed: int, use_llm_generator: bool = False) -> Scorecard:
        return self.run_detailed(n, styles, seed, use_llm_generator).scorecard

    def run_detailed(
        self, n: int, styles: Sequence[str], seed: int, use_llm_generator: bool = False
    ) -> RedTeamRun:
        if not 1 <= n <= self._max_n:
            raise InvalidInput(f"n must be between 1 and {self._max_n}, got {n}")
        items = self._pick_generator(use_llm_generator).generate(n, styles, seed)
        bases: dict[str, CoreResult] = {}
        results = tuple(self._judge_one(item, bases) for item in items)
        scorecard = _scorecard(results, created_at=self._clock.now(), seed=seed)
        run_id = self._repo.save_redteam_run(scorecard)
        return RedTeamRun(dataclasses.replace(scorecard, run_id=run_id), results)

    def _pick_generator(self, use_llm_generator: bool) -> RedTeamGenerator:
        if not use_llm_generator:
            return self._generator
        if self._llm_generator is None:
            log.info("red team: the LLM generator is not wired (UD-3); using the rule-based one")
            return self._generator
        return self._llm_generator

    def _judge_one(self, item: RedTeamItem, bases: dict[str, CoreResult]) -> RedTeamResult:
        _, core = self._core.classify(item.text, memory=self._memory)
        base: CoreResult | None = None
        if item.base_text is not None:
            if item.base_text not in bases:
                bases[item.base_text] = self._core.classify(item.base_text, memory=self._memory)[1]
            base = bases[item.base_text]
        outcome = self._outcome(core)
        passed, reason = self._judge.score(item, core, outcome, base)
        category, priority = decided_labels(core)
        decided = outcome not in NO_DECISION
        base_category, base_priority = decided_labels(base) if base is not None else (None, None)
        return RedTeamResult(
            item=item,
            outcome=outcome,
            category=category if decided else None,
            priority=priority if decided else None,
            flags=core.flags,
            base_category=base_category,
            base_priority=base_priority,
            passed=passed,
            reason=reason,
        )

    def _outcome(self, core: CoreResult) -> Outcome:
        if DISTRESS_FLAG in core.flags:
            return Outcome.DISTRESS
        return self._policy.decide(core, ClarificationBudget(max_questions=self._max_questions), False)


def _scorecard(results: Sequence[RedTeamResult], *, created_at: datetime, seed: int) -> Scorecard:
    by_style: dict[str, list[bool]] = {}
    by_lang: dict[str, list[bool]] = {}
    for r in results:
        by_style.setdefault(r.item.style, []).append(r.passed)
        by_lang.setdefault(r.item.lang.value, []).append(r.passed)
    return Scorecard(
        run_id=PENDING_RUN_ID,
        by_style={k: _rate(v) for k, v in by_style.items()},
        by_lang={k: _rate(v) for k, v in by_lang.items()},
        overall=_rate([r.passed for r in results]),
        failures=[r.failure() for r in results if not r.passed],
        created_at=created_at,
        n=len(results),
        seed=seed,
    )


def _rate(passed: Sequence[bool]) -> float:
    return sum(passed) / len(passed) if passed else 0.0
