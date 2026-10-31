"""Versioned prompt files (`config/prompts/<name>_<version>.md`).

Prompt text never lives in code. A prompt file is Markdown with YAML front matter:

    ---
    id: oracle                # prompt name
    version: v1               # a wording change needs a new version (and a new file)
    request: {temperature: 0, top_p: 1, seed: 42, max_tokens: 80}   # pinned request parameters
    limits: {max_reason_words: 20}                                   # output limits the code enforces
    ---
    # system
    ...system text with $placeholders...
    # user
    ...user text with $placeholders...

Placeholders use `string.Template` syntax (`$name`), so JSON braces in the text need no escaping; a
literal dollar sign is written `$$`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

import yaml

from campuspulse_ai.domain.errors import InvalidInput

_SECTIONS = ("system", "user")
_FRONT_MATTER = "---"


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A loaded prompt: its identity, the two message templates, request parameters and limits."""

    id: str
    version: str
    system: str
    user: str
    request: Mapping[str, object] = field(default_factory=dict)
    limits: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> PromptTemplate:
        """Parse a prompt file. Raises InvalidInput if it is missing or malformed."""
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidInput(f"cannot read prompt {p}: {exc}") from exc
        lines = text.splitlines()
        if not lines or lines[0].strip() != _FRONT_MATTER:
            raise InvalidInput(f"{p}: missing YAML front matter")
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == _FRONT_MATTER)
        except StopIteration:
            raise InvalidInput(f"{p}: unterminated YAML front matter") from None
        try:
            meta = yaml.safe_load("\n".join(lines[1:end])) or {}
        except yaml.YAMLError as exc:
            raise InvalidInput(f"{p}: bad front matter: {exc}") from exc
        if not isinstance(meta, dict):
            raise InvalidInput(f"{p}: front matter must be a mapping")
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for line in lines[end + 1 :]:
            heading = line.strip().lower()
            if heading.startswith("# ") and heading[2:] in _SECTIONS:
                current = heading[2:]
                sections[current] = []
            elif current is not None:
                sections[current].append(line)
        missing = [s for s in _SECTIONS if not "\n".join(sections.get(s, [])).strip()]
        if missing:
            raise InvalidInput(f"{p}: missing prompt sections {missing}")
        request = meta.get("request", {})
        limits = meta.get("limits", {})
        if not isinstance(request, dict) or not isinstance(limits, dict):
            raise InvalidInput(f"{p}: `request` and `limits` must be mappings")
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in limits.values()):
            raise InvalidInput(f"{p}: every limit must be a positive integer")
        pid, version = meta.get("id"), meta.get("version")
        if not isinstance(pid, str) or not isinstance(version, str) or not pid or not version:
            raise InvalidInput(f"{p}: front matter needs string `id` and `version`")
        return cls(
            id=pid,
            version=version,
            system="\n".join(sections["system"]).strip(),
            user="\n".join(sections["user"]).strip(),
            request=dict(request),
            limits={str(k): int(v) for k, v in limits.items()},
        )

    def limit(self, name: str) -> int:
        """A declared output limit. Raises InvalidInput if the prompt does not declare it."""
        try:
            return self.limits[name]
        except KeyError:
            raise InvalidInput(f"prompt {self.id}_{self.version} declares no limit {name!r}") from None

    def render(self, **values: str) -> list[dict[str, str]]:
        """The chat messages with every placeholder filled. Raises InvalidInput on a missing value."""
        try:
            return [
                {"role": "system", "content": Template(self.system).substitute(values)},
                {"role": "user", "content": Template(self.user).substitute(values)},
            ]
        except (KeyError, ValueError) as exc:
            raise InvalidInput(f"prompt {self.id}_{self.version}: missing or bad placeholder {exc}") from exc


def load_prompt(prompts_dir: str | Path, name: str, version: str) -> PromptTemplate:
    """Load `<prompts_dir>/<name>_<version>.md` and check its front matter matches. Raises InvalidInput."""
    prompt = PromptTemplate.load(Path(prompts_dir) / f"{name}_{version}.md")
    if prompt.id != name or prompt.version != version:
        raise InvalidInput(f"prompt file {name}_{version}.md declares {prompt.id}_{prompt.version}")
    return prompt
