"""Export the sentence encoder to portable ONNX int8 and report parity, size, latency and RSS (P1.6, LD-8).

Training machine only (needs `requirements-train.txt`: torch, sentence-transformers; plus `onnx` for the
quantizer). This is the only module that imports torch (ARCHITECTURE §1.4); inference uses
`adapters.models.encoder.OnnxEncoder`.

    python -m campuspulse_ai.frameworks.cli.export_encoder \
        --model intfloat/multilingual-e5-small --revision <sha> --out models/frozen/v1/encoder
    -> int8 size=<MB> MB min_cos=<x> rss_mb_after_load=<n> ms_per_batch32=<n> (threads=1)

Steps:
  1. resolve the Hugging Face commit (`--revision`, else `config/train.yaml encoder.revision` for that model,
     else `huggingface_hub.model_info(...).sha`) and download exactly that revision;
  2. load it with sentence-transformers (eager attention), check the pipeline is Transformer → mean
     Pooling (→ Normalize), and export the transformer with `torch.onnx.export` (TorchScript exporter,
     `dynamo=False`; dynamic batch and sequence axes; inputs input_ids + attention_mask; output
     last_hidden_state). Pooling and L2 normalization happen in numpy inside `OnnxEncoder`;
  3. quantize with `onnxruntime.quantization.quantize_dynamic` (QInt8 weights, per-channel, reduce_range:
     a generic int8 graph; never Hugging Face's AVX512-VNNI file; no optimum);
  4. copy the model's `tokenizer.json` byte for byte and write `encoder_meta.json`;
  5. parity: cosine(int8 `OnnxEncoder`, sentence-transformers fp32) on `tests/fixtures/encoder_parity.txt`
     (also fp32 ONNX vs torch, and int8 batch-vs-single invariance);
  6. in fresh subprocesses (one per thread count), measure RSS after loading, single-text and batch-32
     latency with psutil;
  7. write `reports/encoder_export.json`. Exit 1 if `min_cos` < `encoder_export.min_cosine` or the int8
     file exceeds `encoder_export.max_size_mb`; warn if RSS exceeds `encoder_export.rss_warn_mb`.

`--measure DIR --threads N` is the subprocess mode: it imports only the inference stack and prints JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.config.paths import CONFIG_DIR, REPO_ROOT, REPORTS

PARITY_FILE = REPO_ROOT / "services" / "ai" / "tests" / "fixtures" / "encoder_parity.txt"
DEFAULT_REPORT = REPORTS / "encoder_export.json"
DEFAULT_WORK = REPO_ROOT / ".tmp" / "encoder_export"
ONNX_FILE = "model_int8.onnx"
FP32_FILE = "model_fp32.onnx"
TOKENIZER_FILE = "tokenizer.json"
META_FILE = "encoder_meta.json"
INPUT_NAMES = ("input_ids", "attention_mask")
OUTPUT_NAME = "last_hidden_state"
SNAPSHOT_PATTERNS = ["*.json", "*.safetensors", "sentencepiece.bpe.model", "1_Pooling/*", "*.txt"]
MB = 1024 * 1024
EXPORTER = "torch.onnx.export (TorchScript, dynamo=False) + onnxruntime.quantization.quantize_dynamic"


def load_knobs() -> tuple[dict[str, Any], dict[str, Any]]:
    """(`encoder`, `encoder_export`) sections of `config/train.yaml`."""
    cfg = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))
    return dict(cfg["encoder"]), dict(cfg["encoder_export"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sentences(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cpu_name() -> str:
    """Human-readable CPU model (registry on Windows, /proc/cpuinfo on Linux)."""
    if sys.platform == "win32":
        import winreg

        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or platform.machine()


# ---- measurement subprocess (inference stack only: no torch) -------------------------------------------


def measure(encoder_dir: Path, threads: int, batch: int, repeats_single: int, repeats_batch: int,
            sentences_path: Path) -> dict[str, Any]:
    """RSS and latency of a freshly loaded `OnnxEncoder` in this process (call it in a new process)."""
    import psutil

    proc = psutil.Process()
    rss_baseline = proc.memory_info().rss
    from campuspulse_ai.adapters.models.encoder import OnnxEncoder

    t0 = time.perf_counter()
    encoder = OnnxEncoder(encoder_dir, intra_op_threads=threads)  # batch size from encoder_meta.json
    load_s = time.perf_counter() - t0
    rss_after_load = proc.memory_info().rss
    texts = read_sentences(sentences_path)[:-1]  # the last fixture line is the 256-token stress test
    encoder.encode([texts[0]])  # warm-up: first-run allocations are not latency
    single: list[float] = []
    for i in range(repeats_single):
        t1 = time.perf_counter()
        encoder.encode([texts[i % len(texts)]])
        single.append((time.perf_counter() - t1) * 1000)
    batch_texts = (texts * (batch // len(texts) + 1))[:batch]
    batched: list[float] = []
    for _ in range(repeats_batch):
        t1 = time.perf_counter()
        encoder.encode(batch_texts)
        batched.append((time.perf_counter() - t1) * 1000)
    mem = proc.memory_info()
    peak = getattr(mem, "peak_wset", None)  # Windows peak working set
    if peak is None and sys.platform != "win32":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # Linux reports KiB
    # for comparison only, after every RSS reading: one padded ONNX call per `batch` texts
    padded_encoder = OnnxEncoder(encoder_dir, intra_op_threads=threads, batch_size=batch)
    padded: list[float] = []
    for _ in range(repeats_batch):
        t1 = time.perf_counter()
        padded_encoder.encode(batch_texts)
        padded.append((time.perf_counter() - t1) * 1000)
    return {
        "threads": threads,
        "rss_mb_baseline": round(rss_baseline / MB, 1),
        "rss_mb_after_load": round(rss_after_load / MB, 1),
        "rss_mb_after_encode": round(mem.rss / MB, 1),
        "rss_mb_peak": round(peak / MB, 1) if peak else None,
        "load_s": round(load_s, 2),
        "ms_per_text_median": round(statistics.median(single), 1),
        f"ms_per_batch{batch}_median": round(statistics.median(batched), 1),
        f"ms_per_batch{batch}_padded_median": round(statistics.median(padded), 1),
        "encoder_batch_size": encoder._batch_size,
        "repeats_single": repeats_single,
        "repeats_batch": repeats_batch,
    }


def run_measure_subprocess(encoder_dir: Path, threads: int, knobs: dict[str, Any]) -> dict[str, Any]:
    module = "campuspulse_ai.frameworks.cli.export_encoder"
    cmd = [sys.executable, "-m", module, "--measure", str(encoder_dir), "--threads", str(threads)]
    done = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result


# ---- export (torch) ------------------------------------------------------------------------------------


def resolve_revision(model_id: str, revision: str | None, encoder_cfg: dict[str, Any]) -> str:
    if revision:
        return revision
    if model_id == encoder_cfg.get("model_id") and encoder_cfg.get("revision"):
        return str(encoder_cfg["revision"])
    from huggingface_hub import model_info

    return str(model_info(model_id).sha)


def export(model_id: str, revision: str, out_dir: Path, work_dir: Path, *, max_tokens: int, query_prefix: str,
           knobs: dict[str, Any]) -> tuple[Path, Any]:
    """Download, export fp32 ONNX, quantize, copy the tokenizer, write the meta.

    Returns:
        (fp32 ONNX path, the loaded SentenceTransformer used as the fp32 reference).
    """
    import torch
    from huggingface_hub import snapshot_download
    from onnxruntime.quantization import (  # type: ignore[import-untyped, unused-ignore]
        QuantType,
        quantize_dynamic,
    )
    from sentence_transformers import SentenceTransformer

    local = Path(snapshot_download(model_id, revision=revision, allow_patterns=SNAPSHOT_PATTERNS))
    st = SentenceTransformer(str(local), device="cpu", model_kwargs={"attn_implementation": "eager"})
    st.max_seq_length = max_tokens
    st.eval()
    names = [type(m).__name__ for m in st]
    pooling: Any = st[1]
    mode = pooling.get_config_dict().get("pooling_mode") if names[:2] == ["Transformer", "Pooling"] else None
    if mode != "mean":
        raise SystemExit(f"{model_id}: expected Transformer -> mean Pooling, got {names} (pooling {mode!r})")
    normalize = "Normalize" in names
    dim = int(st.get_sentence_embedding_dimension() or 0)

    class _LastHidden(torch.nn.Module):
        def __init__(self, model: Any) -> None:
            super().__init__()
            self.model = model

        def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
            out = self.model(input_ids=input_ids, attention_mask=attention_mask,
                             token_type_ids=torch.zeros_like(input_ids))
            return out.last_hidden_state  # type: ignore[no-any-return]

    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = work_dir / FP32_FILE
    int8_path = out_dir / ONNX_FILE
    sample = st.tokenizer([query_prefix + "where is the bus", query_prefix + "وين جدول الباصات"],
                          padding=True, return_tensors="pt")
    axes = {"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
            OUTPUT_NAME: {0: "batch", 1: "seq"}}
    with torch.no_grad():
        inputs = (sample["input_ids"], sample["attention_mask"])
        torch.onnx.export(_LastHidden(st[0].auto_model).eval(), inputs, str(fp32_path),
                          input_names=list(INPUT_NAMES), output_names=[OUTPUT_NAME],
                          dynamic_axes=axes, opset_version=int(knobs["opset"]), dynamo=False)
    q = knobs["quantization"]
    extra = {"op_types_to_quantize": list(q["op_types"])} if q.get("op_types") else {}
    quantize_dynamic(str(fp32_path), str(int8_path), weight_type=getattr(QuantType, q["weight_type"]),
                     per_channel=bool(q["per_channel"]), reduce_range=bool(q["reduce_range"]), **extra)
    tokenizer_src = local / TOKENIZER_FILE
    if not tokenizer_src.is_file():
        raise SystemExit(f"{model_id}@{revision} has no {TOKENIZER_FILE}")
    shutil.copyfile(tokenizer_src, out_dir / TOKENIZER_FILE)
    pad_id = st.tokenizer.pad_token_id
    meta = {
        "schema_version": 1,
        "model_id": model_id,
        "revision": revision,
        "dim": dim,
        "max_tokens": max_tokens,
        "query_prefix": query_prefix,
        "pooling": "mean",
        "normalize": normalize,
        "runtime": "onnx_int8",
        "onnx_file": ONNX_FILE,
        "tokenizer_file": TOKENIZER_FILE,
        "pad_token_id": int(pad_id if pad_id is not None else 0),
        "batch_size": int(knobs["batch_size"]),
        "input_names": list(INPUT_NAMES),
        "output_name": OUTPUT_NAME,
        "opset": int(knobs["opset"]),
        "quantization": {"method": "quantize_dynamic", **q},
        "exporter": EXPORTER,
        "sha256": {ONNX_FILE: sha256(int8_path), TOKENIZER_FILE: sha256(out_dir / TOKENIZER_FILE)},
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fp32_dir = work_dir / "fp32"
    fp32_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fp32_path, fp32_dir / FP32_FILE)
    shutil.copyfile(out_dir / TOKENIZER_FILE, fp32_dir / TOKENIZER_FILE)
    fp32_meta = json.dumps({**meta, "onnx_file": FP32_FILE}, indent=2)
    (fp32_dir / META_FILE).write_text(fp32_meta, encoding="utf-8")
    return fp32_path, st


def parity(st: Any, out_dir: Path, fp32_dir: Path, sentences: list[str], query_prefix: str,
           padded_batch: int) -> dict[str, Any]:
    """Cosine of the int8 (and fp32) ONNX encoders against sentence-transformers fp32, per sentence.

    `min_cos` uses the encoder as shipped (its meta batch size); the padded-batch figures show what
    batching would cost (`batch_invariance_min_cos`: same text, alone vs inside a padded batch).
    """
    import numpy as np

    from campuspulse_ai.adapters.models.encoder import OnnxEncoder

    def unit(a: Any) -> Any:  # cosine, also for encoders exported without a Normalize module (MiniLM)
        return a / np.linalg.norm(a, axis=1, keepdims=True)

    ref = unit(st.encode([query_prefix + s for s in sentences], batch_size=32, convert_to_numpy=True))
    got = unit(OnnxEncoder(out_dir).encode_array(sentences))
    got_padded = unit(OnnxEncoder(out_dir, batch_size=padded_batch).encode_array(sentences))
    got_fp32 = unit(OnnxEncoder(fp32_dir).encode_array(sentences))
    cos = (ref * got).sum(axis=1)
    worst = int(cos.argmin())
    return {
        "n_sentences": len(sentences),
        "min_cos": round(float(cos.min()), 4),
        "mean_cos": round(float(cos.mean()), 4),
        "worst_sentence": sentences[worst][:80],
        "min_cos_fp32_onnx": round(float((ref * got_fp32).sum(axis=1).min()), 6),
        f"min_cos_padded_batch{padded_batch}": round(float((ref * got_padded).sum(axis=1).min()), 4),
        "batch_invariance_min_cos": round(float((got * got_padded).sum(axis=1).min()), 6),
    }


def main(argv: list[str] | None = None) -> int:
    encoder_cfg, knobs = load_knobs()
    parser = argparse.ArgumentParser(description="Export the sentence encoder to portable ONNX int8 (P1.6).")
    parser.add_argument("--model", default=encoder_cfg["model_id"])
    parser.add_argument("--revision", default=None, help="HF commit sha (default: train.yaml, else latest)")
    parser.add_argument("--out", type=Path, default=None, help="encoder directory to write")
    parser.add_argument("--max-tokens", type=int, default=int(encoder_cfg["max_tokens"]))
    parser.add_argument("--query-prefix", default=None, help='default: train.yaml for e5, else ""')
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--parity-file", type=Path, default=PARITY_FILE)
    parser.add_argument("--per-channel", choices=("yes", "no"), default=None,
                        help="override encoder_export.quantization.per_channel (D-016 parity trials)")
    parser.add_argument("--reduce-range", choices=("yes", "no"), default=None,
                        help="override encoder_export.quantization.reduce_range (D-016 parity trials)")
    parser.add_argument("--op-types", default=None,
                        help="comma list of ONNX op types to quantize, e.g. MatMul (default: all)")
    parser.add_argument("--measure", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--threads", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.measure is not None:
        result = measure(args.measure, args.threads, int(knobs["measure_batch"]),
                         int(knobs["measure_repeats_single"]), int(knobs["measure_repeats_batch"]),
                         args.parity_file)
        print(json.dumps(result))
        return 0
    if args.out is None:
        parser.error("--out is required")

    q = dict(knobs["quantization"])
    if args.per_channel is not None:
        q["per_channel"] = args.per_channel == "yes"
    if args.reduce_range is not None:
        q["reduce_range"] = args.reduce_range == "yes"
    if args.op_types:
        q["op_types"] = [t.strip() for t in args.op_types.split(",") if t.strip()]
    knobs = {**knobs, "quantization": q}
    revision = resolve_revision(args.model, args.revision, encoder_cfg)
    prefix = args.query_prefix
    if prefix is None:
        prefix = str(encoder_cfg["query_prefix"]) if args.model == encoder_cfg["model_id"] else ""
    work = args.work_dir / args.model.replace("/", "__")
    sentences = read_sentences(args.parity_file)
    fp32_path, st = export(args.model, revision, args.out, work, max_tokens=args.max_tokens,
                           query_prefix=prefix, knobs=knobs)
    par = parity(st, args.out, work / "fp32", sentences, prefix, int(knobs["measure_batch"]))
    del st
    measures = [run_measure_subprocess(args.out, n, knobs) for n in knobs["measure_threads"]]
    size_mb = (args.out / ONNX_FILE).stat().st_size / MB
    import numpy
    import onnx
    import onnxruntime  # type: ignore[import-untyped, unused-ignore]
    import sentence_transformers
    import tokenizers
    import torch
    import transformers

    report = {
        "model_id": args.model,
        "revision": revision,
        "query_prefix": prefix,
        "max_tokens": args.max_tokens,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "exporter": EXPORTER,
        "opset": int(knobs["opset"]),
        "quantization": knobs["quantization"],
        "files": {
            name: {"bytes": (args.out / name).stat().st_size, "sha256": sha256(args.out / name)}
            for name in (ONNX_FILE, TOKENIZER_FILE, META_FILE)
        },
        "size_mb_int8": round(size_mb, 1),
        "size_mb_fp32": round(fp32_path.stat().st_size / MB, 1),
        "parity": par,
        "measure": measures,
        "machine": {"cpu": cpu_name(), "logical_cpus": os.cpu_count(),
                    "os": platform.platform(), "python": platform.python_version()},
        "versions": {"torch": torch.__version__, "transformers": transformers.__version__,
                     "sentence_transformers": sentence_transformers.__version__, "onnx": onnx.__version__,
                     "onnxruntime": onnxruntime.__version__, "tokenizers": tokenizers.__version__,
                     "numpy": numpy.__version__},
        "gates": {"min_cosine": knobs["min_cosine"], "max_size_mb": knobs["max_size_mb"],
                  "rss_warn_mb": knobs["rss_warn_mb"]},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    batch_key = f"ms_per_batch{knobs['measure_batch']}_median"
    for m in measures:
        print(f"int8 size={size_mb:.1f} MB min_cos={par['min_cos']:.3f} "
              f"rss_mb_after_load={m['rss_mb_after_load']} ms_per_batch32={m[batch_key]} "
              f"(threads={m['threads']}, ms_per_text={m['ms_per_text_median']})")
    failed = []
    if par["min_cos"] < knobs["min_cosine"]:
        failed.append(f"min_cos {par['min_cos']} < {knobs['min_cosine']}")
    if size_mb > knobs["max_size_mb"]:
        failed.append(f"int8 size {size_mb:.1f} MB > {knobs['max_size_mb']} MB")
    for m in measures:
        if m["rss_mb_after_load"] > knobs["rss_warn_mb"]:
            rss, warn = m["rss_mb_after_load"], knobs["rss_warn_mb"]
            print(f"WARNING: rss_mb_after_load {rss} > {warn} (threads={m['threads']}; §3.17 budget)")
    if failed:
        print("FAILED: " + "; ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
