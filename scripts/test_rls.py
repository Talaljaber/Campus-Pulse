"""Run the RLS proof (supabase/tests/rls.sql) and print "RLS: n/9 checks passed".

Default: `supabase db reset` on the local CLI stack (Docker Desktop), then run rls.sql with
psql, falling back to `docker exec ... psql` inside the local db container when psql is not
on PATH. `--db-url` runs against any Postgres URL instead (rls.sql always rolls back).
Exit code 0 only when every check passes.

    python scripts/test_rls.py                 # reset local stack + run
    python scripts/test_rls.py --no-reset      # run against the running local stack
    python scripts/test_rls.py --db-url postgresql://...
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RLS_SQL = ROOT / "supabase" / "tests" / "rls.sql"
LOCAL_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
SUMMARY = re.compile(r"RLS: (\d+)/(\d+) checks passed")


def _local_container() -> str:
    config = tomllib.loads((ROOT / "supabase" / "config.toml").read_text(encoding="utf-8"))
    return f"supabase_db_{config['project_id']}"


def _psql_command(db_url: str | None) -> list[str]:
    base = ["-X", "-q", "-A", "-t", "-F", "|", "-v", "ON_ERROR_STOP=1"]
    if shutil.which("psql"):
        return ["psql", db_url or LOCAL_DB_URL, *base]
    if db_url:
        sys.exit("psql is not on PATH; it is required with --db-url")
    return ["docker", "exec", "-i", _local_container(), "psql", "-U", "postgres", "-d", "postgres", *base]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-url", help="run against this Postgres URL instead of the local stack")
    parser.add_argument("--no-reset", action="store_true", help="skip `supabase db reset`")
    args = parser.parse_args()

    if not args.db_url and not args.no_reset:
        subprocess.run(["supabase", "db", "reset"], cwd=ROOT, check=True)

    proc = subprocess.run(
        _psql_command(args.db_url),
        input=RLS_SQL.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    summary = None
    for line in proc.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        if (match := SUMMARY.search(parts[1])) is not None:
            summary = match
            continue
        status = "ok  " if parts[2] == "t" else "FAIL"
        print(f"{status} {parts[0]:>2}. {parts[1]}  ({parts[3] if len(parts) > 3 else ''})")

    if summary is None:
        print("RLS: no summary row in psql output", file=sys.stderr)
        return 1
    print(summary.group(0))
    return 0 if summary.group(1) == summary.group(2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
