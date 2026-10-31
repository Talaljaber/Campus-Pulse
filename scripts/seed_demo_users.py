"""Create or refresh the four demo logins and their profiles (P4.3, UD-13). Dev machine only.

Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY and DEMO_USER_PASSWORD (env or repo `.env`).
The addresses are on the reserved-style `demo.local` domain: they are login names only, no mail
is ever sent to them (users are created already confirmed). All four share DEMO_USER_PASSWORD.
The advisor login is linked to its fictional advisors row, and the demo student to that advisor.
Idempotent: an existing user gets its password reset and its profile upserted; a user still on
a previous login name is renamed in place (same id, so its rows stay linked).

    python scripts/seed_demo_users.py   ->  4 users ready
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
    ("advisor@demo.local", "staff", "academic", "advisor", ()),
)
# UD-13: the advisor login is the fictional advisor a…0001 (seed 02_advisors.sql; its demo_email is
# an allow-listed inbox), and it is the demo student's own advisor.
ADVISOR_LOGINS = (("advisor@demo.local", "a0000000-0000-4000-8000-000000000001"),)
STUDENT_ADVISORS = (("talal@demo.local", "a0000000-0000-4000-8000-000000000001"),)


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
    uids: dict[str, str] = {}
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
        uids[email] = uid
        print(f"{action}: {email} role={role} office={office or '-'} alias={alias}")
    for email, advisor_id in ADVISOR_LOGINS:
        client.table("advisors").update({"profile_id": uids[email]}).eq("id", advisor_id).execute()
        print(f"linked: {email} is advisor {advisor_id}")
    for email, advisor_id in STUDENT_ADVISORS:
        client.table("profiles").update({"advisor_id": advisor_id}).eq("id", uids[email]).execute()
        print(f"linked: {email} has advisor {advisor_id}")
    print(f"{len(DEMO_USERS)} users ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
