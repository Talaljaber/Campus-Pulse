"""Local demo fallback (P8.8): the whole product on one laptop, no hosted service needed.

Needs Docker Desktop running (local Supabase), the Supabase CLI, Node 22 + pnpm, and the Python
venv from docs/ops/README.md with the encoder fetched (`python scripts/fetch_models.py`).
Nothing here talks to a hosted service, an LLM or a mail server: ENABLE_LLM, Linear and Gmail are
forced off and `DEMO_EMAIL_ALLOWLIST` is empty, so no message can leave the machine.

    python scripts/demo_local.py setup   # once: start local Supabase, migrate, seed, create the logins
    python scripts/demo_local.py api     # terminal 1: the API on http://localhost:8000
    python scripts/demo_local.py web     # terminal 2: the web app on http://localhost:3000

`setup` writes `.env.demo.local` (gitignored, holds only the local-stack keys). The logins are the
`@demo.local` ones of scripts/seed_demo_users.py; the password is `DEMO_LOCAL_PASSWORD` or the
default below.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.demo.local"
API_PORT = "8000"
DEFAULT_PASSWORD = "campuspulse-demo"
# Hard-off switches: the local demo never reaches a third party.
OFFLINE = {
    "ENABLE_LLM": "false",
    "ENABLE_SINKS": "false",
    "LLM_ARABIZI_TRANSLATE": "false",
    "GMAIL_SMTP_USER": "",
    "GMAIL_APP_PASSWORD": "",
    "LINEAR_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "DEMO_EMAIL_ALLOWLIST": "",
    "DEMO_STUDENT_INBOX": "",
    "DEMO_OFFICE_INBOX": "",
    "AUTH_MODE": "supabase_jwt",
}


def run(cmd: list[str], *, env: dict[str, str] | None = None, capture: bool = False) -> str:
    exe = shutil.which(cmd[0]) or cmd[0]
    print("+", " ".join(cmd), flush=True)
    done = subprocess.run(
        [exe, *cmd[1:]], cwd=ROOT, env=env, check=True, text=True, stdout=subprocess.PIPE if capture else None
    )
    return done.stdout or ""


def load_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        sys.exit("no .env.demo.local yet: run `python scripts/demo_local.py setup` first")
    values = {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None}
    return {**os.environ, **values}


def grant_service_role(project_dir: Path) -> None:
    """A fresh local stack does not auto-grant new tables to `service_role` (the migrations rely on the
    hosted project's default privileges), so the API would get `permission denied`. Grant them in the
    local database only, through the db container."""
    config = (project_dir / "supabase" / "config.toml").read_text(encoding="utf-8")
    id_line = next(line for line in config.splitlines() if line.startswith("project_id"))
    project_id = id_line.split("=", 1)[1].strip().strip('"')
    sql = (
        "grant usage on schema public to service_role;"
        "grant all on all tables in schema public to service_role;"
        "grant all on all sequences in schema public to service_role;"
        "grant execute on all functions in schema public to service_role;"
    )
    run(["docker", "exec", f"supabase_db_{project_id}", "psql", "-U", "postgres", "-q", "-c", sql])


def setup() -> int:
    docker = shutil.which("docker")
    if docker is None or subprocess.run([docker, "info"], capture_output=True).returncode:
        sys.exit("Docker is not running: start Docker Desktop, wait until it says running, retry")
    # DEMO_SUPABASE_WORKDIR: a folder holding a supabase/ copy with other ports, when 54321-54329 are taken.
    workdir = os.environ.get("DEMO_SUPABASE_WORKDIR")
    sb = ["supabase", *(["--workdir", workdir] if workdir else [])]
    # Skip what the demo does not use; the analytics container (logflare) does not start on Windows.
    run([*sb, "start", "-x", "logflare,vector,imgproxy,edge-runtime,studio,supavisor"])
    # A first `start` already applied supabase/migrations and supabase/seed. For a clean slate:
    # `supabase stop --no-backup` first (local containers only).
    grant_service_role(Path(workdir) if workdir else ROOT)
    status: dict[str, str] = {}
    for line in run([*sb, "status", "-o", "env"], capture=True).splitlines():
        key, sep, val = line.partition("=")
        if sep:
            status[key.strip()] = val.strip().strip('"')
    values = {
        "SUPABASE_URL": status["API_URL"],
        "SUPABASE_SERVICE_ROLE_KEY": status["SERVICE_ROLE_KEY"],
        "NEXT_PUBLIC_SUPABASE_URL": status["API_URL"],
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": status["ANON_KEY"],
        "AI_SERVICE_URL": f"http://localhost:{API_PORT}",
        "AI_SERVICE_TOKEN": secrets.token_urlsafe(24),
        "DEMO_USER_PASSWORD": os.environ.get("DEMO_LOCAL_PASSWORD", DEFAULT_PASSWORD),
        **OFFLINE,
    }
    ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    env = {**os.environ, **values}
    run([sys.executable, "scripts/seed_faq.py"], env=env)
    run([sys.executable, "scripts/seed_demo_users.py"], env=env)
    print(
        "\nready. Next: `python scripts/demo_local.py api`, then `... web`, then open http://localhost:3000"
    )
    return 0


def api() -> int:
    env = load_env()
    env.setdefault("ORT_INTRA_OP_THREADS", "4")
    cmd = [sys.executable, "-m", "uvicorn", "api:app", "--app-dir", "services/ai", "--port", API_PORT]
    return subprocess.call(cmd, cwd=ROOT, env=env)


def web() -> int:
    env = load_env()
    web_dir = ROOT / "apps" / "web"
    if not (web_dir / "node_modules").is_dir():
        run(["pnpm", "install", "--frozen-lockfile"])
    return subprocess.call([shutil.which("pnpm") or "pnpm", "dev"], cwd=web_dir, env=env)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) == 2 else ""
    handlers = {"setup": setup, "api": api, "web": web}
    if cmd not in handlers:
        print(__doc__)
        return 2
    return handlers[cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
