#!/usr/bin/env python3
"""Build and score the P7.0 dev set (data/dev_fixes).

    python scripts/build_dev_fixes.py blind   # shuffle authored rows -> raw/blind_input_<lang>.jsonl
    python scripts/build_dev_fixes.py merge   # join author + blind labels -> dev_fixes.csv, inputs/*.csv
    python scripts/build_dev_fixes.py leak    # drop exact/char duplicates of official + our_test (counts)
    python scripts/build_dev_fixes.py score --pred-dir <dir> --out <json>   # metrics on --debug outputs

The set is never used for training or calibration (data/dev_fixes/README.md).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "data" / "dev_fixes"
RAW = DEV / "raw"
LANGS = ("en", "ar", "az")
PERSONAS = ("A", "B")
CATEGORIES = ("Registration", "IT Support", "Finance", "Transportation", "Facilities", "Academic Support")
PRIORITIES = ("low", "medium", "high")
XFIELDS = ("kind", "deadline", "physical_danger", "account_compromise", "affected", "exam_impact")
COLUMNS = (
    "dev_id",
    "split",
    "lang",
    "persona",
    "block",
    "probe_type",
    "family",
    "text",
    "category",
    "priority",
    "author_category",
    "author_priority",
    "blind_category",
    "blind_priority",
    "agree_cat",
    "agree_pri",
    *(f"x_{f}" for f in XFIELDS),
    "scenario_id",
    "source",
    "needs_human_check",
)
SEED = 20261101


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_authored(raw: Path) -> list[dict[str, Any]]:
    """All authored rows with `lang` (en/ar/az) and `persona` (A/B) derived from the id."""
    rows: list[dict[str, Any]] = []
    for lang in LANGS:
        for p in PERSONAS:
            f = raw / f"authored_{lang.upper()}-{p}.jsonl"
            for r in read_jsonl(f):
                rows.append({**r, "lang": lang, "persona": p})
    return rows


def blind(raw: Path) -> dict[str, int]:
    """Write a shuffled id+text file per language; the labeller sees nothing else."""
    rng = random.Random(SEED)
    authored = load_authored(raw)
    counts: dict[str, int] = {}
    for lang in LANGS:
        rows = [{"id": r["id"], "text": r["text"]} for r in authored if r["lang"] == lang]
        rng.shuffle(rows)
        write_jsonl(raw / f"blind_input_{lang}.jsonl", rows)
        counts[lang] = len(rows)
    return counts


def _norm_label(value: Any, allowed: Sequence[str]) -> str:
    v = str(value or "").strip()
    return v if v in allowed else ""


def merge_rows(
    authored: Sequence[dict[str, Any]], blind_rows: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join author and blind labels. category/priority = author label where both agree, else empty,
    except probes whose labels are kept (the author label of the REAL issue). Rows are sorted by id."""
    by_id = {str(b["id"]): b for b in blind_rows}
    out: list[dict[str, Any]] = []
    for a in sorted(authored, key=lambda r: str(r["id"])):
        b = by_id.get(str(a["id"]), {})
        a_cat = _norm_label(a.get("category"), CATEGORIES)
        a_pri = _norm_label(a.get("priority"), PRIORITIES)
        b_cat = _norm_label(b.get("category"), CATEGORIES)
        b_pri = _norm_label(b.get("priority"), PRIORITIES)
        agree_cat = bool(a_cat) and a_cat == b_cat
        agree_pri = bool(a_pri) and a_pri == b_pri
        block = str(a["block"])
        keep = block == "probe"
        row: dict[str, Any] = {
            "dev_id": a["id"],
            "split": "tune" if a["persona"] == "A" else "check",
            "lang": a["lang"],
            "persona": a["persona"],
            "block": block,
            "probe_type": a.get("probe_type", ""),
            "family": a.get("family", ""),
            "text": a["text"],
            "category": a_cat if (agree_cat or keep) else "",
            "priority": a_pri if (agree_pri or keep) else "",
            "author_category": a.get("category", ""),
            "author_priority": a.get("priority", ""),
            "blind_category": b.get("category", ""),
            "blind_priority": b.get("priority", ""),
            "agree_cat": agree_cat,
            "agree_pri": agree_pri,
            "scenario_id": a["id"],
            "source": "llm_dev_fixes",
            "needs_human_check": True,
        }
        for f in XFIELDS:
            row[f"x_{f}"] = b.get(f, "")
        out.append(row)
    return out


def write_csv(path: Path, rows: Sequence[dict[str, Any]], cols: Sequence[str], bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_inputs(rows: Sequence[dict[str, Any]], out_dir: Path) -> list[str]:
    names = []
    for split in ("tune", "check"):
        for lang in LANGS:
            sub = [
                {"request_id": r["dev_id"], "text": r["text"]}
                for r in rows
                if r["split"] == split and r["lang"] == lang
            ]
            name = f"{split}_{lang}"
            write_csv(out_dir / f"{name}.csv", sub, ("request_id", "text"))
            names.append(name)
    return names


def agreement(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lang in (*LANGS, "all"):
        sub = [r for r in rows if lang == "all" or r["lang"] == lang]
        labelled_cat = [r for r in sub if r["author_category"] in CATEGORIES]
        labelled_pri = [r for r in sub if r["author_priority"] in PRIORITIES]
        high = [r for r in sub if r["priority"] == "high" and r["agree_pri"] in (True, "True")]
        imp = [r for r in sub if r["block"] == "implicit_urgency" and r["priority"]]
        out[lang] = {
            "rows": len(sub),
            "agree_cat": _rate(labelled_cat, "agree_cat"),
            "agree_pri": _rate(labelled_pri, "agree_pri"),
            "agreed_high": len(high),
            "implicit_with_agreed_priority": len(imp),
        }
    return out


def _rate(rows: Sequence[dict[str, Any]], key: str) -> float:
    return round(sum(r[key] in (True, "True") for r in rows) / len(rows), 4) if rows else 0.0


def merge(raw: Path, dev: Path) -> list[dict[str, Any]]:
    blind_rows: list[dict[str, Any]] = []
    for lang in LANGS:
        blind_rows += read_jsonl(raw / f"blind_{lang}.jsonl")
    rows = merge_rows(load_authored(raw), blind_rows)
    write_csv(dev / "dev_fixes.csv", rows, COLUMNS, bom=True)
    write_inputs(rows, dev / "inputs")
    return rows


# --- leakage ---------------------------------------------------------------------------------------------


def leak(dev: Path) -> dict[str, Any]:
    """Drop rows that equal (text_norm) or char-cosine >= leakage.char_cosine to an official or our_test row.
    Prints and returns counts only; never prints holdout text. Also reports e5 cosine >= 0.95 to our_test."""
    import numpy as np
    import yaml
    from sklearn.feature_extraction.text import TfidfVectorizer

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "services" / "ai"))
    import check_leakage as cl

    from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer

    cfg = yaml.safe_load(cl.DATASETS_YAML.read_text(encoding="utf-8"))["leakage"]
    train = yaml.safe_load(cl.TRAIN_YAML.read_text(encoding="utf-8"))
    norm = DefaultNormalizer.from_lexicons(cl.LEXICONS, int(train["guards"]["max_tokens"]))
    rows = read_csv(dev / "dev_fixes.csv")
    dn = [norm.normalize(r["text"]) for r in rows]
    dev_norm = [d.text_norm for d in dn]
    official = [r["text_norm"] for r in read_csv(cl.COMBINED)]
    ours = cl._read_holdout(cl.OUR_TEST_CSV, norm)
    ours_norm = ours["text_norm"].astype(str).tolist()
    char_t = float(cfg["char_cosine"])
    tf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit(
        official + ours_norm + dev_norm
    )
    dv = tf.transform(dev_norm)
    drop: dict[str, str] = {}
    counts = {"exact_official": 0, "char_official": 0, "exact_our_test": 0, "char_our_test": 0}
    for name, pool in (("official", official), ("our_test", ours_norm)):
        pset = set(pool)
        sims = (dv @ tf.transform(pool).T).toarray()
        for i, r in enumerate(rows):
            if dev_norm[i] in pset:
                counts[f"exact_{name}"] += 1
                drop.setdefault(r["dev_id"], f"exact_{name}")
            elif float(sims[i].max()) >= char_t:
                counts[f"char_{name}"] += 1
                drop.setdefault(r["dev_id"], f"char_{name}")
    enc = cl._encoder("onnx")
    e_dev = cl._embed(enc, [d.model_text for d in dn])
    e_our = cl._embed(enc, ours["model_text"].astype(str).tolist())
    esim = np.asarray(e_dev, dtype=np.float64) @ np.asarray(e_our, dtype=np.float64).T
    e5_hits = int((esim.max(axis=1) >= 0.95).sum())
    kept = [r for r in rows if r["dev_id"] not in drop]
    for r in kept:
        r["agree_cat"] = r["agree_cat"] == "True"
        r["agree_pri"] = r["agree_pri"] == "True"
    write_csv(dev / "dev_fixes.csv", kept, COLUMNS, bom=True)
    write_inputs(kept, dev / "inputs")
    report = {
        "rows_in": len(rows),
        "dropped": len(drop),
        "dropped_ids": sorted(drop),
        "reasons": counts,
        "e5_ge_0.95_to_our_test_reported_not_dropped": e5_hits,
        "char_threshold": char_t,
    }
    (dev / "leakage_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "dropped_ids"}))
    return report


# --- scoring ---------------------------------------------------------------------------------------------


def _split_flags(value: str) -> set[str]:
    return {f.strip() for f in value.replace(";", ",").replace("|", ",").split(",") if f.strip()}


def bucket(n: int) -> str:
    return "0" if n == 0 else "1" if n == 1 else "2" if n == 2 else ">=3"


def score_rows(dev_rows: Sequence[dict[str, str]], preds: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Metrics per lang x split x block (+ 'all' blocks), routing buckets, flag rates, family high recall.
    Category/priority metrics use only rows whose agreed label is present and in the label set."""
    from campuspulse_ai.adapters.training.metrics import accuracy, macro_f1

    joined = [(r, preds[r["dev_id"]]) for r in dev_rows if r["dev_id"] in preds]
    out: dict[str, Any] = {"n_scored": len(joined)}
    cells: dict[str, Any] = {}
    langs = [*LANGS, "all"]
    for lang in langs:
        for split in ("tune", "check", "all"):
            for block in ("headline", "implicit_urgency", "probe", "all"):
                sub = [
                    (r, p)
                    for r, p in joined
                    if (lang == "all" or r["lang"] == lang)
                    and (split == "all" or r["split"] == split)
                    and (block == "all" or r["block"] == block)
                ]
                cell: dict[str, Any] = {"n": len(sub)}
                for field, labels in (("category", CATEGORIES), ("priority", PRIORITIES)):
                    pairs = [(r[field], p[field]) for r, p in sub if r[field] in labels]
                    y = [a for a, _ in pairs]
                    yh = [b for _, b in pairs]
                    cell[field] = {
                        "n": len(pairs),
                        "macro_f1": round(macro_f1(y, yh, labels), 4) if pairs else None,
                        "accuracy": round(accuracy(y, yh), 4) if pairs else None,
                    }
                cells[f"{lang}/{split}/{block}"] = cell
    out["cells"] = cells
    for key, col in (("routing_category", "set_cat"), ("routing_priority", "set_pri")):
        buckets: dict[str, dict[str, int]] = {}
        for lang in langs:
            c: dict[str, int] = defaultdict(int)
            for r, p in joined:
                if lang == "all" or r["lang"] == lang:
                    c[bucket(int(float(p.get(col) or 0)))] += 1
            buckets[lang] = dict(c)
        out[key] = buckets
    flags: dict[str, Any] = {}
    for lang in langs:
        sub_p = [p for r, p in joined if lang == "all" or r["lang"] == lang]
        names = sorted({f for p in sub_p for f in _split_flags(p.get("flags", ""))})
        flags[lang] = (
            {
                n: round(sum(n in _split_flags(p.get("flags", "")) for p in sub_p) / len(sub_p), 4)
                for n in names
            }
            if sub_p
            else {}
        )
    out["flag_rates"] = flags
    fam: dict[str, Any] = {}
    for lang in langs:
        per: dict[str, Any] = {}
        for family in sorted({r["family"] for r, _ in joined if r["family"]} | {"__all_high__"}):
            sub = [
                (r, p)
                for r, p in joined
                if (lang == "all" or r["lang"] == lang)
                and r["priority"] == "high"
                and (family == "__all_high__" or r["family"] == family)
            ]
            if sub:
                hit = sum(p["priority"] == "high" for _, p in sub)
                per[family] = {"n": len(sub), "high_recall": round(hit / len(sub), 4)}
        fam[lang] = per
    out["family_high_recall"] = fam
    return out


def score(pred_dir: Path, dev: Path) -> dict[str, Any]:
    dev_rows = read_csv(dev / "dev_fixes.csv")
    preds: dict[str, dict[str, str]] = {}
    for f in sorted(pred_dir.glob("*.csv")):
        for r in read_csv(f):
            preds[r["request_id"]] = r
    return score_rows(dev_rows, preds)


def metrics_md(name: str, m: dict[str, Any]) -> str:
    lines = [
        f"### {name}",
        "",
        "| lang | split | block | n | cat F1 | cat acc | pri F1 | pri acc |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for k, c in m["cells"].items():
        lang, split, block = k.split("/")
        if c["n"] == 0:
            continue
        f = lambda x: "-" if x is None else f"{x:.3f}"  # noqa: E731
        lines.append(
            f"| {lang} | {split} | {block} | {c['n']} | {f(c['category']['macro_f1'])} | "
            f"{f(c['category']['accuracy'])} | {f(c['priority']['macro_f1'])} | "
            f"{f(c['priority']['accuracy'])} |"
        )
    lines += [
        "",
        "Routing (set sizes, all languages): category "
        + json.dumps(m["routing_category"]["all"])
        + "; priority "
        + json.dumps(m["routing_priority"]["all"]),
        "",
        "Flag rates (all): " + json.dumps(m["flag_rates"].get("all", {})),
        "",
        "High recall per family (all): " + json.dumps(m["family_high_recall"].get("all", {})),
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("blind")
    sub.add_parser("merge")
    sub.add_parser("leak")
    sc = sub.add_parser("score")
    sc.add_argument("--pred-dir", type=Path, action="append", required=True)
    sc.add_argument("--name", action="append")
    sc.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "blind":
        print(blind(RAW))
    elif a.cmd == "merge":
        rows = merge(RAW, DEV)
        (DEV / "agreement.json").write_text(json.dumps(agreement(rows), indent=2), encoding="utf-8")
        print(json.dumps(agreement(rows)["all"]))
    elif a.cmd == "leak":
        leak(DEV)
    else:
        sys.path.insert(0, str(ROOT / "services" / "ai"))
        names = a.name or [p.name for p in a.pred_dir]
        res = {n: score(p, DEV) for n, p in zip(names, a.pred_dir, strict=True)}
        a.out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        a.out.with_suffix(".md").write_text(
            "\n".join(metrics_md(n, m) for n, m in res.items()), encoding="utf-8"
        )
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
