#!/usr/bin/env python3
"""P7.1: build a scratch model dir to test lexicon edits without touching `models/frozen/v1`.

    python scripts/scratch_model.py --out .tmp/<pkg>/model [--lexicons config/lexicons]
                                    [--from models/frozen/v1]

Copies the frozen dir (encoder and translator included), overwrites its `lexicons/` with the given
directory, rewrites `MANIFEST.json` over the same file list (lexicon entries follow the new directory) and
prints the new artifact sha. The result loads in `build_offline` (`predict.py --model-dir <out>`).
Refuses an `--out` under `models/`, so a scratch copy can never shadow a frozen model.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "ai"))

from campuspulse_ai.adapters.artifacts.io import MANIFEST_NAME, FileArtifactStore  # noqa: E402

LEXICON_DIR = "lexicons"


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def build_scratch(out: Path, lexicons: Path, source: Path, models_root: Path | None = None) -> str:
    """Create the scratch model dir `out` and return its manifest sha.

    Raises:
        ValueError: `out` lies under `models_root` (default: the repo's `models/`) or already exists.
        FileNotFoundError: `source` or `lexicons` is not a directory.
    """
    out = out.resolve()
    models_root = models_root if models_root is not None else ROOT / "models"
    if _is_under(out, models_root):
        raise ValueError(f"--out {out} is under {models_root}: scratch models never go there")
    if not source.is_dir():
        raise FileNotFoundError(f"--from {source} is not a directory")
    if not lexicons.is_dir():
        raise FileNotFoundError(f"--lexicons {lexicons} is not a directory")
    if out.exists():
        raise ValueError(f"--out {out} already exists; remove it or pick another path")
    shutil.copytree(source, out)
    shutil.rmtree(out / LEXICON_DIR, ignore_errors=True)
    shutil.copytree(lexicons, out / LEXICON_DIR)
    store = FileArtifactStore()
    listed = json.loads((source / MANIFEST_NAME).read_text(encoding="utf-8"))["files"]
    kept = [rel for rel in listed if not rel.startswith(f"{LEXICON_DIR}/")]
    files = [out / rel for rel in kept]
    files += sorted(p for p in (out / LEXICON_DIR).rglob("*") if p.is_file())
    return store.write_manifest(out, [f for f in files if f.name != MANIFEST_NAME]).sha


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scratch_model.py", description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lexicons", type=Path, default=ROOT / "config" / "lexicons")
    ap.add_argument("--from", dest="source", type=Path, default=ROOT / "models" / "frozen" / "v1")
    args = ap.parse_args(argv)
    try:
        sha = build_scratch(args.out, args.lexicons, args.source)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"scratch model {args.out} (sha={sha[:12]}, full {sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
