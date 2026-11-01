#!/usr/bin/env python3
# ruff: noqa: E501
"""Triaged review queue for the 501 unreviewed augmentation rows (P8.1).

    python scripts/review_queue.py build            # writes data/augmented/review/review_queue.csv
    python scripts/review_queue.py apply [--dry-run] [--accept-agreed [--include-arabizi] [--skip-guard]]

The user fills one `decision` cell per row: `keep`, `fix:<Category>/<priority>` or `drop` (blank = undecided).
`apply` sets `needs_human_check=False` ONLY for decided rows and for the siblings that inherit a scenario
verdict (or, with `--accept-agreed`, for checker-agreed rows after the guard passes). It never touches
`data/raw` or `data/clean`, never decides anything by itself, and writes an audit log
`data/augmented/review/applied_<date>.jsonl`.

Blocks, in the order to work through them (highest value for the hidden test first):
  T1  new_scenarios EN+AR rows where the checker disagreed (scope=scenario for the first row of a scenario)
  T2  one anchor row per remaining new_scenarios EN+AR scenario (scope=scenario): its verdict covers the
      scenario's other EN/AR forms listed in `inherits`
  T3  paraphrases + translations: disagreements, then 10 sampled agreements (labels come from the source
      scenario, so `fix:` is refused there: use `drop` for an unfaithful row)
  T4  every Arabizi row (lowest value: no Arabizi in the official data; skip it freely)
"""

from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUG = ROOT / "data" / "augmented"
REVIEW = AUG / "review"
FILES = ("new_scenarios.csv", "paraphrases.csv", "translations.csv", "arabizi.csv", "arabizi_from_official.csv")
COLUMNS = ("block", "draft_id", "decision", "scope", "lang", "text", "draft_category", "draft_priority",
           "check_category", "check_priority", "check_natural", "why_first", "inherits", "scenario_note",
           "file", "edit_text")
CATEGORIES = ("Academic Support", "Facilities", "Finance", "IT Support", "Registration", "Transportation")
PRIORITIES = ("low", "medium", "high")
SECONDS = {"T1": 25, "T2": 15, "T3": 30, "T4": 6}  # per row, for the printed estimate
SAMPLE_AGREEMENTS = 10
SEED = 42
MAX_CHANGE_RATE = 0.10  # guard: share of checker-agreed queue rows the user had to fix or drop
EXIT_OK, EXIT_ERROR = 0, 1


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _write(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str], *, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _rank(rid: str) -> str:
    return hashlib.sha256(f"{SEED}|{rid}".encode()).hexdigest()


def _notes(aug: Path) -> dict[str, str]:
    path = aug / "new_scenarios_notes.md"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"NEW-C\d+", cells[0]):
            out[cells[0]] = f"{cells[3]}; {cells[4]}"
    return out


def _disagreement(s: Mapping[str, str]) -> str:
    bits = []
    if s["check_category"] != s["draft_category"] or s["check_priority"] != s["draft_priority"]:
        bits.append(f"checker says {s['check_category']}/{s['check_priority']}, draft says "
                    f"{s['draft_category']}/{s['draft_priority']}")
    if s["check_natural"] != "True":
        bits.append("checker found the wording unnatural")
    return "; ".join(bits) or "checker disagreed"


def build_rows(aug: Path, review: Path) -> list[dict[str, str]]:
    """The ordered queue rows (T1..T4) for every row still `needs_human_check=True`."""
    sheet = {r["request_id"]: r for r in _read(review / "review_sheet.csv")}
    data: dict[str, tuple[str, dict[str, str]]] = {}
    for name in FILES:
        path = aug / name
        if path.is_file():
            for r in _read(path):
                if r["needs_human_check"].strip().lower() == "true":
                    data[r["request_id"]] = (name, r)
    notes = _notes(aug)

    def make(block: str, rid: str, why: str, scope: str = "row", inherits: Sequence[str] = ()) -> dict[str, str]:
        name, r = data[rid]
        s = sheet.get(rid, {})
        return {"block": block, "draft_id": rid, "decision": "", "scope": scope, "lang": r["lang"],
                "text": r["text"], "draft_category": r["category"], "draft_priority": r["priority"],
                "check_category": s.get("check_category", ""), "check_priority": s.get("check_priority", ""),
                "check_natural": s.get("check_natural", ""), "why_first": why,
                "inherits": " ".join(inherits), "scenario_note": notes.get(r["cv_group"], ""),
                "file": name, "edit_text": ""}

    def disagrees(rid: str) -> bool:
        return rid in sheet and sheet[rid]["agree"] != "True"

    new = sorted((rid for rid, (n, r) in data.items() if n == "new_scenarios.csv" and r["lang"] in ("en", "ar")),
                 key=lambda i: (data[i][1]["cv_group"], i))
    by_group: dict[str, list[str]] = defaultdict(list)
    for rid in new:
        by_group[data[rid][1]["cv_group"]].append(rid)

    t1: list[dict[str, str]] = []
    t2: list[dict[str, str]] = []
    for group, ids in sorted(by_group.items()):
        bad = [i for i in ids if disagrees(i)]
        queued = set(bad)
        if bad:
            anchor = bad[0]
        else:
            anchor = next((i for i in ids if data[i][1]["lang"] == "en"), ids[0])
            queued = {anchor}
        covered = [i for i in ids if i not in queued]
        covered_text = (f"your verdict also covers {len(covered)} other EN/AR form(s) of {group}"
                        if covered else f"all EN/AR forms of {group} are in this queue")
        for i in bad:
            if i == anchor:
                t1.append(make("T1", i, f"{_disagreement(sheet[i])}. SCENARIO row: fix labels here applies to "
                               f"every form of {group}; {covered_text}", "scenario", covered))
            else:
                t1.append(make("T1", i, f"{_disagreement(sheet[i])}. Row only"))
        if not bad:
            t2.append(make("T2", anchor, f"one row per scenario: keep = scenario {group} is right; {covered_text}",
                           "scenario", covered))

    t3_dis: list[dict[str, str]] = []
    pool_agree: list[str] = []
    for rid, (n, r) in sorted(data.items()):
        if n in ("paraphrases.csv", "translations.csv") and r["lang"] != "arabizi":
            if disagrees(rid):
                t3_dis.append(make("T3", rid, f"{_disagreement(sheet[rid])}. Faithful to the source? else drop"))
            elif rid in sheet:
                pool_agree.append(rid)
    pool_agree.sort(key=lambda i: (sheet[i]["read_in_full"] != "True", _rank(i)))
    t3 = t3_dis + [make("T3", i, "sampled agreement: evidence for the fast path (should be keep)")
                   for i in sorted(pool_agree[:SAMPLE_AGREEMENTS])]

    t4: list[dict[str, str]] = []
    arabizi = [rid for rid, (_, r) in data.items() if r["lang"] == "arabizi"]
    order = {n: k for k, n in enumerate(FILES)}
    arabizi.sort(key=lambda i: (not disagrees(i), order[data[i][0]], data[i][1]["cv_group"], i))
    for rid in arabizi:
        name = data[rid][0]
        if disagrees(rid):
            why = f"{_disagreement(sheet[rid])}. Spelling a Jordanian student would write?"
        elif name == "arabizi_from_official.csv":
            why = "no checker pass; labels come from the official scenario: check meaning and spelling only"
        else:
            why = "checker agreed; check spelling only"
        t4.append(make("T4", rid, why))
    return t1 + t2 + t3 + t4


def build(aug: Path = AUG, review: Path = REVIEW, out: Path | None = None) -> int:
    rows = build_rows(aug, review)
    out = out or review / "review_queue.csv"
    _write(out, rows, COLUMNS, bom=True)
    total = 0.0
    print(f"wrote {out} ({len(rows)} rows)")
    for block in ("T1", "T2", "T3", "T4"):
        n = sum(1 for r in rows if r["block"] == block)
        minutes = n * SECONDS[block] / 60
        total += minutes
        print(f"  {block}: {n:>3} rows, about {minutes:4.0f} min")
    print(f"  total: {len(rows)} rows, about {total:.0f} min (T4 is optional)")
    return EXIT_OK


# --- apply -------------------------------------------------------------------------------------------------


class ReviewError(ValueError):
    pass


def parse_decision(cell: str) -> tuple[str, str, str]:
    """(verb, category, priority); verb is '' for undecided."""
    c = cell.strip()
    if not c:
        return "", "", ""
    if c.lower() in ("keep", "drop"):
        return c.lower(), "", ""
    m = re.fullmatch(r"fix:\s*([^/]+?)\s*/\s*(\w+)", c, flags=re.IGNORECASE)
    if m:
        cat = next((k for k in CATEGORIES if k.lower() == m.group(1).lower()), "")
        pri = m.group(2).lower()
        if cat and pri in PRIORITIES:
            return "fix", cat, pri
    raise ReviewError(f"bad decision {cell!r} (use keep | fix:<Category>/<priority> | drop)")


def apply(queue_path: Path | None = None, aug: Path = AUG, review: Path = REVIEW, *, dry_run: bool = False,
          accept_agreed: bool = False, include_arabizi: bool = False, skip_guard: bool = False,
          today: str | None = None) -> int:
    queue_path = queue_path or review / "review_queue.csv"
    queue = _read(queue_path)
    try:
        decisions = {q["draft_id"]: (q, parse_decision(q["decision"])) for q in queue}
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    files = {n: _read(aug / n) for n in FILES if (aug / n).is_file()}
    where = {r["request_id"]: (n, r) for n, rows in files.items() for r in rows}

    # validate decisions
    for rid, (q, (verb, _cat, _)) in decisions.items():
        if rid not in where:
            print(f"warning: {rid} is no longer in {q['file']} (already applied or dropped); skipped")
            continue
        if verb == "fix" and q["file"] != "new_scenarios.csv":
            print(f"error: {rid}: fix: is only for new_scenarios rows; a row of {q['file']} inherits its source "
                  "scenario's labels (use drop if it is unfaithful, keep + edit_text for a wording fix)",
                  file=sys.stderr)
            return EXIT_ERROR

    groups: dict[str, list[str]] = defaultdict(list)
    for rid, (n, r) in where.items():
        if n == "new_scenarios.csv":
            groups[r["cv_group"]].append(rid)

    # scenario-level outcomes from the scenario-scope rows (and any fix anywhere in the group)
    group_labels: dict[str, tuple[str, str]] = {}
    group_drop: set[str] = set()
    group_ok: set[str] = set()
    for rid, (q, (verb, cat, pri)) in decisions.items():
        if rid not in where or where[rid][0] != "new_scenarios.csv" or not verb:
            continue
        group = where[rid][1]["cv_group"]
        if verb == "fix":
            if group in group_labels and group_labels[group] != (cat, pri):
                print(f"error: {group}: two different fix labels {group_labels[group]} and {(cat, pri)}; "
                      "a scenario has one label", file=sys.stderr)
                return EXIT_ERROR
            group_labels[group] = (cat, pri)
        if q["scope"] == "scenario":
            if verb == "drop":
                group_drop.add(group)
            else:
                group_ok.add(group)
    clash = sorted(g for g in group_labels if g in group_drop)
    if clash:
        print(f"error: {clash}: scenario dropped by one row and fixed by another", file=sys.stderr)
        return EXIT_ERROR

    # guard for --accept-agreed
    sheet = {r["request_id"]: r for r in _read(review / "review_sheet.csv")} if accept_agreed else {}
    if accept_agreed and not skip_guard:
        open_rows = [rid for rid, (q, (verb, _, _)) in decisions.items()
                     if q["block"] in ("T1", "T2", "T3") and not verb and rid in where]
        agreed = [(rid, d[1][0]) for rid, d in decisions.items()
                  if sheet.get(rid, {}).get("agree") == "True" and d[1][0]]
        changed = [rid for rid, verb in agreed if verb != "keep"]
        rate = len(changed) / len(agreed) if agreed else 1.0
        if open_rows or not agreed or rate > MAX_CHANGE_RATE:
            print(f"error: guard failed. undecided T1-T3 rows: {len(open_rows)}; decided checker-agreed rows: "
                  f"{len(agreed)}, of which fixed or dropped: {len(changed)} ({rate:.0%}, limit "
                  f"{MAX_CHANGE_RATE:.0%}). Finish T1-T3 first, or rerun with --skip-guard (stated risk: the "
                  "agreed rows are then accepted on the checker's word alone).", file=sys.stderr)
            return EXIT_ERROR

    log: list[dict[str, object]] = []
    counts = {"keep": 0, "fix": 0, "drop": 0, "inherited": 0, "accepted_agreed": 0, "edited_text": 0}
    day = today or datetime.now(UTC).date().isoformat()

    for name, rows in files.items():
        kept: list[dict[str, str]] = []
        for r in rows:
            rid = r["request_id"]
            before = {"category": r["category"], "priority": r["priority"], "text": r["text"],
                      "needs_human_check": r["needs_human_check"]}
            group = r["cv_group"] if name == "new_scenarios.csv" else ""
            q, (verb, _, _) = decisions.get(rid, ({}, ("", "", "")))
            reason = ""
            if group in group_drop:
                verb, reason = "drop", "scenario dropped" + ("" if verb == "drop" else f" via {group}")
            elif verb:
                reason = "decision"
            elif group in group_ok and r["lang"] != "arabizi" and rid not in decisions:
                verb, reason = "inherit", f"scenario {group} verdict"
            elif (accept_agreed and rid in sheet and sheet[rid]["agree"] == "True" and rid not in decisions
                  and (include_arabizi or r["lang"] != "arabizi") and group not in group_labels):
                verb, reason = "agreed", "checker-agreed, guard passed"
            if verb == "drop":
                counts["drop"] += 1
                log.append({"id": rid, "file": name, "action": "drop", "reason": reason, "before": before})
                continue
            if group in group_labels:  # one label per scenario, kept in step even for undecided rows
                r["category"], r["priority"] = group_labels[group]
            if verb in ("keep", "fix", "inherit", "agreed"):
                if q and q.get("edit_text", "").strip() and rid in decisions:
                    r["text"] = q["edit_text"].strip()
                    counts["edited_text"] += 1
                r["needs_human_check"] = "False"
                counts[{"inherit": "inherited", "agreed": "accepted_agreed"}.get(verb, verb)] += 1
            after = {"category": r["category"], "priority": r["priority"], "text": r["text"],
                     "needs_human_check": r["needs_human_check"]}
            if after != before:
                log.append({"id": rid, "file": name, "action": verb or "label_follows_scenario",
                            "reason": reason or f"scenario {group} label fixed", "before": before, "after": after})
            kept.append(r)
        files[name] = kept

    print(f"{'dry run: ' if dry_run else ''}keep={counts['keep']} fix={counts['fix']} drop={counts['drop']} "
          f"inherited_from_scenario={counts['inherited']} accepted_agreed={counts['accepted_agreed']} "
          f"text_edits={counts['edited_text']}")
    if dry_run:
        return EXIT_OK
    for name, rows in files.items():
        with (aug / name).open(encoding="utf-8-sig", newline="") as fh:
            columns = csv.DictReader(fh).fieldnames or []
        bom = (aug / name).read_bytes().startswith(codecs.BOM_UTF8)
        _write(aug / name, rows, columns, bom=bom)
    if log:
        review.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with (review / f"applied_{day}.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            for entry in log:
                fh.write(json.dumps({"ts": stamp, **entry}, ensure_ascii=False) + "\n")
    print("next: validate_dataset --kind augmented on each file, check_leakage, make_folds --include-augmented")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="write data/augmented/review/review_queue.csv")
    p = sub.add_parser("apply", help="apply the decision cells")
    p.add_argument("--queue", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--accept-agreed", action="store_true",
                   help="also accept every undecided checker-agreed row (guarded)")
    p.add_argument("--include-arabizi", action="store_true", help="fast path also covers Arabizi rows")
    p.add_argument("--skip-guard", action="store_true", help="fast path without the evidence guard")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        return build()
    return apply(args.queue, dry_run=args.dry_run, accept_agreed=args.accept_agreed,
                 include_arabizi=args.include_arabizi, skip_guard=args.skip_guard)


if __name__ == "__main__":
    sys.exit(main())
