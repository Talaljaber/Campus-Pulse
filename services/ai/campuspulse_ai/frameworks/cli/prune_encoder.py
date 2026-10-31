"""Prune the encoder's vocabulary to Latin, Arabic, digits, punctuation and symbols (task 9, §3.17 RSS).

    python -m campuspulse_ai.frameworks.cli.prune_encoder --src models/frozen/v1/encoder --out .tmp/enc_pruned
        [--report reports/encoder_prune.json] [--install]

Why: the `tokenizers` Unigram trie over 250,002 pieces costs ≈ 250 MB of RSS, and the int8 embedding table
another ≈ 96 MB, against the 400 MB Render budget (P1.6 finding). CampusPulse only ever sees English, Arabic
and Arabizi.

What: keep a piece when every character is either not a letter or mark (digits of any script, punctuation,
symbols, emoji, the `▁` space marker) or a letter/mark whose Unicode name starts with LATIN or ARABIC; always
keep the special tokens. Keep the original order, so `<s>`, `<pad>`, `</s>`, `<unk>` keep ids 0–3. Slice the
same rows out of the per-tensor-quantized int8 word-embedding table (exact: scale and zero point are scalars).

Why the tokenization cannot change: Unigram segmentation only uses pieces that are substrings of the text, so
for a text whose letters are all Latin/Arabic every candidate piece is kept, with its score. A text with
letters of another script (CJK, Cyrillic, Greek, ...) may now get `<unk>` where it had a piece.

Gate (exit 1 if it fails; nothing is installed): for every text of the official CSVs,
`data/augmented`, `data/our_test/our_test.csv` (read only as tokenizer input, never for scoring or
tuning), the parity fixture and the lexicon exemplars, both raw and as `model_text`, the pruned
tokenizer gives the same tokens and the mapped ids, and the pruned int8 encoder gives cosine ≥ 0.9999
against the unpruned one. Then RSS and latency of both are measured in fresh processes (the export
CLI's measure mode) and written to the report. `--install` replaces `--src` with the pruned files
(the unpruned copy is kept in `.tmp/encoder.unpruned/`).

Training machine only (imports `onnx`); never imported by `predict.py` or the API.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import onnx
from onnx import numpy_helper
from tokenizers import Tokenizer

from campuspulse_ai.adapters.guards.bank import load_texts
from campuspulse_ai.adapters.models.encoder import OnnxEncoder
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import DATA_AUGMENTED, DATA_RAW, LEXICONS, OUR_TEST, REPO_ROOT, REPORTS
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.frameworks.cli.export_encoder import PARITY_FILE, load_knobs, run_measure_subprocess

ONNX_FILE = "model_int8.onnx"
TOKENIZER_FILE = "tokenizer.json"
META_FILE = "encoder_meta.json"
EMBEDDING_INIT = "model.embeddings.word_embeddings.weight_quantized"
KEEP_SCRIPTS = ("LATIN", "ARABIC")
MIN_COSINE = 0.9999  # task 9 gate: embeddings must match the unpruned int8 encoder
DEFAULT_REPORT = REPORTS / "encoder_prune.json"
MAX_TOKENS = 256
MB = 1024 * 1024


def keep_piece(piece: str) -> bool:
    """True when every character is a non-letter or a Latin/Arabic letter or mark."""
    for ch in piece:
        if unicodedata.category(ch)[0] in "LM" and not unicodedata.name(ch, "").startswith(KEEP_SCRIPTS):
            return False
    return True


def kept_ids(tok: dict[str, Any]) -> list[int]:
    special = {int(t["id"]) for t in tok["added_tokens"]}
    return [i for i, (piece, _) in enumerate(tok["model"]["vocab"]) if i in special or keep_piece(piece)]


def prune_tokenizer(tok: dict[str, Any], keep: Sequence[int]) -> dict[str, Any]:
    new_of = {old: new for new, old in enumerate(keep)}
    out: dict[str, Any] = json.loads(json.dumps(tok))
    out["model"]["vocab"] = [tok["model"]["vocab"][i] for i in keep]
    out["model"]["unk_id"] = new_of[int(tok["model"]["unk_id"])]
    for t in out["added_tokens"]:
        t["id"] = new_of[int(t["id"])]
    for spec in (out.get("post_processor") or {}).get("special_tokens", {}).values():
        spec["ids"] = [new_of[int(i)] for i in spec["ids"]]
    return out


def prune_onnx(src: Path, dst: Path, keep: Sequence[int]) -> tuple[int, int]:
    model = onnx.load(str(src))
    for init in model.graph.initializer:
        if init.name == EMBEDDING_INIT:
            table = numpy_helper.to_array(init)
            init.CopyFrom(numpy_helper.from_array(np.ascontiguousarray(table[list(keep)]), EMBEDDING_INIT))
            onnx.save(model, str(dst))
            return int(table.shape[0]), len(keep)
    raise ValueError(f"{src}: initializer {EMBEDDING_INIT!r} not found")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_texts(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [r["text"] for r in csv.DictReader(fh)]


def gate_corpus() -> dict[str, list[str]]:
    """Every text the gate checks, by source (raw texts; `model_text` is derived in `check`)."""
    corpus = {
        "official": _csv_texts(DATA_RAW / "train.csv") + _csv_texts(DATA_RAW / "validation.csv"),
        "augmented": [t for p in sorted(DATA_AUGMENTED.glob("*.csv")) for t in _csv_texts(p)],
        "our_test": _csv_texts(OUR_TEST / "our_test.csv"),
        "parity_fixture": [line for line in PARITY_FILE.read_text(encoding="utf-8").splitlines() if line],
    }
    corpus["exemplars"] = (
        load_texts(LEXICONS / "injection.yaml", "exemplars")
        + load_texts(LEXICONS / "safety.yaml", "exemplars.distress")
        + load_texts(LEXICONS / "safety.yaml", "exemplars.danger")
    )
    return corpus


def _model_texts(raws: Iterable[str], normalizer: DefaultNormalizer) -> list[str]:
    out = []
    for raw in raws:
        try:
            out.append(normalizer.normalize(raw).model_text)
        except InvalidInput:
            continue
    return out


def check(src: Path, out: Path, keep: Sequence[int], prefix: str) -> dict[str, Any]:
    """The gate: identical tokens and mapped ids, and embedding cosine, over the whole corpus."""
    new_of = {old: new for new, old in enumerate(keep)}
    old_tok, new_tok = (
        Tokenizer.from_file(str(src / TOKENIZER_FILE)),
        Tokenizer.from_file(str(out / TOKENIZER_FILE)),
    )
    for t in (old_tok, new_tok):
        t.no_padding()
        t.enable_truncation(max_length=MAX_TOKENS)
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)
    per_source: dict[str, Any] = {}
    all_texts: list[str] = []
    token_mismatches: list[str] = []
    for source, raws in gate_corpus().items():
        texts = list(dict.fromkeys([*raws, *_model_texts(raws, normalizer)]))
        all_texts += texts
        bad = 0
        for text in texts:
            before, after = old_tok.encode(prefix + text), new_tok.encode(prefix + text)
            if before.tokens != after.tokens or [new_of.get(i, -1) for i in before.ids] != list(after.ids):
                bad += 1
                token_mismatches.append(text)
        per_source[source] = {"texts": len(texts), "token_mismatches": bad}
    distinct = list(dict.fromkeys(all_texts))
    old_enc, new_enc = OnnxEncoder(src), OnnxEncoder(out)
    a = old_enc.encode_array(distinct).astype(np.float64)
    b = new_enc.encode_array(distinct).astype(np.float64)
    cos = (a * b).sum(axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    return {
        "per_source": per_source,
        "texts": len(distinct),
        "token_mismatches": len(token_mismatches),
        "mismatch_examples": token_mismatches[:5],
        "min_cosine": float(cos.min()),
        "max_abs_diff": float(np.abs(a - b).max()),
        "passed": bool(not token_mismatches and float(cos.min()) >= MIN_COSINE),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", type=Path, default=REPO_ROOT / "models" / "frozen" / "v1" / "encoder")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / ".tmp" / "enc_pruned")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument(
        "--install", action="store_true", help="replace --src with the pruned encoder if it passes"
    )
    args = ap.parse_args(argv)
    src, out = args.src.resolve(), args.out.resolve()
    tok = json.loads((src / TOKENIZER_FILE).read_text(encoding="utf-8"))
    meta = json.loads((src / META_FILE).read_text(encoding="utf-8"))
    keep = kept_ids(tok)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with (out / TOKENIZER_FILE).open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(prune_tokenizer(tok, keep), fh, ensure_ascii=False)
    rows_before, rows_after = prune_onnx(src / ONNX_FILE, out / ONNX_FILE, keep)
    new_meta = dict(meta)
    new_meta["pad_token_id"] = keep.index(int(meta["pad_token_id"]))
    new_meta["sha256"] = {ONNX_FILE: sha256(out / ONNX_FILE), TOKENIZER_FILE: sha256(out / TOKENIZER_FILE)}
    new_meta["vocab_pruning"] = {
        "rule": "keep pieces whose letters/marks are all LATIN or ARABIC (non-letters kept) + specials",
        "pieces_before": len(tok["model"]["vocab"]),
        "pieces_after": len(keep),
        "embedding_rows_before": rows_before,
        "embedding_rows_after": rows_after,
        "source_sha256": meta.get("sha256", {}),
        "tool": "campuspulse_ai.frameworks.cli.prune_encoder",
    }
    with (out / META_FILE).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(new_meta, indent=2, sort_keys=True) + "\n")

    gate = check(src, out, keep, str(meta["query_prefix"]))
    _, knobs = load_knobs()
    measures = {
        name: [run_measure_subprocess(d, n, knobs) for n in knobs["measure_threads"]]
        for name, d in (("unpruned", src), ("pruned", out))
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pieces": {"before": len(tok["model"]["vocab"]), "after": len(keep)},
        "files_mb": {
            name: {f: round((d / f).stat().st_size / MB, 1) for f in (ONNX_FILE, TOKENIZER_FILE)}
            for name, d in (("unpruned", src), ("pruned", out))
        },
        "sha256_pruned": new_meta["sha256"],
        "gate": gate,
        "measure": measures,
        "installed": False,
    }
    if gate["passed"] and args.install:
        backup = REPO_ROOT / ".tmp" / "encoder.unpruned"  # outside the model dir: never committed or shipped
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(src, backup)
        for name in (ONNX_FILE, TOKENIZER_FILE, META_FILE):
            shutil.copy2(out / name, src / name)
        report["installed"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    m1 = {k: v[0] for k, v in measures.items()}
    verdict = "PASSED" if gate["passed"] else "FAILED"
    print(
        f"pieces {len(tok['model']['vocab'])} -> {len(keep)}; gate {verdict} (texts={gate['texts']}, "
        f"token_mismatches={gate['token_mismatches']}, min_cos={gate['min_cosine']:.6f}); "
        f"rss_mb_after_load {m1['unpruned']['rss_mb_after_load']} -> {m1['pruned']['rss_mb_after_load']} "
        f"(threads={m1['pruned']['threads']}); installed={report['installed']}"
    )
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
