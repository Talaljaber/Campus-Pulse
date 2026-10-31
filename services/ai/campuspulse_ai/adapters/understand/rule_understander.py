"""`RuleBasedUnderstander`: the deterministic, offline understanding (UD-10 fallback, P3.3a).

Regex entities (`entities.py`) plus fixed templates from `config/templates/replies.{en,ar}.yaml`. It is
used when there is no key, when the LLM fails or is rejected, and for every injection-flagged request.
It never calls the network and never raises after construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from campuspulse_ai.adapters.understand.entities import extract_entities
from campuspulse_ai.adapters.understand.schema import UnderstandLimits, decided_labels
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.ports import Clock
from campuspulse_ai.domain.values import ActionType, Entities, Lang, NormalizedRequest, Understanding

NO_ACTION = "none"
_REPLY_KEYS = (*(a.value for a in ActionType), NO_ACTION)
_ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class LangTemplates:
    """The templates of one language file."""

    category_names: Mapping[str, str]
    priority_names: Mapping[str, str]
    teams: Mapping[str, str]
    summary: str
    reply: Mapping[str, str]
    deadline_today: str
    ticket_title: str | None = None
    ticket_body: str | None = None


def _mapping(raw: Mapping[str, object], key: str, keys: tuple[str, ...], where: str) -> dict[str, str]:
    value = raw.get(key)
    if not isinstance(value, dict) or any(
        not isinstance(value.get(k), str) or not value.get(k) for k in keys
    ):
        raise InvalidInput(f"{where}: `{key}` must map every one of {list(keys)} to text")
    return {k: str(value[k]) for k in keys}


def _load_lang(path: Path, *, needs_ticket: bool) -> LangTemplates:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidInput(f"cannot read reply templates {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidInput(f"{path}: expected a mapping")
    where = str(path)
    for key in ("summary", "deadline_today"):
        if not isinstance(raw.get(key), str):
            raise InvalidInput(f"{where}: `{key}` must be text")
    title = body = None
    if needs_ticket:
        ticket = _mapping(raw, "ticket", ("title", "body"), where)
        title, body = ticket["title"], ticket["body"]
    return LangTemplates(
        category_names=_mapping(raw, "category_names", CATEGORY_LABELS, where),
        priority_names=_mapping(raw, "priority_names", PRIORITY_LABELS, where),
        teams=_mapping(raw, "teams", CATEGORY_LABELS, where),
        summary=str(raw["summary"]),
        reply=_mapping(raw, "reply", _REPLY_KEYS, where),
        deadline_today=str(raw["deadline_today"]),
        ticket_title=title,
        ticket_body=body,
    )


@dataclass(frozen=True, slots=True)
class ReplyTemplates:
    """English and Arabic templates. Ticket title/body come from the English file (staff read them)."""

    en: LangTemplates
    ar: LangTemplates

    @classmethod
    def load(cls, templates_dir: str | Path) -> ReplyTemplates:
        """Load `replies.en.yaml` and `replies.ar.yaml`. Raises InvalidInput on a missing or bad file."""
        d = Path(templates_dir)
        return cls(
            en=_load_lang(d / "replies.en.yaml", needs_ticket=True),
            ar=_load_lang(d / "replies.ar.yaml", needs_ticket=False),
        )

    def for_lang(self, lang: Lang) -> LangTemplates:
        """English for English requests; Arabic (script) for Arabic and Arabizi requests."""
        return self.en if lang == Lang.EN else self.ar


def clip(text: str, limit: int) -> str:
    """`text` with collapsed whitespace, cut to `limit` characters with an ellipsis."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: max(limit - len(_ELLIPSIS), 0)].rstrip() + _ELLIPSIS


def _entity_lines(e: Entities) -> str:
    pairs = [
        ("Course", e.course_code),
        ("Building", e.building),
        ("Room", e.room),
        ("Deadline", e.deadline.isoformat() if e.deadline else None),
        ("System", e.system),
    ]
    found = [f"{name}: {value}." for name, value in pairs if value]
    return " ".join(found) if found else "No course, place, deadline or system was named."


class RuleBasedUnderstander:
    """Template understanding (implements `RequestUnderstander`; source "rules", prompt_version None).

    - entities: `extract_entities(req, clock.now().date())`;
    - summaries: the EN and AR `summary` templates over the decided labels and the request text;
    - student_reply: the request language's reply for `action_hint` (`none` when no action yet), plus the
      `deadline_today` sentence when the request names today;
    - ticket title/body: the English `ticket` templates.
    All texts are cut to the `UnderstandLimits`. The decided labels (`decided_labels(decided)`) are only
    read; `decided` is never modified.
    """

    def __init__(self, templates: ReplyTemplates, clock: Clock, limits: UnderstandLimits) -> None:
        self._t = templates
        self._clock = clock
        self._limits = limits

    def understand(
        self, req: NormalizedRequest, decided: CoreResult, action_hint: ActionType | None
    ) -> Understanding:
        cat, pri = decided_labels(decided)
        today = self._clock.now().date()
        entities = extract_entities(req, today)
        gist = " ".join(req.core.split())
        lim = self._limits

        def summary(t: LangTemplates) -> str:
            text = t.summary.format(
                category_name=t.category_names[cat], priority_name=t.priority_names[pri], gist=gist
            )
            return clip(text, lim.max_summary_chars)

        local = self._t.for_lang(req.lang)
        reply = local.reply[action_hint.value if action_hint else NO_ACTION].format(team=local.teams[cat])
        if entities.deadline == today:
            reply += local.deadline_today
        en = self._t.en
        fields = {
            "category": str(cat),
            "priority": str(pri),
            "gist": gist,
            "text": " ".join(req.core.split()),
            "lang": str(req.lang),
            "entity_lines": _entity_lines(entities),
        }
        return Understanding(
            summary_en=summary(en),
            summary_ar=summary(self._t.ar),
            entities=entities,
            student_reply=clip(reply, lim.max_reply_chars),
            ticket_title=clip(str(en.ticket_title).format(**fields), lim.max_title_chars),
            ticket_body=_clip_lines(str(en.ticket_body).format(**fields), lim.max_body_chars),
            source="rules",
            prompt_version=None,
        )


def _clip_lines(text: str, limit: int) -> str:
    """Like `clip` but keeps line breaks (ticket bodies are multi-line)."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    joined = "\n".join(line for line in lines if line)
    return joined if len(joined) <= limit else joined[: max(limit - len(_ELLIPSIS), 0)].rstrip() + _ELLIPSIS
