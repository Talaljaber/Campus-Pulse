#!/usr/bin/env python3
"""P2.17 arm C: translate Arabizi through its Arabic-letter transliteration (`docs/ml/models.md` §28).

    python scripts/arabizi_translit_arm.py study   [--out reports/arabizi_translit_study.json]
    python scripts/arabizi_translit_arm.py arms    [--boot 2000] [--out reports/arabizi_translit_arm.json]
    python scripts/arabizi_translit_arm.py latency [--arabizi 0|1]

`study` runs the existing Arabizi rows (`data/augmented/arabizi.csv`, the Arabizi rows of `new_scenarios.csv`)
through three translation routes (raw, joined `transliteration | original`, transliteration only) and counts
decoder loops, copy-throughs and dropped content.

`arms` trains the rc3 recipe (same code path as `translate_test.py arms`) on official rows plus the Arabizi
rows (arabizi.csv, new-scenario Arabizi rows whose e5 cosine to every our_test row is < 0.90,
arabizi_from_official.csv), with the encoder wrapper's `translate_arabizi` on at train and test time, and
scores Arabizi three ways: our_test Arabizi, scenario-grouped OOF over the Arabizi-from-official rows, and
OOF over the other Arabizi rows. The baseline is the frozen rc3 model (official rows only): the source
scenarios of the Arabizi-from-official rows are in its training set, which favours the baseline.
Everything it writes stays outside `models/frozen/` and `data/`; nothing is frozen or shipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from campuspulse_ai.adapters.models.encoder import CachingEncoder
from campuspulse_ai.adapters.models.translating_encoder import TranslatingEncoder, arabic_ratio
from campuspulse_ai.adapters.models.translator import Ct2Translator
from campuspulse_ai.adapters.preprocess.arabizi import ArabiziTransliterator
from campuspulse_ai.adapters.training.oof import PipelineToggles, run_cv
from campuspulse_ai.adapters.training.pool import AUGMENTED_COLUMNS, FOLDS_CSV, OFFICIAL_CSV
from campuspulse_ai.adapters.training.stages import EncoderInfo, freeze, stage_b
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.adapters.training.translation_cache import CsvCachedTranslator
from campuspulse_ai.composition.evaluation import (
    ENSEMBLE,
    LANGS,
    OUR_TEST_CSV,
    Row,
    _read,
    core_rows,
    coverage_rows,
    load_eval_cfg,
    oof_rows,
    our_test_rows,
)
from campuspulse_ai.composition.offline import build_offline
from campuspulse_ai.composition.training import TrainOptions, make_encoder, make_kit, make_pool
from campuspulse_ai.config.paths import DATA_AUGMENTED, LEXICONS, MODELS_FROZEN, REPORTS
from campuspulse_ai.config.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_test import _f1, _paired  # noqa: E402

TRANSLATOR_DIR = MODELS_FROZEN / "v1" / "translator"
RC3_CACHE = REPORTS / "translate_test" / "translations.csv"
MT = ("Helsinki-NLP/opus-mt-ar-en", "c5b2a50db78d6be98ae207223f8d4f63bc7a0ff1")
DUP_COSINE = 0.90
SCRATCH = Path(tempfile.gettempdir()) / "cp_arabizi_arm_c"  # `arms --tag` adds a suffix
_TOK = re.compile(r"\w+", re.U)


def _arabizi_rows(name: str) -> list[dict[str, str]]:
    with (DATA_AUGMENTED / name).open(encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r["lang"] == "arabizi"]


# --- translation-quality study ---------------------------------------------------------------------------


def _loops(s: str) -> bool:
    w = s.split()
    if re.search(r"♪|(\. ){3,}|(.{1,12})\1{3,}", s):
        return True
    return any(w[i] == w[i + 1] == w[i + 2] for i in range(len(w) - 2))


def _copies(inp: str, out: str) -> bool:
    a = {t.lower() for t in _TOK.findall(inp) if re.search("[A-Za-z]", t)}
    b = {t.lower() for t in _TOK.findall(out)}
    return bool(a) and len(a & b) / len(a) >= 0.5


def _drops(inp: str, out: str) -> bool:
    return len(out.split()) < max(2, 0.4 * len(inp.split()))


def cmd_study(args: argparse.Namespace) -> int:
    from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer

    norm = DefaultNormalizer.from_lexicons(LEXICONS, 256)
    translit = ArabiziTransliterator.from_yaml(LEXICONS / "arabizi.yaml")
    mt = Ct2Translator(TRANSLATOR_DIR, cache_size=0)
    rows = _arabizi_rows("arabizi.csv") + _arabizi_rows("new_scenarios.csv")
    recs = []
    for r in rows:
        req = norm.normalize(r["text"])
        t_in = translit.transliterate(req.text_norm)
        recs.append({"id": r["request_id"], "raw": r["text"], "translit": t_in, "joined": req.model_text})
        for k in ("raw", "translit", "joined"):
            recs[-1]["t_" + k] = mt.translate([recs[-1][k]])[0]
    summary: dict[str, Any] = {
        "n": len(recs),
        "joined_passes_rc3_gate": sum(arabic_ratio(x["joined"]) >= 0.3 for x in recs),
    }
    for k in ("raw", "joined", "translit"):
        loops = sum(_loops(x["t_" + k]) for x in recs)
        copy = sum(_copies(x["raw"], x["t_" + k]) for x in recs)
        drop = sum(_drops(x[k], x["t_" + k]) for x in recs)
        clean = sum(
            not (_loops(x["t_" + k]) or _copies(x["raw"], x["t_" + k]) or _drops(x[k], x["t_" + k]))
            for x in recs
        )
        summary[k] = {"loop": loops, "copy": copy, "drop": drop, "clean": clean}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"summary": summary, "rows": recs}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=1))
    return 0


# --- arm C ------------------------------------------------------------------------------------------------


def _near_duplicates(encoder: Any, texts: list[str], cutoff: float) -> list[bool]:
    """True where the e5 cosine to some our_test row is >= 0.90 (the rows are encoded, never printed)."""
    ours = np.asarray(encoder.encode([r["text"] for r in _read(OUR_TEST_CSV)]), dtype=np.float64)
    mine = np.asarray(encoder.encode(texts), dtype=np.float64)
    ours /= np.linalg.norm(ours, axis=1, keepdims=True)
    mine /= np.linalg.norm(mine, axis=1, keepdims=True)
    return [bool(v >= cutoff) for v in (mine @ ours.T).max(axis=1)]


def _write_train_files(base: Any, k: int, cutoff: float) -> tuple[Path, Path, dict[str, Any]]:
    """The Arabizi training CSV and a folds CSV that places the new-scenario groups."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sets = {n: _arabizi_rows(n) for n in ("arabizi.csv", "new_scenarios.csv", "arabizi_from_official.csv")}
    dup = _near_duplicates(base, [r["text"] for r in sets["new_scenarios.csv"]], cutoff)
    dropped = [r["request_id"] for r, d in zip(sets["new_scenarios.csv"], dup, strict=True) if d]
    keep = [r for r, d in zip(sets["new_scenarios.csv"], dup, strict=True) if not d]
    rows = sets["arabizi.csv"] + keep + sets["arabizi_from_official.csv"]
    data = SCRATCH / "arabizi_train.csv"
    with data.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(AUGMENTED_COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows({c: r[c] for c in AUGMENTED_COLUMNS} for r in rows)
    with FOLDS_CSV.open(encoding="utf-8", newline="") as fh:
        folds = list(csv.DictReader(fh))
    known = {r["cv_group"] for r in folds}
    new_groups = sorted({r["cv_group"] for r in rows} - known)
    folds_csv = SCRATCH / "cv_folds_arabizi.csv"
    with folds_csv.open("w", encoding="utf-8", newline="") as fh:
        w2 = csv.writer(fh, lineterminator="\n")
        w2.writerow(["cv_group", "cv_fold"])
        for r in folds:
            w2.writerow([r["cv_group"], r["cv_fold"]])
        for i, g in enumerate(new_groups):
            w2.writerow([g, i % k])
    info = {
        "arabizi_csv": len(sets["arabizi.csv"]),
        "new_scenario_kept": len(keep),
        "new_scenario_dropped_near_dup": len(dropped),
        "from_official": len(sets["arabizi_from_official.csv"]),
        "ids_from_official": [r["request_id"] for r in sets["arabizi_from_official.csv"]],
        "ids_other": [r["request_id"] for r in sets["arabizi.csv"] + keep],
        "texts": {r["request_id"]: r["text"] for r in rows},
        "groups": {r["request_id"]: r["cv_group"] for r in rows},
    }
    return data, folds_csv, info


def _score(rows: list[Row], base: list[Row], boot: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows), "groups": len({r.group for r in rows})}
    for target in ("category", "priority"):
        out[target] = {"base": _f1(base, target), "arm": _f1(rows, target)}
        out[target]["paired"] = _paired(base, rows, target, boot) if rows else None
    cov = {c["target"]: c for c in coverage_rows([("x", rows)]) if c["lang"] == "all"} if rows else {}
    cov_b = {c["target"]: c for c in coverage_rows([("x", base)]) if c["lang"] == "all"} if base else {}
    for target in ("category", "priority"):
        out[target]["coverage_arm"] = (cov.get(target) or {}).get("coverage")
        out[target]["set_size_arm"] = (cov.get(target) or {}).get("mean_set_size")
        out[target]["coverage_base"] = (cov_b.get(target) or {}).get("coverage")
        out[target]["set_size_base"] = (cov_b.get(target) or {}).get("mean_set_size")
    return out


def cmd_arms(args: argparse.Namespace) -> int:
    global SCRATCH
    SCRATCH = SCRATCH.with_name(SCRATCH.name + args.tag)
    cfg = TrainCfg.load()
    settings = Settings()
    boot = dict(load_eval_cfg()["bootstrap"])
    boot["resamples"] = args.boot
    onnx, _ = make_encoder(TrainOptions(cv_only=True, out=MODELS_FROZEN / "v1"), cfg, settings)
    base = CachingEncoder(onnx)
    data, folds_csv, info = _write_train_files(base, cfg.k, args.dup_cos)
    cache_path = SCRATCH / "translations.csv"
    if not cache_path.is_file():
        shutil.copy(RC3_CACHE, cache_path)
    cached = CsvCachedTranslator(cache_path, Ct2Translator(TRANSLATOR_DIR, cache_size=0), *MT)
    arm_enc = TranslatingEncoder(base, cached, 0.3, translate_arabizi=bool(args.flag))

    toggles = PipelineToggles(include_unreviewed=True)  # CV-only: rows still unchecked
    opts = TrainOptions(
        cv_only=True, toggles=toggles, folds_csv=folds_csv, data=(OFFICIAL_CSV, data)
    )
    pool, normalizer = make_pool(opts, cfg)
    kit = make_kit(cfg, LEXICONS, normalizer, arm_enc)
    oof = run_cv(pool, arm_enc, cfg, toggles, kit, nested=False)
    tuned = stage_b(oof, cfg, arm_enc, LEXICONS)
    cached.save()
    out_dir = SCRATCH / "v1_armc"
    shutil.rmtree(out_dir, ignore_errors=True)
    info_enc = EncoderInfo(onnx.model_id, onnx.revision, "onnx_int8", ())
    freeze(out_dir, oof, tuned, cfg, kit, arm_enc, info_enc, LEXICONS)
    container = build_offline(out_dir, encoder_override=arm_enc, settings=settings)
    arm_oof = oof_rows(out_dir, container.config)
    for r in arm_oof:
        r.text = info["texts"].get(r.request_id, r.text)
    arm_test = our_test_rows(container)

    rc3 = build_offline(MODELS_FROZEN / "v1", settings=settings)
    base_oof = [r for r in oof_rows(MODELS_FROZEN / "v1", rc3.config) if r.subset == "official"]
    base_test = our_test_rows(rc3)
    items = [
        {"request_id": rid, "text": info["texts"][rid], "lang": "arabizi", "g": info["groups"][rid],
         "subset": "augmented", "category": c, "priority": p}
        for rid, c, p in _labels(data)
    ]
    base_az = core_rows(
        rc3, items, "oof", subset_key="subset", group_key="g", cat_key="category", pri_key="priority"
    )
    by_id = {r.request_id: r for r in arm_oof}

    def arm_of(ids: list[str]) -> list[Row]:
        return [by_id[i] for i in ids if i in by_id]

    def base_of(ids: list[str]) -> list[Row]:
        s = set(ids)
        return [r for r in base_az if r.request_id in s]

    res: dict[str, Any] = {"data": {k: v for k, v in info.items() if not isinstance(v, (dict, list))}}
    res["a_our_test_arabizi"] = _score(
        [r for r in arm_test if r.lang == "arabizi"], [r for r in base_test if r.lang == "arabizi"], boot
    )
    ids_b = info["ids_from_official"]
    res["b_from_official_oof"] = _score(arm_of(ids_b), base_of(ids_b), boot)
    res["c_other_arabizi_oof"] = _score(arm_of(info["ids_other"]), base_of(info["ids_other"]), boot)
    arm_off = [r for r in arm_oof if r.subset == "official"]
    slices: dict[str, Any] = {}
    for name, a, b in (("oof_official", arm_off, base_oof), ("our_test", arm_test, base_test)):
        for lang in ("all", *LANGS):
            ra = [r for r in a if lang == "all" or r.lang == lang]
            rb = [r for r in b if lang == "all" or r.lang == lang]
            if ra and rb:
                fa, fb = _f1(ra, "category"), _f1(rb, "category")
                slices[f"{name}/{lang}"] = {
                    "n": len(ra), "base": fb, "arm": fa, "delta": round(float(fa or 0) - float(fb or 0), 4),
                    "paired": _paired(rb, ra, "category", boot),
                }
    res["slices_category_f1"] = slices
    res["bootstrap"] = boot
    res["flag_translate_arabizi"] = bool(args.flag)
    res["dup_cos"] = args.dup_cos
    res["rows"] = {
        name: {
            "arm": [[r.request_id, r.group, r.category, str(r.pred[ENSEMBLE][0])] for r in arm_rows],
            "base": [[r.request_id, r.group, r.category, str(r.pred[ENSEMBLE][0])] for r in base_rows],
        }
        for name, arm_rows, base_rows in (
            ("a", [r for r in arm_test if r.lang == "arabizi"], [r for r in base_test if r.lang == "arabizi"]),
            ("b", arm_of(ids_b), base_of(ids_b)),
            ("c", arm_of(info["ids_other"]), base_of(info["ids_other"])),
        )
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=2, ensure_ascii=False))
    return 0


def _labels(path: Path) -> list[tuple[str, str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [(r["request_id"], r["category"], r["priority"]) for r in csv.DictReader(fh)]


# --- cost -------------------------------------------------------------------------------------------------


def cmd_latency(args: argparse.Namespace) -> int:
    import psutil

    settings = Settings()
    proc = psutil.Process()
    before = proc.memory_info().rss / 2**20
    if args.arabizi:
        cfg = TrainCfg.load()
        onnx, _ = make_encoder(TrainOptions(cv_only=True, out=MODELS_FROZEN / "v1"), cfg, settings)
        enc = TranslatingEncoder(onnx, Ct2Translator(TRANSLATOR_DIR, threads=1), 0.3, translate_arabizi=True)
        container = build_offline(MODELS_FROZEN / "v1", settings=settings, encoder_override=enc)
    else:
        container = build_offline(MODELS_FROZEN / "v1", settings=settings)
    rows = _arabizi_rows("new_scenarios.csv")[:60]
    lat: list[float] = []
    for r in rows:
        t0 = time.perf_counter()
        container.core.classify_many([r["text"]], memory=False)
        lat.append((time.perf_counter() - t0) * 1000)
    after = proc.memory_info().rss / 2**20
    lat.sort()
    print(json.dumps({
        "arabizi_translit": bool(args.arabizi), "n": len(lat), "rss_before_mb": round(before),
        "rss_after_mb": round(after), "p50_ms": round(statistics.median(lat)),
        "p95_ms": round(lat[int(0.95 * (len(lat) - 1))]),
    }))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("study")
    s.add_argument("--out", default=str(REPORTS / "arabizi_translit_study.json"))
    s.set_defaults(fn=cmd_study)
    a = sub.add_parser("arms")
    a.add_argument("--boot", type=int, default=2000)
    a.add_argument("--flag", type=int, choices=(0, 1), default=1, help="translate_arabizi (0 = control)")
    a.add_argument("--dup-cos", type=float, default=DUP_COSINE)
    a.add_argument("--tag", default="")
    a.add_argument("--out", default=str(REPORTS / "arabizi_translit_arm.json"))
    a.set_defaults(fn=cmd_arms)
    lt = sub.add_parser("latency")
    lt.add_argument("--arabizi", type=int, choices=(0, 1), default=1)
    lt.set_defaults(fn=cmd_latency)
    args = p.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
