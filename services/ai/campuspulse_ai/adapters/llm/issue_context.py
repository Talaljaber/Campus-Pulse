"""Bounded, cached, language-independent issue preparation."""

import json
from collections.abc import Sequence

from campuspulse_ai.adapters.llm.cached_chat import CachedChat, prompt_hash
from campuspulse_ai.application.use_cases.chat_ports import Turn
from campuspulse_ai.application.use_cases.issue_context import PreparedIssue


class IssueContextLLM:
    def __init__(self, chat: CachedChat, prompt: str) -> None:
        self._chat = chat
        self._prompt = prompt

    def prepare(self, messages: Sequence[Turn], anchor: str) -> PreparedIssue | None:
        payload = json.dumps(
            {"anchor": anchor, "messages": [{"role": m.role, "content": m.content} for m in messages]},
            ensure_ascii=False,
        )
        raw = self._chat.ask(
            f"issue-context-v1:{prompt_hash(self._prompt)}",
            payload,
            [{"role": "system", "content": self._prompt}, {"role": "user", "content": payload}],
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(raw or "null")
            if not isinstance(data, dict):
                return None
            text = data.get("classifier_text")
            priority = data.get("priority_recommendation")
            evidence = data.get("priority_evidence", [])
            if not isinstance(text, str) or len(text) > 1000:
                return None
            if priority not in (None, "low", "medium", "high"):
                return None
            if not isinstance(evidence, list) or len(evidence) > 10:
                return None
            users = [m.content for m in messages if m.role == "user"]
            if any(
                not isinstance(e, str) or not e.strip() or not any(e in u for u in users) for e in evidence
            ):
                return None
            return PreparedIssue(text.strip(), priority if evidence else None, tuple(evidence))
        except (ValueError, TypeError):
            return None
