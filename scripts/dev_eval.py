#!/usr/bin/env python3
"""P7.1: run and score the dev_fixes set (`data/dev_fixes/`), the P7 tuning and checking ground.

    python scripts/dev_eval.py run --model-dir D --split tune|check|all [--use-llm]
                                   [--llm-cache PATH] --out DIR
    python scripts/dev_eval.py score --pred DIR [--split tune|check|all] [--base DIR] --out FILE.json

`run` calls `services/ai/predict.py --debug` once per `data/dev_fixes/inputs/<split>_<lang>.csv` and writes
`DIR/<split>_<lang>.csv`. `--llm-cache` sets `LLM_ARABIZI_CACHE_PATH`, so measurements never touch the default
cache (use a path under `.tmp/p7_n/`).

`score` joins the predictions to `data/dev_fixes/dev_fixes.csv` (`--dev` overrides) on `request_id = dev_id`
and writes FILE.json plus FILE.md with, per language and block (headline, implicit_urgency, probe, all):
category and priority macro-F1 and accuracy over rows whose label the author and the blind labeller agreed
on; routing buckets from the debug set sizes (0 empty, 1 auto, 2 ask, 3+ review) with the auto-bucket joint
accuracy; per family, recall of the gold-high rows; flag rates by probe type and false hits on non-probe rows.
With `--base` it adds paired group bootstrap deltas (B=2000, seed 42, 5-95 %, groups = scenario_id) per
language and pooled. `check` numbers are for reading once per package, aggregate only.

Refuses any path under the independent evaluator's folder, `data/our_test` or `data/robustness`: our_test
numbers come from `evaluate.py`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))

from campuspulse_ai.adapters.training.metrics import (  # noqa: E402
    accuracy,
    macro_f1,
    paired_group_bootstrap,
)
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS  # noqa: E402

DEV_DIR = ROOT / "data" / "dev_fixes"
DEV_CSV = DEV_DIR / "dev_fixes.csv"
INPUTS = DEV_DIR / "inputs"
LANGS = ("en", "ar", "az")
SPLITS = ("tune", "check")
BLOCKS = ("headline", "implicit_urgency", "probe")
FLAGS_OF_INTEREST = ("safety", "distress", "injection_attempt", "empty_set", "needs_review")
FORBIDDEN = (
    Path(r"C:\Users\hp\Desktop\campuspulse_eval"),
    ROOT / "data" / "our_test",
    ROOT / "data" / "robustness",
)
BOOT: dict[str, Any] = {"resamples": 2000, "seed": 42, "low_pct": 5.0, "high_pct": 95.0}


def check_allowed(path: Path) -> Path:
    """Return `path` unless it lies under a forbidden folder (ValueError)."""
    resolved = path.resolve()
    for banned in FORBIDDEN:
        base = banned.resolve()
        if resolved == base or base in resolved.parents:
            raise ValueError(f"{path}: refused, {banned} is never an input of dev_eval")
    return path


def _splits(split: str) -> tuple[str, ...]:
    if split not in (*SPLITS, "all"):
        raise ValueError(f"--split must be tune, check or all, got {split!r}")
    return SPLITS if split == "all" else (split,)


def run(
    model_dir: Path,
    split: str,
    out: Path,
    *,
    use_llm: bool = False,
    llm_cache: Path | None = None,
    inputs: Path = INPUTS,
) -> list[Path]:
    """Run predict.py --debug over every input file of the split; return the written files."""
    check_allowed(model_dir)
    check_allowed(inputs)
    check_allowed(out)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "services" / "ai") + os.pathsep + env.get("PYTHONPATH", "")
    if llm_cache is not None:
        env["LLM_ARABIZI_CACHE_PATH"] = str(llm_cache)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for sp in _splits(split):
        for lang in LANGS:
            src = inputs / f"{sp}_{lang}.csv"
            if not src.is_file():
                continue
            dst = out / f"{sp}_{lang}.csv"
            cmd = [
                sys.executable, str(ROOT / "services" / "ai" / "predict.py"),
                "--input", str(src), "--output", str(dst), "--model-dir", str(model_dir), "--debug",
            ]
            if use_llm:
                cmd.append("--use-llm")
            subprocess.run(cmd, check=True, env=env)
            written.append(dst)
    if not written:
        raise FileNotFoundError(f"no input files for split {split!r} under {inputs}")
    return written


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def load_predictions(pred_dir: Path, split: str) -> dict[str, dict[str, str]]:
    """request_id -> prediction row (with `split` added) over the split's files in `pred_dir`."""
    check_allowed(pred_dir)
    rows: dict[str, dict[str, str]] = {}
    for sp in _splits(split):
        for path in sorted(pred_dir.glob(f"{sp}_*.csv")):
            for r in read_csv(path):
                rows[r["request_id"]] = {**r, "split": sp}
    if not rows:
        raise FileNotFoundError(f"no predictions for split {split!r} in {pred_dir}")
    return rows


def bucket(set_cat: str, set_pri: str) -> str:
    """Routing bucket from the debug set sizes: 0 empty, 1 auto, 2 ask, 3 review (3 or more)."""
    a, b = int(float(set_cat)), int(float(set_pri))
    if a == 0 or b == 0:
        return "0"
    return str(min(max(a, b), 3))


def row_bucket(row: Mapping[str, str]) -> str:
    """Routing bucket of a joined row. With the debug `route` column (P7.9: the policy's outcome) auto is 1,
    ask 2, and review or out_of_scope 3, except an empty set that went to review, which stays 0; without it,
    the set-size `bucket` of older prediction files."""
    route = row.get("route", "")
    if not route:
        return bucket(row["set_cat"], row["set_pri"])
    if route == "auto":
        return "1"
    if route == "ask":
        return "2"
    return "0" if "empty_set" in _flags(row) and route == "review" else "3"


def _flags(row: Mapping[str, str]) -> set[str]:
    return {f for f in row.get("flags", "").split(";") if f}


def joined_rows(
    dev: Sequence[Mapping[str, str]], preds: Mapping[str, Mapping[str, str]], split: str
) -> list[dict[str, str]]:
    """Dev rows of the split that have a prediction, with pred_* columns attached."""
    want = set(_splits(split))
    out = []
    for d in dev:
        p = preds.get(d["dev_id"])
        if p is None or d.get("split", p["split"]) not in want:
            continue
        out.append({
            **d, "pred_category": p["category"], "pred_priority": p["priority"],
            "set_cat": p.get("set_cat", "1"), "set_pri": p.get("set_pri", "1"), "flags": p.get("flags", ""),
            "route": p.get("route", ""),
        })
    return out


def _quality(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    cat = [r for r in rows if r.get("category")]
    pri = [r for r in rows if r.get("priority")]
    out: dict[str, Any] = {"n": len(rows), "n_cat": len(cat), "n_pri": len(pri)}
    if cat:
        y, p = [r["category"] for r in cat], [r["pred_category"] for r in cat]
        out |= {"category_macro_f1": macro_f1(y, p, CATEGORY_LABELS), "category_accuracy": accuracy(y, p)}
    if pri:
        y, p = [r["priority"] for r in pri], [r["pred_priority"] for r in pri]
        out |= {"priority_macro_f1": macro_f1(y, p, PRIORITY_LABELS), "priority_accuracy": accuracy(y, p)}
    return out


def _routing(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    counts = {"0": 0, "1": 0, "2": 0, "3": 0}
    auto_right = auto_graded = 0
    for r in rows:
        b = row_bucket(r)
        counts[b] += 1
        if b == "1" and r.get("category") and r.get("priority"):
            auto_graded += 1
            auto_right += r["pred_category"] == r["category"] and r["pred_priority"] == r["priority"]
    return {
        "buckets": counts,
        "auto_graded": auto_graded,
        "auto_joint_accuracy": auto_right / auto_graded if auto_graded else None,
    }


def _high_recall(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    fam: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        if r.get("priority") == "high" and r.get("family"):
            fam[r["family"]].append(r["pred_priority"] == "high")
    return {f: {"n": len(v), "recall": sum(v) / len(v)} for f, v in sorted(fam.items())}


def _rates(sets: Sequence[set[str]]) -> dict[str, Any]:
    n = len(sets)
    return {"n": n, **{f: (sum(f in s for s in sets) / n if n else None) for f in FLAGS_OF_INTEREST}}


def _flag_rates(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    by_probe: dict[str, list[set[str]]] = defaultdict(list)
    non_probe: list[set[str]] = []
    for r in rows:
        if r.get("block") == "probe":
            by_probe[r.get("probe_type") or "probe"].append(_flags(r))
        else:
            non_probe.append(_flags(r))
    return {
        "probes": {k: _rates(v) for k, v in sorted(by_probe.items())},
        "non_probe_false_hits": _rates(non_probe),
    }


def _bootstrap(rows: Sequence[Mapping[str, str]], base: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, labels in (("category", CATEGORY_LABELS), ("priority", PRIORITY_LABELS)):
        use = [r for r in rows if r.get(key) and r["dev_id"] in base]
        if not use:
            continue
        out[key] = {
            "n": len(use),
            **paired_group_bootstrap(
                [r[key] for r in use],
                [base[r["dev_id"]][key] for r in use],
                [r[f"pred_{key}"] for r in use],
                [r.get("scenario_id") or r["dev_id"] for r in use],
                labels,
                **BOOT,
            ),
        }
    return out


def score(
    dev: Sequence[Mapping[str, str]],
    preds: Mapping[str, Mapping[str, str]],
    split: str,
    base_preds: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """The full score dict (module docstring)."""
    rows = joined_rows(dev, preds, split)
    base_view: dict[str, dict[str, str]] = {}
    if base_preds is not None:
        for r in joined_rows(dev, base_preds, split):
            base_view[r["dev_id"]] = {"category": r["pred_category"], "priority": r["pred_priority"]}
    result: dict[str, Any] = {"split": split, "n_rows": len(rows), "languages": {}}
    for lang in [*sorted({r["lang"] for r in rows}), "pooled"]:
        sel = rows if lang == "pooled" else [r for r in rows if r["lang"] == lang]
        entry: dict[str, Any] = {
            "quality": {
                "all": _quality(sel),
                **{b: _quality([r for r in sel if r.get("block") == b]) for b in BLOCKS},
            },
            "routing": _routing(sel),
            "high_recall_by_family": _high_recall(sel),
            "flags": _flag_rates(sel),
        }
        if base_preds is not None:
            entry["vs_base"] = _bootstrap(sel, base_view)
        result["languages"][lang] = entry
    return result


def _fmt(v: object) -> str:
    return "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)


def markdown(result: Mapping[str, Any]) -> str:
    lines = [f"# dev_fixes score ({result['split']}, {result['n_rows']} rows)", ""]
    for lang, e in result["languages"].items():
        head = "| block | n | cat F1 | cat acc | pri F1 | pri acc |"
        lines += [f"## {lang}", "", head, "|---|---|---|---|---|---|"]
        for blk, q in e["quality"].items():
            lines.append(
                f"| {blk} | {q['n']} | {_fmt(q.get('category_macro_f1'))} "
                f"| {_fmt(q.get('category_accuracy'))}"
                f" | {_fmt(q.get('priority_macro_f1'))} | {_fmt(q.get('priority_accuracy'))} |"
            )
        b = e["routing"]["buckets"]
        lines += [
            "",
            f"routing: empty {b['0']}, auto {b['1']}, ask {b['2']}, review {b['3']}; auto joint accuracy "
            f"{_fmt(e['routing']['auto_joint_accuracy'])} (n={e['routing']['auto_graded']})",
            "",
        ]
        if e["high_recall_by_family"]:
            lines += [
                "high recall by family: "
                + ", ".join(
                    f"{f} {v['recall']:.2f} (n={v['n']})" for f, v in e["high_recall_by_family"].items()
                ),
                "",
            ]
        fl = e["flags"]
        lines.append(
            "flag rates, non-probe rows (false hits): "
            + ", ".join(f"{k} {_fmt(v)}" for k, v in fl["non_probe_false_hits"].items() if k != "n")
        )
        for pt, v in fl["probes"].items():
            cells = ", ".join(f"{k} {_fmt(x)}" for k, x in v.items() if k != "n")
            lines.append(f"- probe {pt} (n={v['n']}): {cells}")
        for key, d in e.get("vs_base", {}).items():
            lines.append(
                f"vs base {key}: delta {d['delta']:+.3f} [{d['ci_low']:+.3f}, {d['ci_high']:+.3f}], "
                f"P(better) {d['p_better']:.2f} (n={d['n']})"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def cmd_score(args: argparse.Namespace) -> int:
    for p in (args.pred, args.dev, args.out, *([args.base] if args.base else [])):
        check_allowed(p)
    dev = read_csv(args.dev)
    preds = load_predictions(args.pred, args.split)
    base = load_predictions(args.base, args.split) if args.base else None
    result = score(dev, preds, args.split, base)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = args.out.with_suffix(".md")
    md.write_text(markdown(result), encoding="utf-8")
    print(f"wrote {args.out} and {md} ({result['n_rows']} rows)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    written = run(args.model_dir, args.split, args.out, use_llm=args.use_llm, llm_cache=args.llm_cache)
    print(f"wrote {len(written)} prediction files to {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dev_eval.py", description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run predict.py --debug over the dev inputs")
    r.add_argument("--model-dir", type=Path, required=True)
    r.add_argument("--split", default="all")
    r.add_argument("--use-llm", action="store_true")
    r.add_argument("--llm-cache", type=Path, default=None)
    r.add_argument("--out", type=Path, required=True)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("score", help="score a prediction directory")
    s.add_argument("--pred", type=Path, required=True)
    s.add_argument("--split", default="all")
    s.add_argument("--base", type=Path, default=None)
    s.add_argument("--dev", type=Path, default=DEV_CSV)
    s.add_argument("--out", type=Path, required=True)
    s.set_defaults(fn=cmd_score)
    args = ap.parse_args(argv)
    try:
        return int(args.fn(args))
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
