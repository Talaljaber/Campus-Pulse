"""`run_training`: the composition root of `train.py` (P1.16, ARCHITECTURE §3.4).

Wires the training pool, the frozen encoder (ONNX int8, or the test `HashingEncoder`), the lexicon-based
evidence and safety components, then runs stage A (OOF), provisional stage B and, unless `cv_only`, stage C
(freeze). It never reads `data/our_test` or `data/robustness`: `load_pool` refuses holdout paths.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from campuspulse_ai.adapters.guards.bank import compile_bank
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.models.encoder import CachingEncoder, OnnxEncoder, read_encoder_meta
from campuspulse_ai.adapters.models.evidence import LexiconEvidenceExtractor
from campuspulse_ai.adapters.models.hashing_encoder import HashingEncoder
from campuspulse_ai.adapters.models.soft_targets import SoftTargetExpander
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.oof import PipelineToggles, TrainingKit, run_cv
from campuspulse_ai.adapters.training.pool import FEATURES_CSV, FOLDS_CSV, default_pool_paths, load_pool
from campuspulse_ai.adapters.training.stages import EncoderInfo, cv_report, freeze, stage_b
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.config.paths import DATA_CLEAN, LEXICONS, MODELS_FROZEN, REPORTS
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactVersionMismatch
from campuspulse_ai.domain.ports import SentenceEncoder

EncoderKind = Literal["onnx", "hashing"]
LABEL_FLAGS_CSV = DATA_CLEAN / "label_flags.csv"


@dataclass(frozen=True)
class TrainOptions:
    out: Path = MODELS_FROZEN / "v1"
    report: Path = REPORTS / "cv_p1.json"
    cv_only: bool = False
    fast: bool = False  # reserved: skips the stage-B grids once P2.7 adds them (no grid runs in P1)
    retune: bool = False  # reserved for P2/P6 (re-read hand_tuned.yaml; P1 always reads it)
    encoder: EncoderKind = "onnx"
    data: tuple[Path, ...] = ()  # default: data/clean/train_val_combined.csv + data/augmented/*.csv
    folds_csv: Path = FOLDS_CSV
    features_csv: Path = FEATURES_CSV
    lexicon_dir: Path = LEXICONS
    toggles: PipelineToggles = field(default_factory=PipelineToggles)


@dataclass(frozen=True)
class TrainOutcome:
    report: dict[str, Any]
    summary: str
    manifest_sha: str | None


def _encoder(opts: TrainOptions, cfg: TrainCfg, settings: Settings) -> tuple[SentenceEncoder, EncoderInfo]:
    enc_cfg = cfg.section("encoder")
    if opts.encoder == "hashing":
        hashing = HashingEncoder(dim=int(enc_cfg["dim"]), seed=cfg.seed)
        return hashing, EncoderInfo(hashing.model_id, "none", "hashing", ())
    encoder_dir = opts.out / "encoder"  # the encoder is frozen with (and hashed into) the model dir
    meta = read_encoder_meta(encoder_dir)  # ArtifactMissing with the fetch hint if absent
    if (meta["model_id"], meta["revision"]) != (enc_cfg["model_id"], enc_cfg["revision"]):
        raise ArtifactVersionMismatch(
            f"{encoder_dir}: encoder {meta['model_id']}@{meta['revision']} != train.yaml "
            f"{enc_cfg['model_id']}@{enc_cfg['revision']}"
        )
    onnx = OnnxEncoder(encoder_dir, query_prefix=str(enc_cfg["query_prefix"]),
                       max_tokens=int(enc_cfg["max_tokens"]), intra_op_threads=settings.ort_intra_op_threads)
    files = tuple(sorted(p for p in encoder_dir.iterdir() if p.is_file()))
    return onnx, EncoderInfo(onnx.model_id, onnx.revision, "onnx_int8", files)


def run_training(opts: TrainOptions, *, settings: Settings | None = None, now: datetime | None = None
                 ) -> TrainOutcome:
    """Stage A → B → (C). Writes `opts.report`; with `cv_only=False` also the frozen model dir.

    Raises:
        InvalidInput: a holdout path or bad data. ArtifactMissing: the ONNX encoder is not exported/fetched.
        ArtifactVersionMismatch: the encoder differs from `train.yaml`.
    """
    settings = settings or Settings()
    opts = dataclasses.replace(opts, out=opts.out.resolve(), report=opts.report.resolve())
    cfg = TrainCfg.load()
    normalizer = DefaultNormalizer.from_lexicons(opts.lexicon_dir, int(cfg.section("guards")["max_tokens"]))
    paths: Sequence[Path] = opts.data or tuple(default_pool_paths())
    pool = load_pool(paths, normalizer, use_augmentation=opts.toggles.use_augmentation,
                     strip_wrappers=opts.toggles.strip_wrappers, folds_csv=opts.folds_csv,
                     features_csv=opts.features_csv)
    base, info = _encoder(opts, cfg, settings)
    encoder = CachingEncoder(base)
    features = tuple(cfg.section("priority_head")["features"])
    kit = TrainingKit(
        normalizer=normalizer,
        evidence=LexiconEvidenceExtractor.from_yaml(opts.lexicon_dir / "urgency.yaml", features),
        safety=SafetyGuard(compile_bank(opts.lexicon_dir / "safety.yaml", "danger"),
                           compile_bank(opts.lexicon_dir / "safety.yaml", "distress")),
        expander=SoftTargetExpander(LABEL_FLAGS_CSV),
        features=features,
    )
    oof = run_cv(pool, encoder, cfg, opts.toggles, kit)
    tuned = stage_b(oof, cfg, encoder, opts.lexicon_dir)
    report = cv_report(oof, tuned, cfg)
    report["encoder"] = {"model_id": info.model_id, "revision": info.revision, "runtime": info.runtime}
    opts.report.parent.mkdir(parents=True, exist_ok=True)
    with opts.report.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    f1_cat = report["category"]["macro_f1_oof_official"]
    f1_pri = report["priority"]["macro_f1_oof_official"]
    if opts.cv_only:
        summary = (f"cv only: members={','.join(oof.members)} cat_macroF1_oof_official={f1_cat:.3f} "
                   f"pri_macroF1_oof_official={f1_pri:.3f} report={opts.report}")
        return TrainOutcome(report, summary, None)
    config, manifest = freeze(opts.out, oof, tuned, cfg, kit, encoder, info, opts.lexicon_dir, now=now)
    summary = (f"froze {config.artifact_version}: members={','.join(config.ensemble.members)} "
               f"cat_macroF1_oof_official={f1_cat:.3f} pri_macroF1_oof_official={f1_pri:.3f} "
               f"sha={manifest.sha[:12]}")
    return TrainOutcome(report, summary, manifest.sha)
