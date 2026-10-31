"""Red-team report files written by the offline CLI (P4.11).

- `write_report(run, out_dir, source)` -> `<out_dir>/<stamp>.json`: the scorecard, the three
  robustness properties, the source of the seeds and every item (the version used in the report §4).
- `write_candidates(run, out_dir)` -> `<out_dir>/candidates_<stamp>.csv` (None when nothing failed):
  every failed item in the probe columns of `config/datasets.yaml` `probes` plus
  `needs_human_check=True`, for a human to promote into the probes by hand.

`<stamp>` is the run's `created_at` in UTC (`20261105T130000Z`). Candidates are written next to the
report, never into `data/robustness/` (D-013): they come from training texts, so promoting one is a
manual, reviewed step. Errors: `OSError` from the file system. Writes only those two files.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from datetime import UTC
from pathlib import Path

from campuspulse_ai.application.use_cases.run_redteam import RedTeamRun

CANDIDATE_COLUMNS = (
    "request_id",
    "text",
    "lang",
    "style",
    "base_request_id",
    "intended_category",
    "intended_priority",
    "expected_flags",
    "author_method",
    "notes",
    "needs_human_check",
)
CANDIDATE_ID = "CAND-{:03d}"
AUTHOR_METHOD = "perturb"
FLAG_SEPARATOR = ";"
"""As `probes.flag_separator` in config/datasets.yaml."""
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def stamp(run: RedTeamRun) -> str:
    """The file stamp of a run: its `created_at` in UTC."""
    return run.scorecard.created_at.astimezone(UTC).strftime(STAMP_FORMAT)


def write_report(run: RedTeamRun, out_dir: Path, source: Mapping[str, object]) -> Path:
    """Write `<out_dir>/<stamp>.json` and return its path (module docstring)."""
    s = run.scorecard
    body = {
        "run_id": s.run_id,
        "created_at": s.created_at.isoformat(),
        "n": s.n,
        "seed": s.seed,
        "overall": s.overall,
        "by_style": s.by_style,
        "by_lang": s.by_lang,
        "properties": dict(run.properties),
        "source": dict(source),
        "failures": [dict(f) for f in s.failures],
        "items": [
            {
                "style": r.item.style,
                "lang": r.item.lang.value,
                "text": r.item.text,
                "base_id": r.item.base_id,
                "intended_category": r.item.intended_category.value,
                "intended_priority": r.item.intended_priority.value,
                "expected_flags": sorted(r.item.expected_flags),
                "outcome": r.outcome.value,
                "got_category": r.category.value if r.category else None,
                "got_priority": r.priority.value if r.priority else None,
                "base_category": r.base_category.value if r.base_category else None,
                "base_priority": r.base_priority.value if r.base_priority else None,
                "flags": sorted(r.flags),
                "passed": r.passed,
                "stable": r.stable,
                "reason": r.reason,
            }
            for r in run.results
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp(run)}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def write_candidates(run: RedTeamRun, out_dir: Path) -> Path | None:
    """Write the failed items as probe candidates; None (no file) when every item passed."""
    failed = [r for r in run.results if not r.passed]
    if not failed:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"candidates_{stamp(run)}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDIDATE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for i, r in enumerate(failed, start=1):
            writer.writerow(
                {
                    "request_id": CANDIDATE_ID.format(i),
                    "text": r.item.text,
                    "lang": r.item.lang.value,
                    "style": r.item.style,
                    "base_request_id": r.item.base_id or "",
                    "intended_category": r.item.intended_category.value,
                    "intended_priority": r.item.intended_priority.value,
                    "expected_flags": FLAG_SEPARATOR.join(sorted(r.item.expected_flags)),
                    "author_method": AUTHOR_METHOD,
                    "notes": r.reason,
                    "needs_human_check": "True",
                }
            )
    return path
