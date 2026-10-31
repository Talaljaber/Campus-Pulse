#!/usr/bin/env python3
"""Draft augmentation rows (P1.9: rule-based Arabizi; P2.2: LLM paraphrases and new scenarios).

    python scripts/draft_augmentation.py arabizi-rule --out data/augmented/arabizi.csv [--force]
    python scripts/draft_augmentation.py paraphrase [--model <pinned id>] [--per-scenario 3]
                                                    [--out data/augmented/paraphrases.csv] [--dry-run]
    python scripts/draft_augmentation.py new-scenarios [--model <pinned id>] [--plan config/datasets.yaml]
                                                       [--out data/augmented/new_scenarios.csv] [--dry-run]
    python scripts/draft_augmentation.py prune --report reports/leakage.json <csv> [<csv> ...]

**arabizi-rule** reverse-transliterates every official Arabic scenario core into
`augmented.arabizi_variants` (config/datasets.yaml) Arabizi spellings, offline and deterministic:
  1. per Arabic token: a reverse-lexicon hit (`config/lexicons/arabizi.yaml lexicon`, reversed; spelling
     chosen by the variant), else a known proclitic (و, ب, ال, بال, لل, وال ...) + a lexicon word
     (`bel mamar`, `w 3indi`), else a character-level reverse map (variant 0 uses digits 7/5/3/2/6/9,
     variant 1 letters kh/gh/g where the convention allows);
  2. rows copy labels and `cv_group` from the source scenario, with `source=arabizi_rule`,
     `author_method=rule`, `lang=arabizi`, `needs_human_check=True`.
It refuses to overwrite a file that already holds reviewed rows unless `--force` is given.

**paraphrase** asks the pinned OpenRouter model for `augmented.paraphrase.forms` versions of every official
scenario core (same language, the other language, Jordanian Arabizi). Rows inherit the scenario's labels and
`cv_group` (a translation shares its group, ARCHITECTURE §3.2), `source=llm_paraphrase` (`llm_arabizi` for
the Arabizi form), `author_method=llm:<model>`.

**new-scenarios** asks for new situations per (category, priority) cell (`augmented.new_scenarios`): an
EN and an AR form each, plus Arabizi for one scenario in `arabizi_every`. Each scenario gets its own group
`NEW-Sxx` shared by its forms, `source=new_scenario`. The cell's labels are the LLM's *suggestion*: the
developer confirms or fixes them in the P2.4 review. A scenario the model marks `fits_label=false` is
skipped and logged. The prompt lists the official cores of the category as "already covered"; it never sees
`data/our_test` or `data/robustness`.

Every LLM row is `needs_human_check=True`, so `load_pool` never trains on it before the review. Every call
uses the pinned model id and request parameters (temperature 0, top_p 1, seed 42), JSON structured output,
and an on-disk cache (table `augmented.drafting.cache_table` in `Settings.llm_cache_path`, key
sha256(model | prompt version | system | user)), so re-running costs nothing and gives the same rows. Real
calls are appended to `data/augmented/draft_log.jsonl` with their cost (OpenRouter `usage.cost`, else the
price table). Errors: schema-invalid JSON -> one retry, then the item is skipped and logged; spend reaching
`LLM_DAILY_BUDGET_USD` (today's logged spend + this run) -> stop with a message (exit 5); no
`OPENROUTER_API_KEY` -> exit 3. The key is read from the environment or `--env-file` and never printed.
`--dry-run` prints the number of calls and an upper cost estimate without calling anything.

**prune** removes LLM-drafted rows (never rule or hand rows) that `scripts/check_leakage.py` lists against a
holdout (failing or encoder-only), plus drafted rows whose normalized text equals an official text of
another group; for a new scenario every form goes. It reads only the leakage report, never a holdout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.adapters.preprocess.langid import LangIdentifier
from campuspulse_ai.adapters.preprocess.wrappers import normalize_text
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.values import Lang

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "data" / "clean" / "scenarios.csv"
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
ARABIZI_YAML = ROOT / "config" / "lexicons" / "arabizi.yaml"
DATASETS_YAML = ROOT / "config" / "datasets.yaml"
ID_PREFIX = "AUG-AZ-"
SOURCE = "arabizi_rule"
SOURCE_PARAPHRASE, SOURCE_LLM_ARABIZI, SOURCE_NEW = "llm_paraphrase", "llm_arabizi", "new_scenario"
EXIT_OK, EXIT_ERROR, EXIT_NO_KEY, EXIT_BUDGET = 0, 1, 3, 5
CHARS_PER_TOKEN = 3.0  # conservative (Arabic tokenizes densely): only for the --dry-run upper estimate
LANG_NAMES = {"en": "English", "ar": "Jordanian Arabic (Arabic script)"}

# Reverse proclitics, longest first: Arabic prefix -> Arabizi tokens (written before the word).
PROCLITICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("وبال", ("w", "bel")), ("وال", ("w", "el")), ("بال", ("bel",)), ("فال", ("fel",)), ("لل", ("lal",)),
    ("ال", ("el",)), ("و", ("w",)), ("ب", ("b",)),
)
MIN_STEM = 2  # a proclitic is split off only if at least this many letters remain
ARTICLE = "ال"

# Character-level reverse map; a tuple gives (variant 0, variant 1) spellings.
CHARMAP_REV: Mapping[str, tuple[str, str]] = {
    "ا": ("a", "a"), "ب": ("b", "b"), "ت": ("t", "t"), "ث": ("th", "s"), "ج": ("j", "j"), "ح": ("7", "7"),
    "خ": ("5", "kh"), "د": ("d", "d"), "ذ": ("th", "z"), "ر": ("r", "r"), "ز": ("z", "z"), "س": ("s", "s"),
    "ش": ("sh", "sh"), "ص": ("9", "s"), "ض": ("d", "d"), "ط": ("6", "t"), "ظ": ("th", "z"), "ع": ("3", "3"),
    "غ": ("gh", "3'"), "ف": ("f", "f"), "ق": ("2", "g"), "ك": ("k", "k"), "ل": ("l", "l"), "م": ("m", "m"),
    "ن": ("n", "n"), "ه": ("h", "h"), "و": ("w", "w"), "ي": ("y", "y"), "ء": ("2", "2"),
}
FINAL_HEH: tuple[str, str] = ("a", "e")  # word-final ه (from ة) is a vowel in Arabizi: jam3a / jam3e
MEDIAL_VOWEL: Mapping[str, tuple[str, str]] = {"و": ("o", "u"), "ي": ("i", "ee"), "ا": ("a", "a")}

COLUMNS = ("request_id", "text", "lang", "source", "source_scenario_id", "cv_group", "needs_human_check",
           "author_method", "category", "priority")


# --- arabizi-rule (P1.9) ----------------------------------------------------------------------------------


def build_reverse_lexicon(lexicon: Mapping[str, str]) -> dict[str, list[str]]:
    """Arabic (normalized like text_norm) -> Arabizi spellings, in lexicon order.

    English loanwords spelled in Latin (`bus`, `exam`, `online`) are kept: students write them that way.
    """
    rev: dict[str, list[str]] = {}
    for arabizi, arabic in lexicon.items():
        rev.setdefault(normalize_text(str(arabic), "ar"), []).append(str(arabizi))
    return rev


def _chars(word: str, charmap_rev: Mapping[str, tuple[str, str]], variant: int) -> str:
    out: list[str] = []
    for i, ch in enumerate(word):
        last = i == len(word) - 1
        if last and ch == "ه" and i > 0:
            out.append(FINAL_HEH[variant])
        elif i > 0 and ch in MEDIAL_VOWEL:
            out.append(MEDIAL_VOWEL[ch][variant])
        else:
            out.append(charmap_rev.get(ch, (ch, ch))[variant])
    return "".join(out)


def _pick(spellings: Sequence[str], variant: int) -> str:
    return spellings[min(variant, len(spellings) - 1)]


def reverse_transliterate(arabic: str, lexicon_rev: Mapping[str, Sequence[str]],
                          charmap_rev: Mapping[str, tuple[str, str]], variant: int) -> str:
    """One Arabizi spelling of an Arabic text (see the module docstring); `variant` is 0 or 1."""
    tokens: list[str] = []
    for word in normalize_text(arabic, "ar").split():
        if word in lexicon_rev:
            tokens.append(_pick(lexicon_rev[word], variant))
            continue
        for prefix, latin in PROCLITICS:
            stem = word[len(prefix):]
            if not word.startswith(prefix) or len(stem) < MIN_STEM:
                continue
            if stem in lexicon_rev:
                tokens.extend([*latin, _pick(lexicon_rev[stem], variant)])
                break
            if ARTICLE in prefix:  # the article is always a proclitic; و/ب may be root letters
                tokens.extend([*latin, _chars(stem, charmap_rev, variant)])
                break
        else:
            tokens.append(_chars(word, charmap_rev, variant))
    return " ".join(tokens)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _write_rows(out: Path, rows: Sequence[Mapping[str, str]]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _refuse_reviewed(out: Path, force: bool) -> bool:
    """True (and a message) when `out` holds reviewed rows and `force` is not set."""
    if out.is_file() and not force:
        reviewed = [r["request_id"] for r in _read_csv(out)
                    if r["needs_human_check"].strip().lower() == "false"]
        if reviewed:
            print(f"refusing to overwrite {out}: {len(reviewed)} reviewed rows (use --force)",
                  file=sys.stderr)
            return True
    return False


def arabizi_rule(out: Path, force: bool) -> int:
    if _refuse_reviewed(out, force):
        return EXIT_ERROR
    cfg = yaml.safe_load(ARABIZI_YAML.read_text(encoding="utf-8"))
    variants = int(yaml.safe_load(DATASETS_YAML.read_text(encoding="utf-8"))["augmented"]["arabizi_variants"])
    lexicon_rev = build_reverse_lexicon(cfg["lexicon"])
    group_of = {r["scenario_id"]: r["cv_group"] for r in _read_csv(COMBINED)}
    scenarios = [r for r in _read_csv(SCENARIOS) if r["lang"] == "ar"]
    langid = LangIdentifier.from_yaml(ARABIZI_YAML)
    rows: list[dict[str, str]] = []
    for sc in sorted(scenarios, key=lambda r: r["scenario_id"]):
        seen: set[str] = set()
        for variant in range(variants):
            text = reverse_transliterate(sc["core"], lexicon_rev, CHARMAP_REV, variant)
            if text in seen:
                continue
            seen.add(text)
            rows.append({"request_id": f"{ID_PREFIX}{len(rows) + 1:04d}", "text": text, "lang": "arabizi",
                         "source": SOURCE, "source_scenario_id": sc["scenario_id"],
                         "cv_group": group_of[sc["scenario_id"]], "needs_human_check": "True",
                         "author_method": "rule", "category": sc["category"], "priority": sc["priority"]})
    _write_rows(out, rows)
    detected = sum(langid.identify(r["text"]) is Lang.ARABIZI for r in rows)
    print(f"wrote {out}: {len(rows)} rows from {len(scenarios)} Arabic scenarios x {variants} variants; "
          f"LangIdentifier detects {detected}/{len(rows)} as arabizi; "
          "needs_human_check=True (review pending)")
    return EXIT_OK


# --- the LLM client: pinned, temperature 0, cached, costed (P2.2) ------------------------------------------


class BudgetExceeded(RuntimeError):
    """Spending one more call would pass `LLM_DAILY_BUDGET_USD`."""


class SchemaInvalid(ValueError):
    """The model's reply is not JSON matching the requested schema."""


@dataclass(frozen=True)
class DraftResponse:
    """One parsed JSON reply and its accounting (`cached` replies cost 0)."""

    data: Mapping[str, Any]
    key: str
    cached: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float


@dataclass(frozen=True)
class Prompt:
    """A versioned prompt file (`scripts/prompts/<name>.md`): `version:` line, `## system`, `## user`."""

    version: str
    system: str
    user: str

    @classmethod
    def load(cls, path: Path) -> Prompt:
        text = path.read_text(encoding="utf-8")
        version = re.search(r"^version:\s*(\S+)", text, re.M)
        parts = re.split(r"^## (system|user)\s*$", text, flags=re.M)
        sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
        if version is None or set(sections) != {"system", "user"}:
            raise ValueError(f"{path}: needs a `version:` line and `## system` / `## user` sections")
        return cls(version.group(1), sections["system"], sections["user"])


def cache_key(model: str, prompt_version: str, system: str, user: str) -> str:
    return hashlib.sha256("\x1f".join((model, prompt_version, system, user)).encode("utf-8")).hexdigest()


class DraftCache:
    """SQLite cache of raw replies (one table in the shared LLM cache file)."""

    def __init__(self, path: Path, table: str) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError(f"bad cache table name {table!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._table = table
        self._db.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, model TEXT, "
                         "content TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, "
                         "created_at TEXT)")

    def get(self, key: str) -> str | None:
        row = self._db.execute(f"SELECT content FROM {self._table} WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def put(self, key: str, model: str, content: str, tokens_in: int, tokens_out: int, cost: float) -> None:
        self._db.execute(f"INSERT OR REPLACE INTO {self._table} VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (key, model, content, tokens_in, tokens_out, cost,
                          datetime.now(UTC).isoformat(timespec="seconds")))
        self._db.commit()

    def close(self) -> None:
        self._db.close()


def validate_json(content: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    """Parse `content` and check it against a (small) JSON schema: object/array/string/boolean, required
    keys, no extra keys, non-empty strings unless `"minLength": 0`. Raises SchemaInvalid."""
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise SchemaInvalid(f"not JSON: {exc}") from exc

    def check(value: Any, sch: Mapping[str, Any], where: str) -> None:
        kind = sch["type"]
        if kind == "object":
            if not isinstance(value, dict):
                raise SchemaInvalid(f"{where}: expected an object")
            props: Mapping[str, Any] = sch["properties"]
            missing = [k for k in sch.get("required", props) if k not in value]
            extra = [k for k in value if k not in props]
            if missing or extra:
                raise SchemaInvalid(f"{where}: missing {missing}, unexpected {extra}")
            for k, sub in props.items():
                if k in value:
                    check(value[k], sub, f"{where}.{k}")
        elif kind == "array":
            if not isinstance(value, list) or len(value) < int(sch.get("minItems", 0)):
                raise SchemaInvalid(f"{where}: expected an array of >= {sch.get('minItems', 0)} items")
            for i, item in enumerate(value):
                check(item, sch["items"], f"{where}[{i}]")
        elif kind == "string":
            if not isinstance(value, str) or len(value.strip()) < int(sch.get("minLength", 1)):
                raise SchemaInvalid(f"{where}: expected a non-empty string")
            if "enum" in sch and value not in sch["enum"]:
                raise SchemaInvalid(f"{where}: {value!r} not in {sch['enum']}")
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise SchemaInvalid(f"{where}: expected a boolean")
        else:
            raise SchemaInvalid(f"{where}: unsupported schema type {kind!r}")

    check(data, schema, "$")
    return dict(data)


def _response_format(name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    def strict(sch: Mapping[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in sch.items() if k not in ("minLength", "minItems")}
        if sch["type"] == "object":
            out["properties"] = {k: strict(v) for k, v in sch["properties"].items()}
            out["required"] = list(sch["properties"])
            out["additionalProperties"] = False
        if sch["type"] == "array":
            out["items"] = strict(sch["items"])
        return out

    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": strict(schema)}}


class Drafter:
    """Calls the pinned model through `OpenRouterClient` with the cache, the budget and the cost log.

    `client_factory` builds the client lazily (only on a cache miss), so a fully cached run needs no key
    and makes no HTTP call. `spent_today` is the logged spend of the current UTC day before this run.
    """

    def __init__(self, *, model: str, params: Mapping[str, Any], cache: DraftCache, budget_usd: float,
                 spent_today: float, log_path: Path, retries: int,
                 client_factory: Callable[[], Any]) -> None:
        self.model, self.params, self.cache = model, dict(params), cache
        self.budget_usd, self.spent = budget_usd, spent_today
        self.run_cost, self.calls, self.cache_hits = 0.0, 0, 0
        self._log_path, self._retries, self._factory = log_path, retries, client_factory
        self._client: Any = None

    def _chat(self, system: str, user: str, response_format: Mapping[str, Any]
              ) -> tuple[str, int, int, float]:
        from campuspulse_ai.adapters.llm.cost import estimate_cost

        if self.spent >= self.budget_usd:
            raise BudgetExceeded(f"spend {self.spent:.4f} USD has reached LLM_DAILY_BUDGET_USD "
                                 f"{self.budget_usd:.2f}; stopping")
        if self._client is None:
            self._client = self._factory()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        result = self._client.chat(self.model, messages, params=self.params, response_format=response_format)
        cost = (float(result.cost_usd) if result.cost_usd is not None
                else estimate_cost(self.model, result.tokens_in, result.tokens_out))
        self.spent += cost
        self.run_cost += cost
        self.calls += 1
        return str(result.content), int(result.tokens_in), int(result.tokens_out), cost

    def call(self, prompt_version: str, system: str, user: str, schema: Mapping[str, Any], *,
             schema_name: str, item: str, cmd: str) -> DraftResponse | None:
        """One JSON reply (cached when possible), or None when it stayed schema-invalid after the retries."""
        key = cache_key(self.model, prompt_version, system, user)
        hit = self.cache.get(key)
        if hit is not None:
            try:
                data = validate_json(hit, schema)
                self.cache_hits += 1
                return DraftResponse(data, key, True, 0, 0, 0.0)
            except SchemaInvalid:
                pass  # a stale invalid entry: ask again
        fmt = _response_format(schema_name, schema)
        for attempt in range(self._retries + 1):
            content, t_in, t_out, cost = self._chat(system, user, fmt)
            try:
                data = validate_json(content, schema)
            except SchemaInvalid as exc:
                self._log({"cmd": cmd, "item": item, "key": key, "attempt": attempt, "status": "invalid",
                           "error": str(exc)[:200], "tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost})
                continue
            self.cache.put(key, self.model, content, t_in, t_out, cost)
            self._log({"cmd": cmd, "item": item, "key": key, "attempt": attempt, "status": "ok",
                       "tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost})
            return DraftResponse(data, key, False, t_in, t_out, cost)
        return None

    def _log(self, entry: Mapping[str, Any]) -> None:
        record = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "model": self.model, **entry}
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


def spent_today(log_path: Path, day: str | None = None) -> float:
    """USD of the calls logged on `day` (UTC date, default today) in the draft log."""
    if not log_path.is_file():
        return 0.0
    day = day or datetime.now(UTC).date().isoformat()
    total = 0.0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if str(rec.get("ts", "")).startswith(day):
                total += float(rec.get("cost_usd", 0.0))
    return total


# --- the two drafting modes ---------------------------------------------------------------------------------


PARAPHRASE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"same_lang": {"type": "string"}, "other_lang": {"type": "string"},
                   "arabizi": {"type": "string"}, "label_facts": {"type": "string"}},
}
NEW_SCENARIOS_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"scenarios": {"type": "array", "minItems": 1, "items": {
        "type": "object",
        "properties": {"en": {"type": "string"}, "ar": {"type": "string"},
                       "arabizi": {"type": "string", "minLength": 0},
                       "fits_label": {"type": "boolean"}, "why": {"type": "string", "minLength": 0}},
    }}},
}
TRANSLATE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"translation": {"type": "string"}, "arabizi": {"type": "string"}},
}
PRECHECK_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"items": {"type": "array", "minItems": 1, "items": {
        "type": "object",
        "properties": {"id": {"type": "string"},
                       "category": {"type": "string", "enum": list(CATEGORY_LABELS)},
                       "priority": {"type": "string", "enum": list(PRIORITY_LABELS)},
                       "natural": {"type": "boolean"}},
    }}},
}
SHORTCUT_HIGH = ("At least one of your situations must be high WITHOUT the words \"today\", \"اليوم\" or "
                 "\"elyom\" (for example an exam happening right now, students stuck somewhere, a danger).")
SHORTCUT_OTHER = ("At least one of your situations must mention \"today\" / \"اليوم\" naturally while "
                  "staying {priority} (for example a question about today's timetable or a minor fault "
                  "noticed today).")


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    lang: str
    core: str
    category: str
    priority: str
    cv_group: str
    translation: str  # the core of the official translation, "" if none


def official_scenarios() -> list[Scenario]:
    """The 42 official scenarios with their cv_group and translation core, sorted by id."""
    group_of = {r["scenario_id"]: r["cv_group"] for r in _read_csv(COMBINED)}
    rows = _read_csv(SCENARIOS)
    core_of = {r["scenario_id"]: r["core"] for r in rows}
    return [Scenario(r["scenario_id"], r["lang"], r["core"], r["category"], r["priority"],
                     group_of[r["scenario_id"]], core_of.get(r["translation_of"], ""))
            for r in sorted(rows, key=lambda r: r["scenario_id"])]


def _row(rid: str, text: str, lang: str, source: str, sid: str, group: str, method: str, cat: str,
         pri: str) -> dict[str, str]:
    return {"request_id": rid, "text": " ".join(text.split()), "lang": lang, "source": source,
            "source_scenario_id": sid, "cv_group": group, "needs_human_check": "True",
            "author_method": method, "category": cat, "priority": pri}


def paraphrase_requests(prompt: Prompt, scenarios: Sequence[Scenario]) -> list[tuple[Scenario, str]]:
    out = []
    for sc in scenarios:
        other = "ar" if sc.lang == "en" else "en"
        line = (f"Its official {LANG_NAMES[other].split(' (')[0]} version: {sc.translation}" if sc.translation
                else "")
        out.append((sc, prompt.user.format(lang=sc.lang, core=sc.core, category=sc.category,
                                           priority=sc.priority, translation_line=line,
                                           same_lang_name=LANG_NAMES[sc.lang],
                                           other_lang_name=LANG_NAMES[other])))
    return out


def paraphrase_rows(drafter: Drafter, prompt: Prompt, scenarios: Sequence[Scenario], forms: Sequence[str],
                    id_prefix: str) -> tuple[list[dict[str, str]], list[str]]:
    """Rows for every scenario and form, in scenario then form order; and the skipped scenario ids."""
    rows: list[dict[str, str]] = []
    skipped: list[str] = []
    method = f"llm:{drafter.model}"
    for sc, user in paraphrase_requests(prompt, scenarios):
        resp = drafter.call(prompt.version, prompt.system, user, PARAPHRASE_SCHEMA, schema_name="paraphrase",
                            item=sc.scenario_id, cmd="paraphrase")
        if resp is None:
            skipped.append(sc.scenario_id)
            continue
        for form in forms:
            lang = sc.lang if form == "same_lang" else ("arabizi" if form == "arabizi" else
                                                        ("ar" if sc.lang == "en" else "en"))
            source = SOURCE_LLM_ARABIZI if lang == "arabizi" else SOURCE_PARAPHRASE
            rows.append(_row(f"{id_prefix}{len(rows) + 1:04d}", str(resp.data[form]), lang, source,
                             sc.scenario_id, sc.cv_group, method, sc.category, sc.priority))
    return rows, skipped


def cell_plan(cfg: Mapping[str, Any]) -> list[tuple[str, str, int]]:
    """(category, priority, n scenarios) per cell, in official label order; sums to `target`."""
    extra: Mapping[str, int] = cfg.get("extra_per_cell", {})
    plan = [(c, p, int(cfg["per_cell_min"]) + int(extra.get(f"{c}|{p}", 0)))
            for c in CATEGORY_LABELS for p in PRIORITY_LABELS]
    total = sum(n for _, _, n in plan)
    if total != int(cfg["target"]):
        raise ValueError(f"augmented.new_scenarios: cells sum to {total}, target is {cfg['target']}")
    return plan


def new_scenario_requests(prompt: Prompt, scenarios: Sequence[Scenario], cfg: Mapping[str, Any]
                          ) -> list[tuple[str, str, int, list[int], str]]:
    """(category, priority, n, arabizi positions (1-based), user prompt) per cell."""
    every = int(cfg["arabizi_every"])
    out = []
    for cat, pri, n in cell_plan(cfg):
        covered = "\n".join(f"- {s.core}" for s in scenarios if s.category == cat)
        positions = [i for i in range(1, n + 1) if (i - 1) % every == 0]
        out.append((cat, pri, n, positions, prompt.user.format(
            category=cat, priority=pri, n=n, arabizi_positions=", ".join(map(str, positions)),
            covered=covered)))
    return out


def new_scenario_rows(drafter: Drafter, prompt: Prompt, scenarios: Sequence[Scenario],
                      cfg: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    """Rows of every accepted scenario (EN, AR, and Arabizi where asked); and skipped items."""
    rows: list[dict[str, str]] = []
    skipped: list[str] = []
    method = f"llm:{drafter.model}"
    n_scen = 0
    for cat, pri, n, positions, user in new_scenario_requests(prompt, scenarios, cfg):
        rule = SHORTCUT_HIGH if pri == "high" else SHORTCUT_OTHER.format(priority=pri)
        system = prompt.system.replace("{shortcut_rule}", rule)
        resp = drafter.call(prompt.version, system, user, NEW_SCENARIOS_SCHEMA, schema_name="new_scenarios",
                            item=f"{cat}|{pri}", cmd="new-scenarios")
        if resp is None:
            skipped.append(f"{cat}|{pri}: invalid JSON")
            continue
        for i, sc in enumerate(resp.data["scenarios"][:n], start=1):
            if not sc["fits_label"]:
                skipped.append(f"{cat}|{pri} #{i}: model says it does not fit ({sc['why'][:80]})")
                continue
            n_scen += 1
            group = f"{cfg['group_prefix']}{n_scen:02d}"
            forms = [("en", sc["en"]), ("ar", sc["ar"])]
            if i in positions and sc["arabizi"].strip():
                forms.append(("arabizi", sc["arabizi"]))
            for lang, text in forms:
                rows.append(_row(f"{cfg['id_prefix']}{len(rows) + 1:04d}", text, lang, SOURCE_NEW, group,
                                 group, method, cat, pri))
    return rows, skipped


def translate_requests(prompt: Prompt, scenarios: Sequence[Scenario]) -> list[tuple[Scenario, str]]:
    out = []
    for sc in scenarios:
        other = "ar" if sc.lang == "en" else "en"
        out.append((sc, prompt.user.format(lang=sc.lang, core=sc.core, other_lang_name=LANG_NAMES[other])))
    return out


def translate_rows(drafter: Drafter, prompt: Prompt, scenarios: Sequence[Scenario], id_prefix: str
                   ) -> tuple[list[dict[str, str]], list[str]]:
    """D-014 translation rows (`source=llm_translate`, the scenario's labels and cv_group).

    The translation is kept only when the scenario has no official translation (else it nearly copies an
    official row of the same group). The Arabizi form is kept once per group's Arabic side: for an Arabic
    scenario, and for an English scenario without an official Arabic translation.
    """
    rows: list[dict[str, str]] = []
    skipped: list[str] = []
    method = f"llm:{drafter.model}"
    for sc, user in translate_requests(prompt, scenarios):
        resp = drafter.call(prompt.version, prompt.system, user, TRANSLATE_SCHEMA, schema_name="translate",
                            item=sc.scenario_id, cmd="translate")
        if resp is None:
            skipped.append(sc.scenario_id)
            continue
        forms: list[tuple[str, str]] = []
        if not sc.translation:
            forms.append(("ar" if sc.lang == "en" else "en", str(resp.data["translation"])))
        if sc.lang == "ar" or not sc.translation:
            forms.append(("arabizi", str(resp.data["arabizi"])))
        for lang, text in forms:
            rows.append(_row(f"{id_prefix}{len(rows) + 1:04d}", text, lang, "llm_translate", sc.scenario_id,
                             sc.cv_group, method, sc.category, sc.priority))
    return rows, skipped


# --- precheck: an independent LLM labels every drafted row (D-014) ----------------------------------------

SHEET_COLUMNS = ("file", "request_id", "text", "lang", "source", "draft_category", "draft_priority",
                 "check_category", "check_priority", "check_natural", "agree", "read_in_full",
                 "human_verdict", "human_category", "human_priority", "human_text", "notes")
VERDICTS = ("ok", "fix", "drop")


def _sample(ids: Sequence[str], share: float, seed: int) -> set[str]:
    """A seeded, order-independent sample: the `share` of ids with the smallest sha256(seed|id)."""
    ranked = sorted(ids, key=lambda i: hashlib.sha256(f"{seed}|{i}".encode()).hexdigest())
    k = int(round(share * len(ranked)))
    return set(ranked[:k])


def precheck_sheet(drafter: Drafter, prompt: Prompt, files: Sequence[Path], cfg: Mapping[str, Any]
                   ) -> tuple[list[dict[str, str]], list[str]]:
    """Review-sheet rows: every LLM-drafted row with the checker's labels and whether it agrees.

    `read_in_full` is True for every disagreement (category, priority or `natural=false`), for every row
    the checker could not label, and for a seeded `sample_agreements` share of the agreements. The sheet
    never changes the augmentation files; `needs_human_check` stays True until `apply-review`.
    """
    drafted: list[tuple[str, dict[str, str]]] = []
    for path in files:
        for r in _read_csv(path):
            if r["author_method"].startswith("llm"):
                drafted.append((path.name, r))
    labels: dict[str, Mapping[str, Any]] = {}
    skipped: list[str] = []
    step = int(cfg["rows_per_call"])
    for start in range(0, len(drafted), step):
        chunk = drafted[start:start + step]
        lines = "\n".join(json.dumps({"id": r["request_id"], "text": r["text"]}, ensure_ascii=False)
                          for _, r in chunk)
        span = f"rows {start + 1}-{start + len(chunk)}"
        resp = drafter.call(prompt.version, prompt.system, prompt.user.format(rows=lines), PRECHECK_SCHEMA,
                            schema_name="precheck", item=span, cmd="precheck")
        if resp is None:
            skipped.append(span)
            continue
        for item in resp.data["items"]:
            labels[str(item["id"])] = item
    out: list[dict[str, str]] = []
    for name, r in drafted:
        got = labels.get(r["request_id"])
        agree = (got is not None and got["category"] == r["category"] and got["priority"] == r["priority"]
                 and bool(got["natural"]))
        out.append({"file": name, "request_id": r["request_id"], "text": r["text"], "lang": r["lang"],
                    "source": r["source"], "draft_category": r["category"], "draft_priority": r["priority"],
                    "check_category": str(got["category"]) if got else "",
                    "check_priority": str(got["priority"]) if got else "",
                    "check_natural": str(bool(got["natural"])) if got else "",
                    "agree": str(agree), "read_in_full": "", "human_verdict": "", "human_category": "",
                    "human_priority": "", "human_text": "", "notes": ""})
    agreeing = [o["request_id"] for o in out if o["agree"] == "True"]
    sampled = _sample(agreeing, float(cfg["sample_agreements"]), int(cfg["seed"]))
    for o in out:
        o["read_in_full"] = str(o["agree"] != "True" or o["request_id"] in sampled)
    return out, skipped


def apply_review(sheet: Path, files: Sequence[Path], accept_unsampled: bool) -> int:
    """Apply the developer's verdicts from the review sheet to the augmentation files.

    `ok` -> `needs_human_check=False`; `fix` -> the `human_*` corrections, then False; `drop` -> the row
    goes (a new scenario's other forms stay unless dropped too). Rows without a verdict are untouched.
    With `accept_unsampled`, agreeing rows that were *not* sampled are also set to False, but only when the
    developer gave a verdict to every `read_in_full` row and every sampled agreement got `ok`: the sample
    is the developer's evidence that the agreements are trustworthy. This command is run by the developer;
    nothing else ever sets `needs_human_check=False`.
    """
    entries = {r["request_id"]: r for r in _read_csv(sheet)}
    bad = sorted(i for i, r in entries.items() if r["human_verdict"].strip() not in ("", *VERDICTS))
    if bad:
        print(f"error: unknown human_verdict for {bad[:5]} (use {', '.join(VERDICTS)})", file=sys.stderr)
        return EXIT_ERROR
    must_read = [r for r in entries.values() if r["read_in_full"] == "True"]
    unread = [r["request_id"] for r in must_read if not r["human_verdict"].strip()]
    sample_failed = [r["request_id"] for r in must_read if r["agree"] == "True"
                     and r["human_verdict"].strip() not in ("", "ok")]
    if accept_unsampled and (unread or sample_failed):
        print(f"error: --accept-unsampled-agreements needs a verdict on every read_in_full row "
              f"({len(unread)} missing) and 'ok' on every sampled agreement ({len(sample_failed)} are not)",
              file=sys.stderr)
        return EXIT_ERROR
    counts = {"ok": 0, "fix": 0, "drop": 0, "accepted_unsampled": 0}
    for path in files:
        kept: list[dict[str, str]] = []
        for r in _read_csv(path):
            e = entries.get(r["request_id"])
            verdict = e["human_verdict"].strip() if e else ""
            if verdict == "drop":
                counts["drop"] += 1
                continue
            if verdict == "fix" and e is not None:
                for col in ("category", "priority", "text"):
                    if e[f"human_{col}"].strip():
                        r[col] = e[f"human_{col}"].strip()
            if verdict in ("ok", "fix"):
                counts[verdict] += 1
                r["needs_human_check"] = "False"
            elif accept_unsampled and e is not None and e["agree"] == "True" and e["read_in_full"] != "True":
                counts["accepted_unsampled"] += 1
                r["needs_human_check"] = "False"
            kept.append(r)
        _write_rows(path, kept)
    print(f"applied review: ok={counts['ok']} fix={counts['fix']} drop={counts['drop']} "
          f"accepted_unsampled_agreements={counts['accepted_unsampled']}; run validate_dataset, "
          "check_leakage and make_folds --include-augmented next")
    return EXIT_OK


# --- prune: drop drafted rows that check_leakage lists against a holdout ----------------------------------


def prune_rows(rows: Sequence[Mapping[str, str]], flagged_ids: set[str], official_norm: Mapping[str, str]
               ) -> tuple[list[dict[str, str]], list[str]]:
    """Drop LLM rows in `flagged_ids` (a new scenario loses every form) and LLM rows whose normalized text
    equals an official text of another group (`official_norm`: text_norm -> cv_group)."""
    drop_groups: set[str] = set()
    drop_ids: set[str] = set()
    for r in rows:
        if not r["author_method"].startswith("llm"):
            continue
        norm = normalize_text(r["text"], "ar" if r["lang"] == "ar" else "en")
        clash = norm in official_norm and official_norm[norm] != r["cv_group"]
        if r["request_id"] in flagged_ids or clash:
            drop_ids.add(r["request_id"])
            if r["source"] == SOURCE_NEW:
                drop_groups.add(r["cv_group"])
    kept, dropped = [], []
    for r in rows:
        gone = r["request_id"] in drop_ids or (r["source"] == SOURCE_NEW and r["cv_group"] in drop_groups)
        if gone and r["author_method"].startswith("llm"):
            dropped.append(r["request_id"])
        else:
            kept.append(dict(r))
    return kept, dropped


def prune(report: Path, csvs: Sequence[Path]) -> int:
    data = json.loads(report.read_text(encoding="utf-8"))
    flagged = set(data.get("offending_augmented_ids", [])) | set(data.get("review_augmented_ids", []))
    official_norm = {r["text_norm"]: r["cv_group"] for r in _read_csv(COMBINED)}
    for path in csvs:
        kept, dropped = prune_rows(_read_csv(path), flagged, official_norm)
        _write_rows(path, kept)
        print(f"pruned {path}: dropped {len(dropped)} drafted rows near a holdout or an official text; "
              f"{len(kept)} rows left" + (f" ({', '.join(dropped)})" if dropped else ""))
    return EXIT_OK


# --- CLI ------------------------------------------------------------------------------------------------


def _drafting_cfg() -> dict[str, Any]:
    return dict(yaml.safe_load(DATASETS_YAML.read_text(encoding="utf-8"))["augmented"])


def _estimate(calls: Sequence[tuple[str, str]], model: str, max_tokens: int) -> float:
    from campuspulse_ai.adapters.llm.cost import estimate_cost

    return sum(estimate_cost(model, int(len(s + u) / CHARS_PER_TOKEN), max_tokens) for s, u in calls)


def run_llm(args: argparse.Namespace, *, client_factory: Callable[[str], Any] | None = None,
            settings: Any = None) -> int:
    """Run `paraphrase` or `new-scenarios` (module docstring). `client_factory(api_key)` is for tests."""
    from campuspulse_ai.config.settings import Settings

    aug = _drafting_cfg()
    drafting = aug["drafting"]
    default_model = aug["precheck"]["model"] if args.cmd == "precheck" else drafting["model"]
    model = args.model or str(default_model)
    prompts = ROOT / str(drafting["prompts_dir"])
    log_path = ROOT / str(drafting["log"])
    scenarios = official_scenarios()
    if args.cmd == "paraphrase":
        prompt = Prompt.load(prompts / "paraphrase.md")
        pcfg = aug["paraphrase"]
        forms = list(pcfg["forms"])[: args.per_scenario or int(pcfg["per_scenario"])]
        planned = [(prompt.system, u) for _, u in paraphrase_requests(prompt, scenarios)]
        items = f"{len(scenarios)} scenarios x {len(forms)} forms"
    elif args.cmd == "translate":
        prompt = Prompt.load(prompts / "translate.md")
        planned = [(prompt.system, u) for _, u in translate_requests(prompt, scenarios)]
        items = f"{len(scenarios)} scenarios"
    elif args.cmd == "precheck":
        prompt = Prompt.load(prompts / "precheck.md")
        n_rows = sum(1 for p in args.csvs for r in _read_csv(p) if r["author_method"].startswith("llm"))
        step = int(aug["precheck"]["rows_per_call"])
        planned = [(prompt.system, "x" * 120 * step)] * -(-n_rows // step)
        items = f"{n_rows} drafted rows"
    else:
        prompt = Prompt.load(prompts / "new_scenarios.md")
        ncfg = yaml.safe_load(Path(args.plan).read_text(encoding="utf-8"))["augmented"]["new_scenarios"]
        reqs = new_scenario_requests(prompt, scenarios, ncfg)
        planned = [(prompt.system, r[4]) for r in reqs]
        items = f"{sum(r[2] for r in reqs)} scenarios in {len(reqs)} cells"
    max_tokens = int(drafting["request"]["max_tokens"])
    estimate = _estimate(planned, model, max_tokens)
    if args.dry_run:
        print(f"dry run: {args.cmd} with {model}: {len(planned)} calls ({items}); "
              f"upper cost estimate {estimate:.2f} USD (every output at max_tokens={max_tokens})")
        return EXIT_OK
    if args.cmd != "precheck" and _refuse_reviewed(args.out, args.force):
        return EXIT_ERROR
    settings = settings or Settings(_env_file=args.env_file)  # type: ignore[call-arg]
    key = settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else ""

    def factory() -> Any:
        if not key:
            raise KeyError("OPENROUTER_API_KEY")
        if client_factory is not None:
            return client_factory(key)
        from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient

        return OpenRouterClient(key, timeout_s=float(drafting["timeout_s"]), max_retries=2)

    cache = DraftCache(ROOT / settings.llm_cache_path if not settings.llm_cache_path.is_absolute()
                       else settings.llm_cache_path, str(drafting["cache_table"]))
    params = {k: drafting["request"][k] for k in ("temperature", "top_p", "seed", "max_tokens")}
    drafter = Drafter(model=model, params=params, cache=cache,
                      budget_usd=float(settings.llm_daily_budget_usd), spent_today=spent_today(log_path),
                      log_path=log_path, retries=int(drafting["retries_on_invalid_json"]),
                      client_factory=factory)
    try:
        if args.cmd == "paraphrase":
            rows, skipped = paraphrase_rows(drafter, prompt, scenarios, forms,
                                            str(aug["paraphrase"]["id_prefix"]))
        elif args.cmd == "translate":
            rows, skipped = translate_rows(drafter, prompt, scenarios, str(aug["translate"]["id_prefix"]))
        elif args.cmd == "precheck":
            sheet, skipped = precheck_sheet(drafter, prompt, args.csvs, aug["precheck"])
        else:
            rows, skipped = new_scenario_rows(drafter, prompt, scenarios, ncfg)
    except KeyError:
        print("error: OPENROUTER_API_KEY is not set (env or --env-file)", file=sys.stderr)
        return EXIT_NO_KEY
    except BudgetExceeded as exc:
        print(f"error: {exc} (nothing written)", file=sys.stderr)
        return EXIT_BUDGET
    finally:
        drafter.close()
        cache.close()
    for s in skipped:
        print(f"skipped: {s}")
    if args.cmd == "precheck":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(sheet)
        agree = sum(r["agree"] == "True" for r in sheet)
        full = sum(r["read_in_full"] == "True" for r in sheet)
        print(f"wrote {args.out}: {len(sheet)} drafted rows; checker {model} agrees on {agree}, "
              f"disagrees or unsure on {len(sheet) - agree}; read in full: {full}; "
              f"{drafter.calls} API calls, {drafter.cache_hits} cache hits; "
              f"cost this run {drafter.run_cost:.4f} USD")
        return EXIT_OK
    _write_rows(args.out, rows)
    print(f"wrote {args.out}: {len(rows)} rows ({items}); model {model}; {drafter.calls} API calls, "
          f"{drafter.cache_hits} cache hits; cost this run {drafter.run_cost:.4f} USD; "
          f"needs_human_check=True (review pending)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft augmentation rows.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rule = sub.add_parser("arabizi-rule", help="rule-based Arabizi spellings of every Arabic scenario (P1.9)")
    rule.add_argument("--out", type=Path, required=True)
    rule.add_argument("--force", action="store_true", help="overwrite even if reviewed rows exist")
    for name, default_out, help_text in (
        ("paraphrase", "data/augmented/paraphrases.csv", "LLM paraphrases of every official scenario (P2.2)"),
        ("new-scenarios", "data/augmented/new_scenarios.csv", "LLM-drafted new scenarios per cell (P2.2)"),
        ("translate", "data/augmented/translations.csv", "LLM EN<->AR translations + Arabizi (D-014)"),
        ("precheck", "data/augmented/review_sheet.csv", "independent LLM labels for the review (D-014)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--model", default=None, help="pinned model id (default: augmented.drafting.model)")
        p.add_argument("--out", type=Path, default=ROOT / default_out)
        p.add_argument("--env-file", type=Path, default=None, help="dotenv file holding OPENROUTER_API_KEY")
        p.add_argument("--dry-run", action="store_true", help="print calls and an upper cost estimate only")
        p.add_argument("--force", action="store_true", help="overwrite even if reviewed rows exist")
        if name == "paraphrase":
            p.add_argument("--per-scenario", type=int, default=None, help="forms per scenario (<= 3)")
        elif name == "new-scenarios":
            p.add_argument("--plan", type=Path, default=DATASETS_YAML,
                           help="YAML with augmented.new_scenarios")
        elif name == "precheck":
            p.add_argument("csvs", type=Path, nargs="+", help="augmentation files whose llm rows to check")
    pr = sub.add_parser("prune", help="drop drafted rows that check_leakage lists against a holdout")
    pr.add_argument("--report", type=Path, default=ROOT / "reports" / "leakage.json")
    pr.add_argument("csvs", type=Path, nargs="+")
    ap = sub.add_parser("apply-review", help="apply the developer's verdicts from the review sheet")
    ap.add_argument("--sheet", type=Path, default=ROOT / "data" / "augmented" / "review_sheet.csv")
    ap.add_argument("--accept-unsampled-agreements", action="store_true",
                    help="also accept agreeing rows that were not sampled (only if the sample passed)")
    ap.add_argument("csvs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd == "arabizi-rule":
        return arabizi_rule(args.out, args.force)
    if args.cmd == "prune":
        return prune(args.report, args.csvs)
    if args.cmd == "apply-review":
        return apply_review(args.sheet, args.csvs, args.accept_unsampled_agreements)
    return run_llm(args)


if __name__ == "__main__":
    sys.exit(main())
