"""Create or refresh the demo logins and their profiles (P4.3, P9.1). Dev machine only.

Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY and DEMO_USER_PASSWORD (env or repo `.env`).
The addresses are on the reserved-style `demo.local` domain: they are login names only, no mail
is ever sent to them (users are created already confirmed). Everyone shares DEMO_USER_PASSWORD.
All people are fictional: 3 students, 6 office staff, 1 admin. The directory columns added by
migration 0013 (display name, student number, faculty, university email) are upserted too.
Idempotent: an existing user gets its password reset and its profile upserted; a user still on
a previous login name is renamed in place (same id, so its rows stay linked).

`advisor@demo.local` is no longer managed (advisor routing left the product in P9): an existing
account is left untouched.

    python scripts/seed_demo_users.py   ->  10 users ready
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from campuspulse_ai.config.settings import Settings

ROOT = Path(__file__).resolve().parents[1]

DEMO_DOMAIN = "demo.local"
STUDENT_DOMAIN = "student.demo.local"
UNMANAGED_LOGIN = "advisor@demo.local"


@dataclass(frozen=True)
class DemoUser:
    username: str
    role: str
    office: str | None
    alias: str
    display_name: str
    student_number: str | None = None
    faculty: str | None = None
    previous: tuple[str, ...] = ()  # earlier login names, renamed in place

    @property
    def email(self) -> str:
        return f"{self.username}@{DEMO_DOMAIN}"

    @property
    def university_email(self) -> str | None:
        """Fictional student mailbox shown on the Profile page; never mailed."""
        return f"{self.username}@{STUDENT_DOMAIN}" if self.role == "student" else None

    def profile_row(self, uid: str) -> dict[str, object]:
        return {
            "id": uid,
            "role": self.role,
            "office": self.office,
            "alias": self.alias,
            "display_name": self.display_name,
            "student_number": self.student_number,
            "faculty": self.faculty,
            "university_email": self.university_email,
        }


# Office codes match tickets.office (docs/db/schema.md); the label is the desk's demo display name.
OFFICES = (
    ("registrar", "Registrar"),
    ("it", "IT"),
    ("finance", "Finance"),
    ("transport", "Transport"),
    ("facilities", "Facilities"),
    ("academic", "Academic"),
)
ENGINEERING = "Faculty of Engineering (demo)"
BUSINESS = "Faculty of Business (demo)"

DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser("talal", "student", None, "talal", "Talal Jaber", "20230017", ENGINEERING,
             previous=("student-demo-17@demo.local",)),
    DemoUser("lina", "student", None, "lina", "Lina Haddad", "20230042", BUSINESS),
    DemoUser("omar", "student", None, "omar", "Omar Saleh", "20220311", ENGINEERING),
    *(
        DemoUser(
            code, "staff", code, f"staff-{code}", f"{label} Desk (demo)",
            previous=("staff-it@demo.local",) if code == "it" else (),
        )
        for code, label in OFFICES
    ),
    DemoUser("admin", "admin", None, "admin", "Admin (demo)"),
)  # fmt: skip


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
    for user in DEMO_USERS:
        old = next((e for e in user.previous if e in existing), None)
        if user.email in existing:
            uid = existing[user.email]
            client.auth.admin.update_user_by_id(uid, {"password": password})
            action = "updated"
        elif old is not None:
            uid = existing[old]
            client.auth.admin.update_user_by_id(
                uid, {"email": user.email, "password": password, "email_confirm": True}
            )
            action = f"renamed (was {old})"
        else:
            created = client.auth.admin.create_user(
                {"email": user.email, "password": password, "email_confirm": True}
            )
            uid = created.user.id
            action = "created"
        client.table("profiles").upsert(user.profile_row(uid)).execute()
        print(f"{action}: {user.email} role={user.role} office={user.office or '-'} alias={user.alias}")
    if UNMANAGED_LOGIN in existing:
        print(f"note: {UNMANAGED_LOGIN} exists and is left untouched (advisor logins are no longer seeded)")
    print(f"{len(DEMO_USERS)} users ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
