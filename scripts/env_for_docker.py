"""Write a comment-free copy of `.env` that `docker run --env-file` can read (P4.13).

`docker run --env-file` takes every line literally: `ENABLE_LLM=false   # scope: ai` becomes the value
`false   # scope: ai`, and quotes are kept. This script parses `.env` the way the app does
(python-dotenv: inline comments and quotes stripped, empty values dropped) and writes plain
`KEY=value` lines to a temporary file outside the repo, then prints its path.

    python scripts/env_for_docker.py                       # -> C:\\Users\\...\\Temp\\cp-docker-xxxx.env
    python scripts/env_for_docker.py --set ENABLE_SINKS=false --set SLA_SCAN_MINUTES=0 \
        --unset GMAIL_APP_PASSWORD
    docker run --rm -m 512m --cpus 0.5 -p 8000:10000 --env-file <printed path> campuspulse-ai

The output holds secrets: it is created with owner-only permissions where the OS supports it, never
inside the repository (`--out` refuses a path under the repo root), and should be deleted after use.
Values are never printed. Exit codes: 0 written; 2 bad arguments, a missing `.env`, a path inside the
repo, or a value docker cannot carry (a newline).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "cp-docker-"
SUFFIX = ".env"
OWNER_ONLY = 0o600


def clean_env(source: Path, sets: list[str], unsets: list[str]) -> dict[str, str]:
    """The parsed `.env` (non-empty values only) with `--set KEY=VALUE` and `--unset KEY` applied.
    Raises `ValueError` for a malformed `--set` or a value with a newline."""
    values = {k: v for k, v in dotenv_values(source).items() if v}
    for item in sets:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"--set needs KEY=VALUE, got {item!r}")
        values[key.strip()] = value
    for key in unsets:
        values.pop(key.strip(), None)
    bad = sorted(k for k, v in values.items() if "\n" in v or "\r" in v)
    if bad:
        raise ValueError(f"docker --env-file cannot carry multi-line values: {bad}")
    return values


def write_env(values: dict[str, str], out: Path | None) -> Path:
    """Write `KEY=value` lines to `out` (or a new temp file) with owner-only permissions."""
    if out is None:
        fd, name = tempfile.mkstemp(prefix=PREFIX, suffix=SUFFIX)
        os.close(fd)
        out = Path(name)
    out.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8", newline="\n")
    with contextlib.suppress(OSError):  # Windows ignores POSIX modes; its temp dir is per-user
        out.chmod(OWNER_ONLY)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=ROOT / ".env", help="source .env (default: repo root)")
    parser.add_argument("--out", type=Path, default=None, help="output path (default: a new temp file)")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a value")
    parser.add_argument("--unset", action="append", default=[], metavar="KEY", help="drop a key")
    args = parser.parse_args(argv)
    if not args.env.is_file():
        print(f"no env file at {args.env}", file=sys.stderr)
        return 2
    if args.out is not None and args.out.resolve().is_relative_to(ROOT):
        print("refused: --out must be outside the repository (the file holds secrets)", file=sys.stderr)
        return 2
    try:
        values = clean_env(args.env, args.set, args.unset)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    path = write_env(values, args.out)
    print(path)
    print(f"{len(values)} variables; delete the file after use", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
