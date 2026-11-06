#!/usr/bin/env python3
# ruff: noqa: E501  (markdown table rows are long f-strings; splitting them hurts readability)
"""Tables for `reports/results_v2.md` (rc1 vs rc2, ablations, bake-off) from the committed report files.

    python scripts/results_v2.py [--out .tmp/results_v2_tables.md]

Reads only `reports/` (results_v1.json for rc1, and metrics.json, coverage.json, fairness.json,
ablations.json, cv_p2.json, encoder_bakeoff.json written for rc2). It recomputes nothing, so the tables match
the reports byte for byte. The narrative of results_v2.md is written by hand around these tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
SETS = ("set1", "set2", "set3")


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((REPORTS / name).read_text(encoding="utf-8"))
    return data


def f(x: Any, nd: int = 3) -> str:
    return "–" if x is None else f"{float(x):.{nd}f}"


def bench(metrics: dict[str, Any], dataset: str, target: str, model: str = "Ensemble (tier 0)") -> Any:
    for r in metrics["benchmark"]:
        if r["dataset"] == dataset and r["target"] == target and r["model"] == model:
            return r
    return None


def cov(coverage: dict[str, Any], dataset: str, target: str, lang: str = "all") -> Any:
    for r in coverage["rows"]:
        if r["dataset"] == dataset and r["target"] == target and r["lang"] == lang:
            return r
    return None


def headline(v1: dict[str, Any], m: dict[str, Any], c: dict[str, Any], cv: dict[str, Any]) -> list[str]:
    lines = [
        "| slice | rows / groups | cat F1 rc1 | cat F1 rc2 | pri F1 rc1 | pri F1 rc2 | cat cov (size) rc1 → rc2 "
        "| pri cov (size) rc1 → rc2 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    o1 = v1["oof"]["official"]
    oc, op = cov(c, "oof_official", "category"), cov(c, "oof_official", "priority")
    lines.append(
        f"| OOF official | {o1['rows']} / {o1['groups']} | {f(o1['category']['macro_f1'])} | "
        f"{f(bench(m, 'oof_official', 'category')['macro_f1'])} | {f(o1['priority']['macro_f1'])} | "
        f"{f(bench(m, 'oof_official', 'priority')['macro_f1'])} | – → {f(oc['coverage'])} ({f(oc['mean_set_size'], 2)})"
        f" | – → {f(op['coverage'])} ({f(op['mean_set_size'], 2)}) |"
    )
    n = cv.get("nested", {})
    if n:
        lines.append(
            f"| OOF official, nested (honest tuned estimate) | 432 / 30 | – | "
            f"{f(n['category_macro_f1_oof_official'])} | – | {f(n['priority_macro_f1_oof_official'])} | "
            f"– → {f(n['coverage_official']['category'])} ({f(n['mean_set_size_official']['category'], 2)}) | "
            f"– → {f(n['coverage_official']['priority'])} ({f(n['mean_set_size_official']['priority'], 2)}) |"
        )
    for s in (*SETS, "pooled"):
        t1 = v1["our_test"][s]
        ds = "our_test" if s == "pooled" else f"our_test_{s}"
        k1 = t1["conformal"]
        cc, cp = cov(c, ds, "category"), cov(c, ds, "priority")
        lines.append(
            f"| our_test {s} | {t1['rows']} / {t1['groups']} | {f(t1['category']['macro_f1'])} | "
            f"{f(bench(m, ds, 'category')['macro_f1'])} | {f(t1['priority']['macro_f1'])} | "
            f"{f(bench(m, ds, 'priority')['macro_f1'])} | {f(k1['category']['coverage'])} "
            f"({f(k1['category']['mean_set_size'], 2)}) → {f(cc['coverage'])} ({f(cc['mean_set_size'], 2)}) | "
            f"{f(k1['priority']['coverage'])} ({f(k1['priority']['mean_set_size'], 2)}) → {f(cp['coverage'])} "
            f"({f(cp['mean_set_size'], 2)}) |"
        )
    return lines


def by_lang(v1: dict[str, Any], fair: dict[str, Any]) -> list[str]:
    lines = [
        "| our_test pooled slice | rows / groups | cat F1 rc1 | cat F1 rc2 | pri F1 rc1 | pri F1 rc2 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for lang in ("en", "ar", "arabizi"):
        t1 = v1["our_test"]["pooled"]["by_lang"][lang]
        cat = next(
            s
            for s in fair["slices"]
            if s["dataset"] == "our_test" and s["slice"] == lang and s["target"] == "category"
        )
        pri = next(
            s
            for s in fair["slices"]
            if s["dataset"] == "our_test" and s["slice"] == lang and s["target"] == "priority"
        )
        lines.append(
            f"| {lang} | {cat['n_rows']} / {cat['n_groups']} | {f(t1['category']['macro_f1'])} | "
            f"{f(cat['macro_f1'])} | {f(t1['priority']['macro_f1'])} | {f(pri['macro_f1'])} |"
        )
    for lang in ("en", "ar"):
        o1 = v1["oof"]["by_lang_script_official"][lang]
        cat = next(
            s
            for s in fair["slices"]
            if s["dataset"] == "oof_official" and s["slice"] == lang and s["target"] == "category"
        )
        pri = next(
            s
            for s in fair["slices"]
            if s["dataset"] == "oof_official" and s["slice"] == lang and s["target"] == "priority"
        )
        lines.append(
            f"| OOF official {lang} | {cat['n_rows']} / {cat['n_groups']} | {f(o1['category']['macro_f1'])} | "
            f"{f(cat['macro_f1'])} | {f(o1['priority']['macro_f1'])} | {f(pri['macro_f1'])} |"
        )
    return lines


def ablations(abl: dict[str, Any]) -> list[str]:
    lines = [
        "| arm | OOF cat F1 (Δ, 90 % CI) | OOF pri F1 (Δ, 90 % CI) | our_test cat F1 (Δ) | our_test pri F1 (Δ) "
        "| set1+2 note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, a in abl["arms"].items():
        oc, op = a["oof_official"]["category"], a["oof_official"]["priority"]
        tc, tp = a["our_test"]["category"], a["our_test"]["priority"]
        s1 = a.get("our_test_set1", {}).get("category", {})
        s2 = a.get("our_test_set2", {}).get("category", {})
        flag = " **unreviewed**" if a.get("unreviewed_training_rows") else ""
        lines.append(
            f"| `{name}`{flag} | {f(oc['macro_f1'])} ({oc['delta']:+.3f}, [{oc['ci90'][0]:+.3f}, {oc['ci90'][1]:+.3f}]) "
            f"| {f(op['macro_f1'])} ({op['delta']:+.3f}, [{op['ci90'][0]:+.3f}, {op['ci90'][1]:+.3f}]) "
            f"| {f(tc['macro_f1'])} ({tc['delta']:+.3f}) | {f(tp['macro_f1'])} ({tp['delta']:+.3f}) "
            f"| cat set1 {f(s1.get('macro_f1'))}, set2 {f(s2.get('macro_f1'))} |"
        )
    return lines


def bakeoff(b: dict[str, Any]) -> list[str]:
    lines = [
        "| encoder | data | head | centred | cat F1 | EN | AR | Δ vs e5 LR official (90 % CI) |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for r in b["grid"]:
        v = r.get("vs_e5_lr_official")
        ci = f"{v['delta']:+.3f} [{v['ci90_low']:+.3f}, {v['ci90_high']:+.3f}]" if v else "–"
        lines.append(
            f"| {r['encoder']} | {r['data']} | {r['head']} | {'yes' if r['centred'] else 'no'} | "
            f"{f(r['cat_f1'])} | {f(r['slices'].get('en'))} | {f(r['slices'].get('ar'))} | {ci} |"
        )
    lines += ["", "| comparison | heads passing the D-016 rule | adopt |", "| --- | ---: | --- |"]
    for k, d in b["decisions"].items():
        lines.append(f"| `{k}` | {d['heads_passing']}/3 | {'yes' if d['adopt'] else 'no'} |")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / ".tmp" / "results_v2_tables.md")
    args = ap.parse_args(argv)
    v1, m, c = load("results_v1.json"), load("metrics.json"), load("coverage.json")
    fair, abl, cv, b = (
        load("fairness.json"),
        load("ablations.json"),
        load("cv_p2.json"),
        load("encoder_bakeoff.json"),
    )
    parts = [
        "## Headline",
        "",
        *headline(v1, m, c, cv),
        "",
        "## By language",
        "",
        *by_lang(v1, fair),
        "",
        "## Ablations",
        "",
        *ablations(abl),
        "",
        "## Bake-off",
        "",
        *bakeoff(b),
        "",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
