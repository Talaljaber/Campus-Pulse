"""Fetch the frozen encoder into `models/frozen/v1/encoder/` and verify it (P1.17, ARCHITECTURE §3.12).

    python scripts/fetch_models.py [--tag models-v1-rc1] [--source {github,hf}] [--from-file <tar.gz>]
                                   [--model-dir models/frozen/v1] [--force]

The small artifacts (heads, index, config, MANIFEST.json) are committed; only the encoder (> 100 MB) is a
release asset: `campuspulse-models-v1.tar.gz` (the `encoder/` folder) plus `SHA256SUMS`.

Flow: (1) if every file in MANIFEST.json already verifies, print `up to date` and exit 0 (unless `--force`);
(2) download the tarball and SHA256SUMS (or take `--from-file`, whose SHA256SUMS is read from the same folder
when present) into `models/frozen/.cache/`; (3) check the tarball's sha256; (4) extract with
`tarfile` `filter="data"` (no absolute paths, `..` or links), only under `encoder/`; (5) verify every file
in MANIFEST.json. Success: `verified <n> files against MANIFEST.json (v1 sha=<12 hex>)`.

Exit codes: 0 ok · 2 checksum or manifest mismatch (expected and actual sha printed) · 3 network error (the
manual URL and the `--from-file` hint are printed). Stdlib only, so it runs straight after
`pip install -r services/ai/requirements.txt`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = REPO_ROOT / "models" / "frozen" / "v1"
DEFAULT_TAG = "models-v1-rc1"
ASSET = "campuspulse-models-v1.tar.gz"
SUMS = "SHA256SUMS"
GITHUB_URL = "https://github.com/Talaljaber/Ai-Quest/releases/download/{tag}/{name}"
HF_REPO_ENV = "CAMPUSPULSE_HF_REPO"  # e.g. <user>/campuspulse-models (the backup mirror, ARCHITECTURE §3.12)
HF_URL = "https://huggingface.co/{repo}/resolve/{tag}/{name}"
EXTRACT_PREFIX = "encoder/"
CHUNK = 1 << 20
TIMEOUT_S = 60
EXIT_OK, EXIT_CHECKSUM, EXIT_NETWORK = 0, 2, 3


class FetchError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_sha(files: dict[str, str]) -> str:
    """Same identity as `domain.values.Manifest.sha`: sha256 over sorted `path:digest` lines."""
    lines = "\n".join(f"{p}:{d}" for p, d in sorted(files.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def load_manifest(model_dir: Path) -> tuple[str, dict[str, str]]:
    path = model_dir / "MANIFEST.json"
    if not path.is_file():
        raise FetchError(
            f"{path} not found: clone the repo (the manifest is committed) or run train.py", EXIT_CHECKSUM
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data["artifact_version"]), {str(k): str(v) for k, v in data["files"].items()}


def verify(model_dir: Path, files: dict[str, str]) -> list[str]:
    """Problems with the files listed in the manifest (empty = all present and matching)."""
    problems = []
    for rel, expected in sorted(files.items()):
        full = model_dir / rel
        if not full.is_file():
            problems.append(f"missing {rel}")
        elif (actual := sha256_file(full)) != expected:
            problems.append(f"sha256 mismatch for {rel}: expected {expected}, got {actual}")
    return problems


def _download(url: str, dest: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp, dest.open("wb") as fh:  # noqa: S310
            shutil.copyfileobj(resp, fh, CHUNK)
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(
            f"download failed: {url}: {exc}\nDownload it manually and run: "
            f"python scripts/fetch_models.py --from-file <path to {ASSET}>",
            EXIT_NETWORK,
        ) from exc


def _expected_sum(sums_file: Path, name: str) -> str | None:
    if not sums_file.is_file():
        return None
    for line in sums_file.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def _extract(tar_path: Path, model_dir: Path) -> None:
    with tarfile.open(tar_path, "r:gz") as tar:
        members = []
        for m in tar.getmembers():
            name = PurePosixPath(m.name).as_posix().removeprefix("./")
            if not (name == EXTRACT_PREFIX.rstrip("/") or name.startswith(EXTRACT_PREFIX)):
                raise FetchError(
                    f"{tar_path}: unexpected member {m.name!r} (only {EXTRACT_PREFIX} is allowed)",
                    EXIT_CHECKSUM,
                )
            members.append(m)
        tar.extractall(model_dir, members=members, filter="data")


def fetch(args: argparse.Namespace) -> str:
    model_dir: Path = args.model_dir.resolve()
    version, files = load_manifest(model_dir)
    if not args.force and not verify(model_dir, files):
        sha = manifest_sha(files)[:12]
        return f"up to date: verified {len(files)} files against MANIFEST.json ({version} sha={sha})"
    cache = model_dir.parent / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    if args.from_file:
        tar_path = Path(args.from_file).resolve()
        sums_path = tar_path.parent / SUMS
    else:
        if args.source == "hf":
            repo = os.environ.get(HF_REPO_ENV)
            if not repo:
                raise FetchError(f"--source hf needs {HF_REPO_ENV}=<user>/<repo>", EXIT_NETWORK)
            url = HF_URL.format(repo=repo, tag=args.tag, name="{name}")
        else:
            url = GITHUB_URL.format(tag=args.tag, name="{name}")
        tar_path, sums_path = cache / ASSET, cache / SUMS
        _download(url.format(name=SUMS), sums_path)
        _download(url.format(name=ASSET), tar_path)
    expected = _expected_sum(sums_path, ASSET)
    actual = sha256_file(tar_path)
    if expected is None and not args.from_file:
        raise FetchError(f"{SUMS} does not list {ASSET}", EXIT_CHECKSUM)
    if expected is not None and expected != actual:
        raise FetchError(f"{ASSET}: sha256 expected {expected}, got {actual}", EXIT_CHECKSUM)
    _extract(tar_path, model_dir)
    problems = verify(model_dir, files)
    if problems:
        raise FetchError("\n".join(problems), EXIT_CHECKSUM)
    return f"verified {len(files)} files against MANIFEST.json ({version} sha={manifest_sha(files)[:12]})"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", default=DEFAULT_TAG, help="release tag (default %(default)s)")
    ap.add_argument("--source", choices=("github", "hf"), default="github")
    ap.add_argument("--from-file", type=Path, default=None, help="a downloaded campuspulse-models-v1.tar.gz")
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    ap.add_argument("--force", action="store_true", help="fetch even if the files already verify")
    try:
        print(fetch(ap.parse_args(argv)))
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
