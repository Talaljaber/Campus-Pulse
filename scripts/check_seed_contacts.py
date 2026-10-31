"""Seed lint (P4.3): every email address in supabase/seed/*.sql must be in DEMO_EMAIL_ALLOWLIST.

Uses the same RecipientPolicy as the notifier, so a seed that passes here can never produce a
send to a non-allow-listed address. Reads DEMO_EMAIL_ALLOWLIST from the env or the repo `.env`.

    python scripts/check_seed_contacts.py   ->  seed contacts OK: 6 addresses in 4 files, all allow-listed
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import RecipientNotAllowed
from campuspulse_ai.domain.policy import RecipientPolicy

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "supabase" / "seed"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def main() -> int:
    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    policy = RecipientPolicy(settings.demo_email_allowlist)
    files = sorted(SEED_DIR.glob("*.sql"))
    found = {
        addr.lower(): path.name for path in files for addr in EMAIL.findall(path.read_text(encoding="utf-8"))
    }
    missing = []
    for addr, name in sorted(found.items()):
        try:
            policy.check(addr)
        except RecipientNotAllowed:
            missing.append((addr, name))
    if missing:
        for addr, name in missing:
            print(f"NOT ALLOW-LISTED: {addr}  ({name})", file=sys.stderr)
        summary = f"{len(missing)} of {len(found)} addresses are not in DEMO_EMAIL_ALLOWLIST"
        print(f"seed contacts FAILED: {summary}", file=sys.stderr)
        return 1
    print(f"seed contacts OK: {len(found)} addresses in {len(files)} files, all allow-listed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
