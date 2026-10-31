"""`FileArtifactStore`: checksummed artifact I/O for a frozen model directory (P1.4, ARCHITECTURE §3.12).

`MANIFEST.json` (in the model dir) lists every artifact file by its POSIX path relative to the model dir,
with its sha256. `load_manifest` re-hashes every listed file, so a tampered, truncated or missing file
fails loudly before any model is loaded:

    {
      "artifact_version": "v1",
      "created_at": "2026-11-01T10:00:00+00:00",
      "files": {"config.json": "<sha256>", "encoder/model_int8.onnx": "<sha256>", ...}
    }

The manifest itself is never listed. `Manifest.sha` (domain) is the identity reported by `/health` and
`predict.py --debug`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from campuspulse_ai.domain.errors import ArtifactChecksumMismatch, ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.values import Manifest

MANIFEST_NAME = "MANIFEST.json"
CONFIG_NAME = "config.json"
FETCH_HINT = "run `python scripts/fetch_models.py` to download the frozen artifacts"
_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file, read in 1 MiB chunks (the encoder is ~120 MB)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FileArtifactStore:
    """Implements `domain.ports.ArtifactStore` over the local filesystem."""

    def __init__(self, now: Callable[[], datetime] = _utc_now) -> None:
        """
        Args:
            now: clock for `created_at` (inject a fixed one for byte-reproducible manifests).
        """
        self._now = now

    @staticmethod
    def _relpath(model_dir: Path, file: Path) -> str:
        full = file if file.is_absolute() else model_dir / file
        try:
            rel = full.resolve().relative_to(model_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"{file} is outside the model dir {model_dir}") from exc
        return rel.as_posix()

    @staticmethod
    def _artifact_version(model_dir: Path) -> str:
        config = model_dir / CONFIG_NAME
        if config.is_file():
            try:
                version = json.loads(config.read_text(encoding="utf-8")).get("artifact_version")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                version = None
            if isinstance(version, str) and version:
                return version
        return model_dir.name

    def write_manifest(self, model_dir: Path, files: Sequence[Path]) -> Manifest:
        """Hash `files` and write `model_dir/MANIFEST.json` (sorted keys, indent 2, LF).

        Args:
            model_dir: the frozen model directory, e.g. `models/frozen/v1`.
            files: artifact files, absolute or relative to `model_dir`; duplicates are merged.

        Returns:
            The written `Manifest`. `artifact_version` comes from `config.json` if present, else the dir name.

        Raises:
            ArtifactMissing: a listed file does not exist.
            ValueError: a file lies outside `model_dir`, or is the manifest itself.
        """
        model_dir = Path(model_dir)
        hashes: dict[str, str] = {}
        for file in files:
            rel = self._relpath(model_dir, Path(file))
            if rel == MANIFEST_NAME:
                raise ValueError("MANIFEST.json cannot list itself")
            full = model_dir / rel
            if not full.is_file():
                raise ArtifactMissing(f"cannot hash missing artifact {full}")
            hashes[rel] = sha256_file(full)
        manifest = Manifest(
            artifact_version=self._artifact_version(model_dir),
            files=dict(sorted(hashes.items())),
            created_at=self._now().isoformat(timespec="seconds"),
        )
        payload = {
            "artifact_version": manifest.artifact_version,
            "created_at": manifest.created_at,
            "files": dict(manifest.files),
        }
        with (model_dir / MANIFEST_NAME).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        return manifest

    def load_manifest(self, model_dir: Path) -> Manifest:
        """Read `MANIFEST.json` and verify the sha256 of every listed file.

        Raises:
            ArtifactMissing: the manifest or a listed file is absent (the message has the fetch hint).
            ArtifactVersionMismatch: the manifest is malformed, lists an unsafe path, or disagrees with
                `config.json` about `artifact_version`.
            ArtifactChecksumMismatch: a file's sha256 differs from the manifest.
        """
        model_dir = Path(model_dir)
        path = model_dir / MANIFEST_NAME
        if not path.is_file():
            raise ArtifactMissing(f"{path} not found; {FETCH_HINT}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            version, created, files = data["artifact_version"], data["created_at"], data["files"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ArtifactVersionMismatch(f"{path}: malformed manifest: {exc}") from exc
        if not (isinstance(version, str) and isinstance(created, str) and isinstance(files, dict)):
            raise ArtifactVersionMismatch(f"{path}: malformed manifest field types")
        for rel, expected in sorted(files.items()):
            pure = PurePosixPath(rel)
            if not isinstance(expected, str) or pure.is_absolute() or ".." in pure.parts:
                raise ArtifactVersionMismatch(f"{path}: unsafe or invalid entry {rel!r}")
            full = model_dir / rel
            if not full.is_file():
                raise ArtifactMissing(f"artifact {full} is missing; {FETCH_HINT}")
            actual = sha256_file(full)
            if actual != expected:
                raise ArtifactChecksumMismatch(f"{full}: sha256 {actual} != manifest {expected}")
        if CONFIG_NAME in files and self._artifact_version(model_dir) != version:
            raise ArtifactVersionMismatch(f"{path}: artifact_version {version!r} differs from {CONFIG_NAME}")
        return Manifest(artifact_version=version, files=dict(files), created_at=created)
