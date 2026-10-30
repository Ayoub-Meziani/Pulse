"""Throwaway Postgres for backend tests.

Same Supabase Postgres build as the live project (includes auth.users, auth.uid() and the
anon/authenticated/service_role roles). It never points at a shared database: containers are
local, bound to 127.0.0.1, and recreated on every `up`.

Two profiles, kept until every migration on the branch is verified live
(PULSE_DATABASE_SYNC_POLICY.md):
    latest  every file in supabase/migrations                 port 55432
    live    only migrations up to LIVE_UNTIL (= live pulse)   port 55433

    python scripts/test_db.py up [latest|live]     # (re)create, apply migrations, print the URL
    python scripts/test_db.py down [latest|live]   # remove the container

Then run the backend tests with PULSE_TEST_DATABASE_URL set to the printed URL.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# Build of the live project (PULSE_DATABASE_SYNC_POLICY.md). Same official image, two registries:
# the second is tried when the first refuses (e.g. anonymous rate limits on shared CI runners).
IMAGES = ("public.ecr.aws/supabase/postgres:17.11.0.003", "supabase/postgres:17.11.0.003")
PASSWORD = "pulse-test-only"
MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
# Last migration VERIFIED on the live project `pulse` (sync policy §5). Update only after verification.
LIVE_UNTIL = "20261030170000"  # M9 live_early_warning; M1-M9 verified live 2026-10-30 23:39 UTC (382/382, M9 file = AI blob 687c42f); M9 kept by Ayoub, applied without confirmed approval (incident 10d)
PROFILES = {"latest": ("pulse-test-db", 55432, None), "live": ("pulse-test-db-live", 55433, LIVE_UNTIL)}


def docker(*args: str, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], input=input, capture_output=True, check=check)


def psql(name: str, sql: bytes, user: str = "postgres") -> subprocess.CompletedProcess:
    return docker("exec", "-i", name, "psql", "-U", user, "-d", "postgres", "-h", "127.0.0.1",
                  "-v", "ON_ERROR_STOP=1", "-q", "-f", "-", input=sql, check=False)


def fail(message: str) -> None:
    if os.getenv("GITHUB_ACTIONS"):  # visible as a public annotation on the CI run
        print(f"::error title=test_db.py::{message.replace(chr(10), ' | ')[:900]}")
    sys.exit(message)


def ensure_image() -> str:
    """Use a local copy if present; otherwise pull, retrying each registry."""
    for image in IMAGES:
        if docker("image", "inspect", image, check=False).returncode == 0:
            return image
    errors = []
    for attempt in range(3):
        for image in IMAGES:
            r = docker("pull", "--quiet", image, check=False)
            if r.returncode == 0:
                return image
            errors.append(f"{image}: {r.stderr.decode(errors='replace').strip()[:200]}")
        time.sleep(5 * (attempt + 1))
    fail("could not pull the test database image; " + " || ".join(errors[-2:]))


def wait_ready(name: str, timeout: float = 180) -> None:
    # The image restarts Postgres once after its init scripts, so wait until auth.users is queryable twice.
    deadline, ok = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        ok = ok + 1 if psql(name, b"select 1 from auth.users limit 0;").returncode == 0 else 0
        if ok >= 2:
            return
        time.sleep(2)
    logs = docker("logs", "--tail", "20", name, check=False)
    fail("test database did not become ready; " + logs.stderr.decode(errors="replace")[-600:])


def migrations(until: str | None) -> list[Path]:
    files = sorted(MIGRATIONS.glob("*.sql"))
    return [f for f in files if until is None or f.name.split("_", 1)[0] <= until]


def up(profile: str) -> None:
    name, port, until = PROFILES[profile]
    files = migrations(until)
    if not files:
        sys.exit(f"no migrations in {MIGRATIONS}")
    image = ensure_image()
    docker("rm", "-f", name, check=False)
    r = docker("run", "-d", "--name", name, "-e", f"POSTGRES_PASSWORD={PASSWORD}",
               "-p", f"127.0.0.1:{port}:5432", image, check=False)
    if r.returncode != 0:
        fail(f"docker run failed: {r.stderr.decode(errors='replace').strip()[:600]}")
    print(f"[{profile}] {image}")
    wait_ready(name)
    compat = Path(__file__).with_name("test_db_auth_live.sql")  # live auth.uid()/jwt() definitions
    r = psql(name, compat.read_bytes(), user="supabase_admin")  # auth schema is not owned by postgres
    if r.returncode != 0:
        fail(f"{compat.name} failed:\n{r.stderr.decode(errors='replace')}")
    print(f"[{profile}] applied {compat.name}")
    for f in files:
        r = psql(name, f.read_bytes())
        if r.returncode != 0:
            fail(f"migration {f.name} failed:\n{r.stderr.decode(errors='replace')}")
        print(f"[{profile}] applied {f.name}")
    print(f"PULSE_TEST_DATABASE_URL=postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:{port}/postgres")


def down(profile: str) -> None:
    name = PROFILES[profile][0]
    docker("rm", "-f", name, check=False)
    print(f"removed {name}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    profile = sys.argv[2] if len(sys.argv) > 2 else "latest"
    if cmd not in ("up", "down") or profile not in PROFILES:
        sys.exit(__doc__)
    (up if cmd == "up" else down)(profile)
