"""CounterfactualUseCase: the live "what if this word were gone?" check (SPEC §5.1 [10], P3.12)."""

from __future__ import annotations

from campuspulse_ai.application import dto
from campuspulse_ai.domain.errors import InvalidInput, NotFound, Unauthorized
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import Explainer, Repository


class CounterfactualUseCase:
    """`GET /v1/explain/{request_id}/counterfactual?drop=<token>`.

    `run(request_id, drop, caller_alias=None)`:
    1. loads the request (and, for a student caller, checks it is theirs: `caller_alias` must equal the
       request's alias);
    2. checks that `drop` occurs in the request text (case-insensitive), so the UI can only remove words
       the student actually wrote;
    3. reads the decided labels from the latest prediction;
    4. asks `Explainer.counterfactual(normalized request, drop)` for the labels without that token.

    Returns `CounterfactualResponse` with both label pairs, the new probabilities and `flipped`.
    Read-only: nothing is written.
    Errors: `NotFound` (unknown request, or no decision yet, 404); `Unauthorized` (another student's
    request, 403); `InvalidInput` (blank token, or not in the text, 422); `ArtifactError` from the
    explainer (503).
    """

    def __init__(self, explainer: Explainer, repo: Repository) -> None:
        self._explainer = explainer
        self._repo = repo

    def run(
        self, request_id: str, drop: str, *, caller_alias: str | None = None
    ) -> dto.CounterfactualResponse:
        request = self._repo.get_request(request_id)
        if caller_alias is not None and request.alias != caller_alias:
            raise Unauthorized(f"request {request_id} belongs to another student")
        token = drop.strip()
        normalized = request.normalized
        if normalized is None:
            raise NotFound(f"request {request_id} has no normalized text")
        texts = (request.raw_text, normalized.text_norm, normalized.model_text)
        if not token or not any(token.casefold() in t.casefold() for t in texts):
            raise InvalidInput(f"{drop!r} does not occur in the request text")
        pred = self._repo.latest_prediction(request_id)
        category, priority, p_cat, p_pri = self._explainer.counterfactual(normalized, token)
        return dto.CounterfactualResponse(
            request_id=request_id,
            drop=token,
            original_category=pred.category,
            original_priority=pred.priority,
            category=Category(category),
            priority=Priority(priority),
            category_prob=_clamp(p_cat.prob(str(category))),
            priority_prob=_clamp(p_pri.prob(str(priority))),
            flipped=(category, priority) != (pred.category, pred.priority),
        )


def _clamp(p: float) -> float:
    return min(max(p, 0.0), 1.0)
