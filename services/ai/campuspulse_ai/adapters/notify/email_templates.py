"""Read the ticket email templates from `config/templates/email/` (P9.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.application.use_cases.ticket_emails import LANGS, TicketEmailTemplates


def load_ticket_email_templates(directory: Path) -> TicketEmailTemplates:
    """`ticket_emails.{en,ar}.yaml` + `layout.html` -> validated templates (`ValueError` names a bad key)."""
    parsed: dict[str, Any] = {}
    for lang in LANGS:
        parsed[lang] = yaml.safe_load((directory / f"ticket_emails.{lang}.yaml").read_text(encoding="utf-8"))
    layout = (directory / "layout.html").read_text(encoding="utf-8")
    return TicketEmailTemplates.from_dicts(parsed, layout)
