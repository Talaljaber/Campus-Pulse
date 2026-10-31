#!/usr/bin/env python3
"""Draft augmentation rows (P1.9: rule-based Arabizi; P2.2 adds the LLM subcommands).

    python scripts/draft_augmentation.py arabizi-rule --out data/augmented/arabizi.csv [--force]

`arabizi-rule` reverse-transliterates every official Arabic scenario core into
`augmented.arabizi_variants` (config/datasets.yaml) Arabizi spellings, offline and deterministic:
  1. per Arabic token: a reverse-lexicon hit (`config/lexicons/arabizi.yaml lexicon`, reversed; spelling
     chosen by the variant), else a known proclitic (و, ب, ال, بال, لل, وال ...) + a lexicon word
     (`bel mamar`, `w 3indi`), else a character-level reverse map (variant 0 uses digits 7/5/3/2/6/9,
     variant 1 letters kh/gh/g where the convention allows);
  2. rows copy labels and `cv_group` from the source scenario, with `source=arabizi_rule`,
     `author_method=rule`, `lang=arabizi`, `needs_human_check=True`.
Rows stay out of training until the developer has read them, fixed unnatural spellings and set
`needs_human_check=False` (load_pool drops unreviewed rows). The command refuses to overwrite a file that
already holds reviewed rows unless `--force` is given. It prints how many drafts the package
`LangIdentifier` detects as Arabizi (the P2.4 gate on reviewed rows is >= 95 %).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from campuspulse_ai.adapters.preprocess.langid import LangIdentifier
from campuspulse_ai.adapters.preprocess.wrappers import normalize_text
from campuspulse_ai.domain.values import Lang

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "data" / "clean" / "scenarios.csv"
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
ARABIZI_YAML = ROOT / "config" / "lexicons" / "arabizi.yaml"
DATASETS_YAML = ROOT / "config" / "datasets.yaml"
ID_PREFIX = "AUG-AZ-"
SOURCE = "arabizi_rule"

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


def arabizi_rule(out: Path, force: bool) -> int:
    if out.is_file() and not force:
        rows_in = _read_csv(out)
        reviewed = [r["request_id"] for r in rows_in if r["needs_human_check"].strip().lower() == "false"]
        if reviewed:
            msg = f"refusing to overwrite {out}: {len(reviewed)} reviewed rows (use --force)"
            print(msg, file=sys.stderr)
            return 1
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
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    detected = sum(langid.identify(r["text"]) is Lang.ARABIZI for r in rows)
    print(f"wrote {out}: {len(rows)} rows from {len(scenarios)} Arabic scenarios x {variants} variants; "
          f"LangIdentifier detects {detected}/{len(rows)} as arabizi; "
          "needs_human_check=True (review pending)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft augmentation rows (offline subcommands).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rule = sub.add_parser("arabizi-rule", help="rule-based Arabizi spellings of every Arabic scenario (P1.9)")
    rule.add_argument("--out", type=Path, required=True)
    rule.add_argument("--force", action="store_true", help="overwrite even if reviewed rows exist")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return arabizi_rule(args.out, args.force)


if __name__ == "__main__":
    sys.exit(main())
