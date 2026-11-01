"""`run_training`: the composition root of `train.py` (P1.16, P2.7, ARCHITECTURE §3.4).

Wires the training pool, the frozen encoder (ONNX int8, or the test `HashingEncoder`), the lexicon-based
evidence and safety components and the embedded office descriptions (D-014), then runs stage A + the stage-B
selections (OOF), stage B and, unless `cv_only`, stage C (freeze). `retune` recomputes the OOF-score stage-B
keys of a frozen model from its `oof.npz` without refitting. It never reads `data/our_test` or
`data/robustness`: `load_pool` refuses holdout paths.
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
from campuspulse_ai.adapters.models.prototype import NAME as PROTO
from campuspulse_ai.adapters.models.prototype import office_prototypes
from campuspulse_ai.adapters.models.soft_targets import SoftTargetExpander
from campuspulse_ai.adapters.models.translating_encoder import TranslatingEncoder
from campuspulse_ai.adapters.models.translator import Ct2Translator, read_translator_meta
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.oof import PipelineToggles, TrainingKit, run_cv
from campuspulse_ai.adapters.training.pool import FEATURES_CSV, FOLDS_CSV, Pool, default_pool_paths, load_pool
from campuspulse_ai.adapters.training.stages import EncoderInfo, cv_report, freeze, retune, stage_b
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.adapters.training.translation_cache import CsvCachedTranslator
from campuspulse_ai.config.paths import DATA_CLEAN, LEXICONS, MODELS_FROZEN, REPO_ROOT, REPORTS
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactVersionMismatch, InvalidInput
from campuspulse_ai.domain.ports import SentenceEncoder

EncoderKind = Literal["onnx", "hashing"]
LABEL_FLAGS_CSV = DATA_CLEAN / "label_flags.csv"
TRANSLATION_CACHE = REPORTS / "translate_test" / "translations.csv"  # source, translation, model id, revision


@dataclass(frozen=True)
class TrainOptions:
    out: Path = MODELS_FROZEN / "v1"
    report: Path = REPORTS / "cv_p2.json"
    cv_only: bool = False
    fast: bool = False  # skip the C grids (grid midpoints) and the nested estimates: tests and quick looks
    retune: bool = False  # recompute the OOF-score stage-B keys of `out` from its oof.npz, no refit
    encoder: EncoderKind = "onnx"
    encoder_dir: Path | None = None  # another exported encoder for CV-only comparisons (P2.6)
    data: tuple[Path, ...] = ()  # default: data/clean/train_val_combined.csv + data/augmented/*.csv
    folds_csv: Path = FOLDS_CSV
    features_csv: Path = FEATURES_CSV
    lexicon_dir: Path = LEXICONS
    toggles: PipelineToggles = field(default_factory=PipelineToggles)
    translation_cache: Path = TRANSLATION_CACHE  # source,translation,model_id,revision (P8.1)


@dataclass(frozen=True)
class TrainOutcome:
    report: dict[str, Any]
    summary: str
    manifest_sha: str | None


def make_encoder(
    opts: TrainOptions, cfg: TrainCfg, settings: Settings
) -> tuple[SentenceEncoder, EncoderInfo]:
    """The training encoder: the frozen ONNX int8 one in `<out>/encoder` (checked against train.yaml),
    another exported encoder dir (`encoder_dir`, CV-only comparisons), or the test `HashingEncoder`."""
    enc_cfg = cfg.section("encoder")
    if opts.encoder == "hashing":
        hashing = HashingEncoder(dim=int(enc_cfg["dim"]), seed=cfg.seed)
        return hashing, EncoderInfo(hashing.model_id, "none", "hashing", ())
    if opts.encoder_dir is not None:
        if not opts.cv_only:
            raise InvalidInput("--encoder-dir is for CV-only comparisons; freeze with the train.yaml encoder")
        onnx = OnnxEncoder(opts.encoder_dir, intra_op_threads=settings.ort_intra_op_threads)
        return onnx, EncoderInfo(onnx.model_id, onnx.revision, "onnx_int8", ())
    encoder_dir = opts.out / "encoder"  # the encoder is frozen with (and hashed into) the model dir
    meta = read_encoder_meta(encoder_dir)  # ArtifactMissing with the fetch hint if absent
    if (meta["model_id"], meta["revision"]) != (enc_cfg["model_id"], enc_cfg["revision"]):
        raise ArtifactVersionMismatch(
            f"{encoder_dir}: encoder {meta['model_id']}@{meta['revision']} != train.yaml "
            f"{enc_cfg['model_id']}@{enc_cfg['revision']}"
        )
    onnx = OnnxEncoder(
        encoder_dir,
        query_prefix=str(enc_cfg["query_prefix"]),
        max_tokens=int(enc_cfg["max_tokens"]),
        intra_op_threads=settings.ort_intra_op_threads,
    )
    files = tuple(sorted(p for p in encoder_dir.iterdir() if p.is_file()))
    tr_cfg = cfg.raw.get("translate") or {}
    if not tr_cfg.get("enabled", False):
        return onnx, EncoderInfo(onnx.model_id, onnx.revision, "onnx_int8", files)
    # D-019: the same wrapper as inference; texts already in the cache keep their recorded translation
    translator_dir = opts.out / str(tr_cfg.get("dir", "translator"))
    meta = read_translator_meta(translator_dir)  # ArtifactMissing with the fetch hint if absent
    if (meta["model_id"], meta["revision"]) != (tr_cfg["model"], tr_cfg["revision"]):
        raise ArtifactVersionMismatch(
            f"{translator_dir}: translator {meta['model_id']}@{meta['revision']} != train.yaml "
            f"{tr_cfg['model']}@{tr_cfg['revision']}"
        )
    cached = CsvCachedTranslator(
        opts.translation_cache, Ct2Translator(translator_dir), str(tr_cfg["model"]), str(tr_cfg["revision"])
    )
    wrapped = TranslatingEncoder(
        onnx, cached, float(tr_cfg["min_arabic_ratio"]), bool(tr_cfg.get("arabizi", False))
    )
    translator_files = tuple(sorted(p for p in translator_dir.iterdir() if p.is_file()))
    return wrapped, EncoderInfo(onnx.model_id, onnx.revision, "onnx_int8", files + translator_files)


def make_kit(
    cfg: TrainCfg, lexicon_dir: Path, normalizer: DefaultNormalizer, encoder: SentenceEncoder
) -> TrainingKit:
    """The non-learned collaborators, with the office descriptions embedded when m2proto is a member."""
    features = tuple(cfg.section("priority_head")["features"])
    office = None
    if PROTO in cfg.members:
        office = office_prototypes(encoder, REPO_ROOT / str(cfg.section("prototype")["descriptions"]))
    return TrainingKit(
        normalizer=normalizer,
        evidence=LexiconEvidenceExtractor.from_yaml(lexicon_dir / "urgency.yaml", features),
        safety=SafetyGuard(
            compile_bank(lexicon_dir / "safety.yaml", "danger"),
            compile_bank(lexicon_dir / "safety.yaml", "distress"),
        ),
        expander=SoftTargetExpander(LABEL_FLAGS_CSV),
        features=features,
        office=office,
    )


def make_pool(opts: TrainOptions, cfg: TrainCfg) -> tuple[Pool, DefaultNormalizer]:
    normalizer = DefaultNormalizer.from_lexicons(opts.lexicon_dir, int(cfg.section("guards")["max_tokens"]))
    paths: Sequence[Path] = opts.data or tuple(default_pool_paths())
    pool = load_pool(
        paths,
        normalizer,
        use_augmentation=opts.toggles.use_augmentation,
        strip_wrappers=opts.toggles.strip_wrappers,
        folds_csv=opts.folds_csv,
        features_csv=opts.features_csv,
        include_unreviewed=opts.toggles.include_unreviewed,
        include_model_reviewed=opts.toggles.include_model_reviewed,
    )
    return pool, normalizer


def _is_scratch(out: Path) -> bool:
    """True when `out` is not under the repo's `models/` directory (a scratch candidate, never a release)."""
    try:
        out.resolve().relative_to((REPO_ROOT / "models").resolve())
    except ValueError:
        return True
    return False


def run_training(
    opts: TrainOptions, *, settings: Settings | None = None, now: datetime | None = None
) -> TrainOutcome:
    """Stage A → B → (C), or `retune`. Writes `opts.report` (not for `retune`); with `cv_only=False` also the
    frozen model dir.

    Raises:
        InvalidInput: a holdout path, bad data, unreviewed rows in a freeze, or `--encoder-dir` in a freeze.
        ArtifactMissing: the ONNX encoder is not exported/fetched (or no oof.npz for `retune`).
        ArtifactVersionMismatch: the encoder differs from `train.yaml`, or `retune` on another pool.
    """
    settings = settings or Settings()
    opts = dataclasses.replace(opts, out=opts.out.resolve(), report=opts.report.resolve())
    cfg = TrainCfg.load()
    scratch = _is_scratch(opts.out)  # P8.1: only a dir outside `models/` may use the arm
    if opts.toggles.include_unreviewed and not opts.cv_only:
        raise InvalidInput("a frozen model never trains on unreviewed augmentation rows")
    if opts.toggles.include_model_reviewed and not opts.cv_only and not scratch:
        raise InvalidInput("a frozen model never trains on unreviewed or model-reviewed augmentation rows "
                           "(the model-panel arm needs its own decision first)")
    pool, normalizer = make_pool(opts, cfg)
    if opts.retune:
        config, manifest, changed = retune(opts.out, cfg, pool, now=now)
        diff = (
            "; ".join(f"{k}: {a} -> {b}" for k, a, b in ((k, *v) for k, v in changed.items())) or "no change"
        )
        return TrainOutcome(
            {"retune": {k: list(v) for k, v in changed.items()}},
            f"retuned {config.artifact_version}: {diff} sha={manifest.sha[:12]}",
            manifest.sha,
        )
    base, info = make_encoder(opts, cfg, settings)
    encoder = CachingEncoder(base)
    translator = getattr(base, "translator", None)
    kit = make_kit(cfg, opts.lexicon_dir, normalizer, encoder)
    oof = run_cv(pool, encoder, cfg, opts.toggles, kit, nested=not opts.fast, fast=opts.fast)
    tuned = stage_b(oof, cfg, encoder, opts.lexicon_dir)
    if isinstance(translator, CsvCachedTranslator) and translator.dirty:
        translator.save()  # new training texts join the recorded translations
    report = cv_report(oof, tuned, cfg)
    report["encoder"] = {"model_id": info.model_id, "revision": info.revision, "runtime": info.runtime}
    opts.report.parent.mkdir(parents=True, exist_ok=True)
    with opts.report.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    f1_cat = report["category"]["macro_f1_oof_official"]
    f1_pri = report["priority"]["macro_f1_oof_official"]
    nested = report.get("nested") or {}
    nested_txt = (
        f" nested_cat={nested['category_macro_f1_oof_official']:.3f} "
        f"nested_pri={nested['priority_macro_f1_oof_official']:.3f}"
        if nested
        else ""
    )
    if opts.cv_only:
        summary = (
            f"cv only: members={','.join(oof.members)} cat_macroF1_oof_official={f1_cat:.3f} "
            f"pri_macroF1_oof_official={f1_pri:.3f}{nested_txt} report={opts.report}"
        )
        return TrainOutcome(report, summary, None)
    config, manifest = freeze(opts.out, oof, tuned, cfg, kit, encoder, info, opts.lexicon_dir, now=now)
    if isinstance(translator, CsvCachedTranslator) and translator.dirty:
        translator.save()
    weights = ",".join(f"{m}:{w:.1f}" for m, w in config.ensemble.weights_category.items())
    summary = (
        f"froze {config.artifact_version}: members={','.join(config.ensemble.members)} "
        f"weights_cat={{{weights}}} cat_macroF1_oof_official={f1_cat:.3f} "
        f"pri_macroF1_oof_official={f1_pri:.3f}{nested_txt} q_cat={tuned.q_category:.2f} "
        f"q_pri={tuned.q_priority:.2f} sha={manifest.sha[:12]}"
    )
    return TrainOutcome(report, summary, manifest.sha)
