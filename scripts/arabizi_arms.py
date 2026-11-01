#!/usr/bin/env python3
# ruff: noqa: E501
"""P2.16 Arabizi experiment, arm B: train on Arabizi rows (encoded as today, untranslated) vs rc3 (arm A).

    python scripts/arabizi_arms.py [--boot 2000] [--out reports/arabizi_arms.json]

The official data has no Arabizi row, so the rc3 model never trained on one. Arm B adds the existing unreviewed
LLM-written Arabizi rows (`data/augmented/{arabizi,new_scenarios,paraphrases,translations,
arabizi_from_official}.csv`, `lang == arabizi` only; an unreviewed MEASUREMENT arm, never frozen). The same rc3
recipe and the same scenario-held-out folds are used (`make_folds.py --include-augmented` gives the new groups
a fold; official groups do not move). Two B variants: B1 drops every augmented row whose e5 cosine to an
our_test row is >= 0.90 (`check_leakage.py` `review_augmented_ids`); B2 keeps them (transparency).

Arm A on the Arabizi rows: the same folds with Arabizi rows kept out of every training fold (they are only
scored), so A and B are scored on identical rows. Arm A on our_test and official OOF is the plain rc3 pipeline.

Arabizi measurements: (a) our_test Arabizi rows; (b) OOF on the `arabizi_from_official` rows (grouped by their
inherited cv_group); (c) OOF on the new-scenario and `arabizi.csv` rows. The conformal coverage of OOF rows is
circular (the per-language quantile is calibrated on those same rows), so only our_test coverage is a test.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

import campuspulse_ai.adapters.training.oof as oof_mod
from campuspulse_ai.adapters.models.encoder import CachingEncoder
from campuspulse_ai.adapters.training.metrics import macro_f1, paired_group_bootstrap
from campuspulse_ai.adapters.training.oof import PipelineToggles, run_cv
from campuspulse_ai.adapters.training.pool import AUGMENTED_COLUMNS, OFFICIAL_CSV
from campuspulse_ai.adapters.training.stages import EncoderInfo, freeze, stage_b
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.composition.evaluation import (
    ENSEMBLE,
    LABELS,
    Row,
    coverage_rows,
    load_eval_cfg,
    oof_rows,
    our_test_rows,
)
from campuspulse_ai.composition.offline import build_offline
from campuspulse_ai.composition.training import TrainOptions, make_encoder, make_kit, make_pool
from campuspulse_ai.config.paths import DATA_AUGMENTED, LEXICONS, MODELS_FROZEN, REPORTS
from campuspulse_ai.config.settings import Settings

ARABIZI_FILES = ("arabizi", "new_scenarios", "paraphrases", "translations", "arabizi_from_official")
LEAK_JSON = Path("reports/arabizi_leakage.json")


def arabizi_rows() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name in ARABIZI_FILES:
        with (DATA_AUGMENTED / f"{name}.csv").open(encoding="utf-8-sig", newline="") as f:
            out += [dict(r) for r in csv.DictReader(f) if r["lang"] == "arabizi"]
    return out


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(AUGMENTED_COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def run_arm(
    name: str,
    paths: tuple[Path, ...],
    folds: Path,
    enc: Any,
    cfg: TrainCfg,
    settings: Settings,
    info: EncoderInfo,
    *,
    score_test: bool,
    hide_arabizi_from_training: bool = False,
) -> tuple[list[Row], list[Row]]:
    toggles = PipelineToggles(include_unreviewed=True)
    opts = TrainOptions(cv_only=True, toggles=toggles, folds_csv=folds, data=paths)
    pool, normalizer = make_pool(opts, cfg)
    kit = make_kit(cfg, LEXICONS, normalizer, enc)
    original = oof_mod.group_folds
    if hide_arabizi_from_training:
        arabizi = np.asarray([str(x) == "arabizi" for x in pool.lang])

        def patched(p: Any, k: int) -> Any:
            return [(tr[~arabizi[tr]], te) for tr, te in original(p, k)]

        oof_mod.group_folds = patched
    try:
        oof = run_cv(pool, enc, cfg, toggles, kit, nested=False)
    finally:
        oof_mod.group_folds = original
    tuned = stage_b(oof, cfg, enc, LEXICONS)
    with tempfile.TemporaryDirectory(prefix=f"cp_az_{name}_") as tmp:
        out = Path(tmp) / "v1"
        freeze(out, oof, tuned, cfg, kit, enc, info, LEXICONS)
        container = build_offline(out, encoder_override=enc, settings=settings)
        oof_r = oof_rows(out, container.config)
        test_r = our_test_rows(container) if score_test else []
    print(f"arm {name}: {len(pool)} pool rows done", flush=True)
    return oof_r, test_r


def f1(rows: Sequence[Row], target: str = "category") -> float | None:
    if not rows:
        return None
    t = 0 if target == "category" else 1
    return round(
        macro_f1(
            [getattr(r, target) for r in rows], [str(r.pred[ENSEMBLE][t]) for r in rows], LABELS[target]
        ),
        4,
    )


def paired(
    base: Sequence[Row], cand: Sequence[Row], boot: dict[str, Any], target: str = "category"
) -> dict[str, float]:
    b = {r.request_id: r for r in base}
    c = {r.request_id: r for r in cand}
    ids = sorted(set(b) & set(c))
    t = 0 if target == "category" else 1
    comp = paired_group_bootstrap(
        [getattr(b[i], target) for i in ids],
        [str(b[i].pred[ENSEMBLE][t]) for i in ids],
        [str(c[i].pred[ENSEMBLE][t]) for i in ids],
        [b[i].group for i in ids],
        LABELS[target],
        resamples=int(boot["resamples"]),
        seed=int(boot["seed"]),
        low_pct=float(boot["low_pct"]),
        high_pct=float(boot["high_pct"]),
    )
    return {k: round(float(v), 4) for k, v in comp.items()} | {
        "n": len(ids),
        "n_groups": len({b[i].group for i in ids}),
    }


def cov(rows: Sequence[Row]) -> dict[str, Any] | None:
    cr = [c for c in coverage_rows([("x", list(rows))]) if c["target"] == "category" and c["lang"] == "all"]
    return {k: cr[0][k] for k in ("coverage", "mean_set_size", "n_rows")} if cr else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--out", default=str(REPORTS / "arabizi_arms.json"))
    ap.add_argument("--folds", required=True, help="make_folds.py --include-augmented output")
    ap.add_argument("--leakage", required=True, help="check_leakage.py --out json")
    args = ap.parse_args()
    cfg = TrainCfg.load()
    settings = Settings()
    boot = dict(load_eval_cfg()["bootstrap"])
    boot["resamples"] = args.boot
    folds = Path(args.folds)
    near = set(json.loads(Path(args.leakage).read_text(encoding="utf-8"))["review_augmented_ids"])
    rows_all = arabizi_rows()
    kept = [r for r in rows_all if r["request_id"] not in near]
    print(
        f"arabizi rows {len(rows_all)}; with an our_test neighbour >= 0.90: {len(rows_all) - len(kept)}; kept {len(kept)}"
    )
    enc0, _ = make_encoder(TrainOptions(cv_only=True, out=MODELS_FROZEN / "v1"), cfg, settings)
    info = EncoderInfo(enc0.model_id, getattr(enc0, "revision", "none"), "onnx_int8", ())
    enc = CachingEncoder(enc0)
    tmp = Path(tempfile.mkdtemp(prefix="cp_az_data_"))
    p_all, p_kept = tmp / "az_all.csv", tmp / "az_kept.csv"
    write_csv(p_all, rows_all)
    write_csv(p_kept, kept)
    kept_ids = {r["request_id"] for r in kept}
    a_oof_az, _ = run_arm(
        "A_arabizi_scored",
        (OFFICIAL_CSV, p_all),
        folds,
        enc,
        cfg,
        settings,
        info,
        score_test=False,
        hide_arabizi_from_training=True,
    )
    a_oof, a_test = run_arm("A", (OFFICIAL_CSV,), folds, enc, cfg, settings, info, score_test=True)
    b1_oof, b1_test = run_arm("B1", (OFFICIAL_CSV, p_kept), folds, enc, cfg, settings, info, score_test=True)
    b2_oof, b2_test = run_arm("B2", (OFFICIAL_CSV, p_all), folds, enc, cfg, settings, info, score_test=True)

    def split(rows: Sequence[Row]) -> dict[str, list[Row]]:
        az = [r for r in rows if r.lang == "arabizi" and r.subset == "augmented"]
        return {
            "b_from_official": [r for r in az if r.request_id.startswith("AUG-AO-")],
            "c_new_and_rule": [
                r for r in az if r.request_id.startswith(("AUG-NC-", "AUG-AZ-")) and r.request_id in kept_ids
            ],
            "c_new_and_rule_all": [r for r in az if r.request_id.startswith(("AUG-NC-", "AUG-AZ-"))],
        }

    result: dict[str, Any] = {
        "n_arabizi_rows": len(rows_all),
        "n_near_our_test": len(rows_all) - len(kept),
        "n_kept": len(kept),
        "bootstrap": boot,
        "arms": {},
    }
    sa = split(a_oof_az)
    for name, oof_r, test_r in (("B1", b1_oof, b1_test), ("B2", b2_oof, b2_test)):
        sb = split(oof_r)
        entry: dict[str, Any] = {}
        # (a) our_test
        for lang in ("arabizi", "en", "ar", "all"):
            ra = [r for r in a_test if lang == "all" or r.lang == lang]
            rb = [r for r in test_r if lang == "all" or r.lang == lang]
            entry[f"a_our_test_{lang}"] = {
                "A": f1(ra),
                name: f1(rb),
                "cov_A": cov(ra),
                f"cov_{name}": cov(rb),
                "delta": paired(ra, rb, boot) if ra else None,
            }
        # (b), (c): the A rows are the A_arabizi_scored run
        for key in ("b_from_official", "c_new_and_rule", "c_new_and_rule_all"):
            ids = {r.request_id for r in sb[key]}
            ra = [r for r in sa[key] if r.request_id in ids]
            rb = sb[key]
            entry[key] = {
                "A": f1(ra),
                name: f1(rb),
                "cov_A": cov(ra),
                f"cov_{name}": cov(rb),
                "delta": paired(ra, rb, boot) if ra else None,
            }
        # slices: official OOF EN / AR / all (must not drop > 0.03)
        for lang in ("en", "ar", "all"):
            ra = [r for r in a_oof if r.subset == "official" and (lang == "all" or r.lang == lang)]
            rb = [r for r in oof_r if r.subset == "official" and (lang == "all" or r.lang == lang)]
            entry[f"oof_official_{lang}"] = {"A": f1(ra), name: f1(rb), "delta": paired(ra, rb, boot)}
        for target in ("priority",):
            entry["our_test_priority_all"] = {"A": f1(a_test, target), name: f1(test_r, target)}
        result["arms"][name] = entry
    out = Path(args.out)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
