#!/usr/bin/env python3
"""P2.14 translate-test experiment: a local, offline Arabic->English MT model in front of the encoder.

    python scripts/translate_test.py fetch      # download opus-mt-ar-en at the pinned revision, convert to
                                                # CTranslate2 int8 under .tmp/translate/ (training machine)
    python scripts/translate_test.py export     # runtime files -> models/frozen/v1/translator/ (P2.15)
    python scripts/translate_test.py bench      # RSS and per-request latency (ct2 int8 and torch fp32)
    python scripts/translate_test.py arms [--boot 2000] [--out reports/translate_test.json]
    python scripts/translate_test.py samples    # print dialect rows next to their translations

Arms (identical rc2 recipe: `run_cv` over the frozen cv_fold folds, fixed stage B, `freeze` to a temp dir,
our_test scored by `build_offline`; the same code path as `evaluate.py --ablations`):
  A  baseline        the rc2 encoder as is;
  B  translate-only  every Arabic-script encoder input is replaced by its English translation, at train and
                     test time (pool rows, office descriptions, exemplar indexes, our_test);
  C  dual            the encoder output is the renormalized mean of the embeddings of the original and of
                     the translation (one vector, so every member, the kNN index, the prototypes and conformal
                     stay unchanged; averaging member probabilities would double every member's inference);
  D  test-only       trained as A; our_test inputs translated at inference (our_test only: the OOF folds embed
                     each row once, so a train-original / test-translated OOF would need per-fold embeddings).
Arabizi: the normalizer already transliterates Arabizi into Arabic script for the encoder (`model_text`), so
B/C/D translate that transliteration (option a). The translation applies to the encoder only: M1 (TF-IDF,
priority only, category weight 0) still reads the original text.

Translations are deterministic (greedy, beam 1, no sampling) and cached in
`reports/translate_test/translations.csv` (source, translation, model id, revision), so `arms` re-runs
offline from the cache. The MT model is a measurement dependency (requirements-train.txt), never imported by
predict.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from campuspulse_ai.adapters.models.encoder import CachingEncoder
from campuspulse_ai.adapters.training.metrics import macro_f1, paired_group_bootstrap
from campuspulse_ai.adapters.training.oof import PipelineToggles, run_cv
from campuspulse_ai.adapters.training.pool import FOLDS_CSV
from campuspulse_ai.adapters.training.stages import EncoderInfo, freeze, stage_b
from campuspulse_ai.adapters.training.train_config import TrainCfg
from campuspulse_ai.composition.evaluation import (
    ENSEMBLE,
    LABELS,
    LANGS,
    TARGETS,
    Row,
    _views,
    coverage_rows,
    fairness,
    load_eval_cfg,
    oof_rows,
    our_test_rows,
)
from campuspulse_ai.composition.offline import build_offline
from campuspulse_ai.composition.training import TrainOptions, make_encoder, make_kit, make_pool
from campuspulse_ai.config.paths import LEXICONS, MODELS_FROZEN, REPO_ROOT, REPORTS
from campuspulse_ai.config.settings import Settings

MT_MODEL_ID = "Helsinki-NLP/opus-mt-ar-en"
MT_REVISION = "c5b2a50db78d6be98ae207223f8d4f63bc7a0ff1"  # pinned HF revision (fetched 2026-10-31)
MT_DIR = REPO_ROOT / ".tmp" / "translate"
HF_DIR = MT_DIR / "opus-mt-ar-en"
CT2_DIR = MT_DIR / "opus-mt-ar-en-ct2-int8"
META = MT_DIR / "mt_meta.json"
CACHE = REPORTS / "translate_test" / "translations.csv"
BEAM = 1
MAX_LEN = 256
_AR = re.compile(r"[؀-ۿݐ-ݿ]")


def is_arabic(text: str) -> bool:
    """True when at least 30 % of the letters are Arabic script (mixed EN/AR code-switching included)."""
    letters = sum(c.isalpha() for c in text)
    return letters > 0 and len(_AR.findall(text)) / letters >= 0.3


# --- the translator ---------------------------------------------------------------------------------------


class Ct2Translator:
    """opus-mt-ar-en converted to CTranslate2 int8; sentencepiece tokenization only (no torch at runtime)."""

    def __init__(self, ct2_dir: Path = CT2_DIR, hf_dir: Path = HF_DIR, threads: int = 1) -> None:
        import ctranslate2
        import sentencepiece as spm

        self._tr = ctranslate2.Translator(
            str(ct2_dir), device="cpu", compute_type="int8", intra_threads=threads
        )
        self._src = spm.SentencePieceProcessor(model_file=str(hf_dir / "source.spm"))
        self._tgt = spm.SentencePieceProcessor(model_file=str(hf_dir / "target.spm"))

    def translate(self, texts: Sequence[str]) -> list[str]:
        if not texts:
            return []
        toks = [self._src.encode(t, out_type=str)[: MAX_LEN - 1] + ["</s>"] for t in texts]
        res = self._tr.translate_batch(toks, beam_size=BEAM, max_decoding_length=MAX_LEN)
        return [self._tgt.decode(r.hypotheses[0]).strip() for r in res]


class TorchTranslator:
    """The same model in fp32 with transformers (latency/RSS reference only)."""

    def __init__(self, hf_dir: Path = HF_DIR) -> None:
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        torch.set_num_threads(1)
        self._torch = torch
        self._tok = MarianTokenizer.from_pretrained(str(hf_dir))
        self._model = MarianMTModel.from_pretrained(str(hf_dir)).eval()

    def translate(self, texts: Sequence[str]) -> list[str]:
        batch = self._tok(list(texts), return_tensors="pt", padding=True, truncation=True, max_length=MAX_LEN)
        with self._torch.no_grad():
            out = self._model.generate(**batch, num_beams=BEAM, do_sample=False, max_length=MAX_LEN)
        return self._tok.batch_decode(out, skip_special_tokens=True)


class TranslationCache:
    """source -> translation, persisted to CSV with the model id and revision of every row."""

    def __init__(self, path: Path, revision: str, translator_factory: Callable[[], Any] | None) -> None:
        self.path, self.revision, self._factory = path, revision, translator_factory
        self._tr: Any = None
        self.table: dict[str, str] = {}
        self.dirty = False
        if path.is_file():
            with path.open(encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    if r["model_id"] == MT_MODEL_ID and r["revision"] == revision:
                        self.table[r["source"]] = r["translation"]

    def __call__(self, texts: Sequence[str]) -> list[str]:
        missing = list(dict.fromkeys(t for t in texts if t not in self.table))
        if missing:
            if self._factory is None:
                raise RuntimeError(
                    f"{len(missing)} texts are not in {self.path} and no MT model is available"
                )
            if self._tr is None:
                self._tr = self._factory()
            for i in range(0, len(missing), 16):
                chunk = missing[i : i + 16]
                self.table.update(zip(chunk, self._tr.translate(chunk), strict=True))
            self.dirty = True
        return [self.table[t] for t in texts]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["source", "translation", "model_id", "revision", "backend", "beam"])
            for s in sorted(self.table):
                w.writerow([s, self.table[s], MT_MODEL_ID, self.revision, "ctranslate2-int8", BEAM])
        self.dirty = False


class TranslatingEncoder:
    """Wraps a SentenceEncoder: Arabic-script inputs are translated (`replace`) or embedded twice (`dual`)."""

    def __init__(self, inner: Any, translate: Callable[[Sequence[str]], list[str]], mode: str) -> None:
        if mode not in ("replace", "dual"):
            raise ValueError(mode)
        self.inner, self._translate, self.mode = inner, translate, mode
        self.dim = inner.dim

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        texts = list(texts)
        idx = [i for i, t in enumerate(texts) if is_arabic(t)]
        if not idx:
            return self.inner.encode(texts)
        tr = self._translate([texts[i] for i in idx])
        if self.mode == "replace":
            new = list(texts)
            for i, t in zip(idx, tr, strict=True):
                new[i] = t
            return self.inner.encode(new)
        base = np.asarray(self.inner.encode(texts), dtype=np.float64)
        alt = np.asarray(self.inner.encode(tr), dtype=np.float64)
        mixed = base[idx] + alt
        base[idx] = mixed / np.linalg.norm(mixed, axis=1, keepdims=True)
        return base.tolist()


def revision() -> str:
    return str(json.loads(META.read_text(encoding="utf-8"))["revision"]) if META.is_file() else "unknown"


def make_cache() -> TranslationCache:
    factory = (lambda: Ct2Translator()) if CT2_DIR.is_dir() else None
    return TranslationCache(CACHE, revision(), factory)


# --- fetch ------------------------------------------------------------------------------------------------


def cmd_fetch(_: argparse.Namespace) -> int:
    import ctranslate2
    from huggingface_hub import HfApi, snapshot_download

    info = HfApi().model_info(MT_MODEL_ID)
    rev = str(info.sha)
    snapshot_download(
        MT_MODEL_ID,
        revision=rev,
        local_dir=str(HF_DIR),
        allow_patterns=["*.json", "*.spm", "vocab.json", "pytorch_model.bin", "*.safetensors", "README.md"],
    )
    ctranslate2.converters.TransformersConverter(str(HF_DIR)).convert(
        str(CT2_DIR), quantization="int8", force=True
    )

    def size(d: Path) -> int:
        return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())

    card = getattr(info, "card_data", None) or getattr(info, "cardData", None)
    licence = getattr(card, "license", None) if card is not None else None
    meta = {
        "model_id": MT_MODEL_ID,
        "revision": rev,
        "license": licence or "cc-by-4.0 (model card)",
        "hf_dir_mb": round(size(HF_DIR) / 2**20, 1),
        "ct2_int8_mb": round(size(CT2_DIR) / 2**20, 1),
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """P2.15 / D-019: the files `Ct2Translator` loads, in `<out>` (default `models/frozen/v1/translator/`).

    The CTranslate2 int8 model, the two sentencepiece models and `translator_meta.json` (model id, pinned
    revision, licence, decoding). `train.py` hashes them into MANIFEST.json; they ship in the models tarball.
    """
    import shutil

    if not CT2_DIR.is_dir() or not META.is_file():
        print("run `python scripts/translate_test.py fetch` first", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for src in sorted(CT2_DIR.iterdir()):
        if src.is_file():
            shutil.copyfile(src, out / src.name)
    for name in ("source.spm", "target.spm"):
        shutil.copyfile(HF_DIR / name, out / name)
    mt = json.loads(META.read_text(encoding="utf-8"))
    meta = {
        "model_id": MT_MODEL_ID,
        "revision": mt["revision"],
        "license": mt.get("license", "apache-2.0"),
        "beam": BEAM,
        "max_len": MAX_LEN,
        "compute_type": "int8",
        "arabic_ratio_rule": "letters >= 30% Arabic script",
    }
    (out / "translator_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"exported {sorted(p.name for p in out.iterdir())} to {out}")
    return 0


# --- bench ------------------------------------------------------------------------------------------------


def _rss_mb() -> float:
    import psutil

    return psutil.Process(os.getpid()).memory_info().rss / 2**20


def _arabic_samples(n: int) -> list[str]:
    with (REPO_ROOT / "data" / "clean" / "train_val_combined.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        rows = [r for r in csv.DictReader(f) if r.get("lang") == "ar"]
    return [r["text"] for r in rows][:n]


def cmd_bench(args: argparse.Namespace) -> int:
    """One backend per process (RSS is per process): `bench --backend ct2|torch|api`."""
    texts = _arabic_samples(60)
    out: dict[str, Any] = {"backend": args.backend, "n_requests": len(texts), "threads": 1}
    if args.backend == "api":  # the offline core as the API loads it, then the translator on top
        out["rss_before_mb"] = round(_rss_mb(), 1)
        container = build_offline(MODELS_FROZEN / "v1")
        container.encoder.encode(["warm up"])
        out["rss_core_mb"] = round(_rss_mb(), 1)
        tr = Ct2Translator()
        tr.translate(texts[:5])
        out["rss_core_plus_mt_mb"] = round(_rss_mb(), 1)
        enc_lat = []
        for t in texts:
            t0 = time.perf_counter()
            container.encoder.encode([t + " x"])
            enc_lat.append((time.perf_counter() - t0) * 1000)
        out["encoder_p50_ms"] = round(statistics.median(enc_lat), 1)
    else:
        base = _rss_mb()
        tr = Ct2Translator() if args.backend == "ct2" else TorchTranslator()
        tr.translate(texts[:5])  # warm-up
        out["rss_added_mb"] = round(_rss_mb() - base, 1)
    lat = []
    for t in texts:
        t0 = time.perf_counter()
        tr.translate([t])
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    out["p50_ms"] = round(lat[len(lat) // 2], 1)
    out["p95_ms"] = round(lat[int(0.95 * (len(lat) - 1))], 1)
    out["max_ms"] = round(lat[-1], 1)
    if args.backend != "api":
        out["rss_after_mb_added"] = round(_rss_mb() - base, 1)
    print(json.dumps(out))
    return 0


# --- arms -------------------------------------------------------------------------------------------------


def _run_arm(
    name: str, train_enc: Any, test_enc: Any, cfg: TrainCfg, settings: Settings, info: EncoderInfo
) -> tuple[list[Row], list[Row]]:
    toggles = PipelineToggles()
    opts = TrainOptions(cv_only=True, toggles=toggles, folds_csv=FOLDS_CSV)
    pool, normalizer = make_pool(opts, cfg)
    kit = make_kit(cfg, LEXICONS, normalizer, train_enc)
    oof = run_cv(pool, train_enc, cfg, toggles, kit, nested=False)
    tuned = stage_b(oof, cfg, train_enc, LEXICONS)
    with tempfile.TemporaryDirectory(prefix=f"cp_tt_{name}_") as tmp:
        out = Path(tmp) / "v1"
        freeze(out, oof, tuned, cfg, kit, train_enc, info, LEXICONS)
        container = build_offline(out, encoder_override=test_enc, settings=settings)
        oof_r = [r for r in oof_rows(out, container.config) if r.subset == "official"]
        test_r = our_test_rows(container)
    print(f"arm {name}: done", flush=True)
    return oof_r, test_r


def _f1(rows: Sequence[Row], target: str) -> float | None:
    if not rows:
        return None
    t = 0 if target == "category" else 1
    return round(
        macro_f1(
            [getattr(r, target) for r in rows], [str(r.pred[ENSEMBLE][t]) for r in rows], LABELS[target]
        ),
        4,
    )


def _paired(base: Sequence[Row], cand: Sequence[Row], target: str, boot: dict[str, Any]) -> dict[str, float]:
    b = {r.request_id: r for r in base}
    c = {r.request_id: r for r in cand}
    ids = sorted(b)
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
    return {k: round(float(v), 4) for k, v in comp.items()}


def cmd_arms(args: argparse.Namespace) -> int:
    cfg = TrainCfg.load()
    settings = Settings()
    eval_cfg = load_eval_cfg()
    boot = dict(eval_cfg["bootstrap"])
    boot["resamples"] = args.boot
    onnx, _ = make_encoder(TrainOptions(cv_only=True, out=MODELS_FROZEN / "v1"), cfg, settings)
    info = EncoderInfo(onnx.model_id, onnx.revision, "onnx_int8", ())
    base = CachingEncoder(onnx)
    cache = make_cache()
    replace = TranslatingEncoder(base, cache, "replace")
    dual = TranslatingEncoder(base, cache, "dual")
    plan = {"A": (base, base), "B": (replace, replace), "C": (dual, dual), "D": (base, replace)}
    arms = [a for a in args.arms.split(",") if a in plan]
    results: dict[str, Any] = {}
    rows: dict[str, tuple[list[Row], list[Row]]] = {}
    for a in arms:
        rows[a] = _run_arm(a, *plan[a], cfg, settings, info)
        if cache.dirty:
            cache.save()
    for a in arms:
        oof_r, test_r = rows[a]
        if a == "D":  # trained as A: its OOF is A's
            oof_r = rows["A"][0] if "A" in rows else oof_r
        views = _views(oof_r, test_r, [])
        entry: dict[str, Any] = {"f1": {}, "vs_A": {}}
        for dataset, vr in views:
            if dataset == "oof_all":
                continue
            for target in TARGETS:
                cell = {"all": _f1(vr, target)}
                for lang in LANGS:
                    cell[lang] = _f1([r for r in vr if r.lang == lang], target)
                entry["f1"].setdefault(dataset, {})[target] = cell
        entry["coverage"] = [c for c in coverage_rows(views) if c["dataset"] != "oof_all"]
        entry["fairness"] = fairness(views)
        if a != "A" and "A" in rows:
            a_oof, a_test = rows["A"]
            for target in TARGETS:
                entry["vs_A"].setdefault("oof_official", {})[target] = _paired(a_oof, oof_r, target, boot)
                entry["vs_A"].setdefault("our_test", {})[target] = _paired(a_test, test_r, target, boot)
                for lang in LANGS:
                    ao = [r for r in a_oof if r.lang == lang]
                    co = [r for r in oof_r if r.lang == lang]
                    at = [r for r in a_test if r.lang == lang]
                    ct = [r for r in test_r if r.lang == lang]
                    entry["vs_A"].setdefault(f"oof_official_{lang}", {})[target] = (
                        _paired(ao, co, target, boot) if ao else None
                    )
                    entry["vs_A"].setdefault(f"our_test_{lang}", {})[target] = (
                        _paired(at, ct, target, boot) if at else None
                    )
        results[a] = entry
    doc = {
        "experiment": "P2.14 translate-test",
        "mt_model": json.loads(META.read_text(encoding="utf-8"))
        if META.is_file()
        else {"model_id": MT_MODEL_ID},
        "decoding": {"beam": BEAM, "sampling": False, "backend": "ctranslate2 int8"},
        "arms_note": __doc__.split("Arms")[1].split("Translations are")[0].strip() if __doc__ else "",
        "bootstrap": boot,
        "cache": str(CACHE.relative_to(REPO_ROOT)).replace("\\", "/"),
        "cache_rows": len(cache.table),
        "arms": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


def cmd_samples(args: argparse.Namespace) -> int:
    """Translate a few raw Arabizi rows as-is (option b) and print cached Arabic translations. The official
    pool has no Arabizi rows, so the Arabizi examples come from our_test (read for evaluation only)."""
    cache = make_cache()
    with (REPO_ROOT / "data" / "our_test" / "our_test.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    arabizi = [r["text"] for r in rows if r.get("lang") == "arabizi"][: args.n]
    tr = Ct2Translator().translate(arabizi) if CT2_DIR.is_dir() else []
    for s, t in zip(arabizi, tr, strict=False):
        print(f"[arabizi as-is] {s}  =>  {t}")
    for s, t in list(cache.table.items())[: args.n]:
        print(f"[ar] {s}  =>  {t}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    e = sub.add_parser("export")
    e.add_argument("--out", default=str(MODELS_FROZEN / "v1" / "translator"))
    e.set_defaults(fn=cmd_export)
    b = sub.add_parser("bench")
    b.add_argument("--backend", choices=("ct2", "torch", "api"), default="ct2")
    b.set_defaults(fn=cmd_bench)
    a = sub.add_parser("arms")
    a.add_argument("--arms", default="A,B,C,D")
    a.add_argument("--boot", type=int, default=2000)
    a.add_argument("--out", default=str(REPORTS / "translate_test.json"))
    a.set_defaults(fn=cmd_arms)
    s = sub.add_parser("samples")
    s.add_argument("--n", type=int, default=25)
    s.set_defaults(fn=cmd_samples)
    args = p.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
