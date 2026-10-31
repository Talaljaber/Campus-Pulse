"""Create or refresh the three demo logins and their profiles (P4.3). Dev machine only.

Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY and DEMO_USER_PASSWORD (env or repo `.env`).
The addresses are on the reserved-style `demo.local` domain: they are login names only, no mail
is ever sent to them (users are created already confirmed). All three share DEMO_USER_PASSWORD.
Idempotent: an existing user gets its password reset and its profile upserted; a user still on
a previous login name is renamed in place (same id, so its rows stay linked).

    python scripts/seed_demo_users.py   ->  3 users ready
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

from campuspulse_ai.config.settings import Settings

ROOT = Path(__file__).resolve().parents[1]

# (email, role, office, alias, previous login names) — office codes match tickets.office
# (docs/db/schema.md). Login names chosen by the user on 2026-10-31.
DEMO_USERS = (
    ("talal@demo.local", "student", None, "talal", ("student-demo-17@demo.local",)),
    ("it@demo.local", "staff", "it", "staff-it", ("staff-it@demo.local",)),
    ("admin@demo.local", "admin", None, "admin", ()),
)


def main() -> int:
    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    password = (
        os.environ.get("DEMO_USER_PASSWORD") or dotenv_values(ROOT / ".env").get("DEMO_USER_PASSWORD") or ""
    ).strip()
    key = settings.supabase_service_role_key
    if not settings.supabase_url or key is None or not password:
        print("needs SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and DEMO_USER_PASSWORD", file=sys.stderr)
        return 2

    from supabase import create_client

    client = create_client(settings.supabase_url, key.get_secret_value())
    existing = {u.email: u.id for u in client.auth.admin.list_users(per_page=1000)}
    for email, role, office, alias, previous in DEMO_USERS:
        old = next((e for e in previous if e in existing), None)
        if email in existing:
            uid = existing[email]
            client.auth.admin.update_user_by_id(uid, {"password": password})
            action = "updated"
        elif old is not None:
            uid = existing[old]
            client.auth.admin.update_user_by_id(
                uid, {"email": email, "password": password, "email_confirm": True}
            )
            action = f"renamed (was {old})"
        else:
            created = client.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
            uid = created.user.id
            action = "created"
        client.table("profiles").upsert({"id": uid, "role": role, "office": office, "alias": alias}).execute()
        print(f"{action}: {email} role={role} office={office or '-'} alias={alias}")
    print(f"{len(DEMO_USERS)} users ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
