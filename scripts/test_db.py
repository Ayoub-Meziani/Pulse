"""Throwaway Postgres for backend tests.

Same Supabase Postgres build as the live project (includes auth.users, auth.uid() and the
anon/authenticated/service_role roles) with every file of supabase/migrations applied in order.
It never points at a shared database: the container is local, bound to 127.0.0.1, and recreated
on every `up`.

    python scripts/test_db.py up      # (re)create the container, apply migrations, print the URL
    python scripts/test_db.py down    # remove the container

Then run the backend tests with PULSE_TEST_DATABASE_URL set to the printed URL.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

IMAGE = "public.ecr.aws/supabase/postgres:17.11.0.003"  # build of the live project (PULSE_DATABASE_SYNC_POLICY.md)
NAME = "pulse-test-db"
PORT = 55432
PASSWORD = "pulse-test-only"
URL = f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:{PORT}/postgres"
MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def docker(*args: str, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], input=input, capture_output=True, check=check)


def psql(sql: bytes, user: str = "postgres") -> subprocess.CompletedProcess:
    return docker("exec", "-i", NAME, "psql", "-U", user, "-d", "postgres", "-h", "127.0.0.1",
                  "-v", "ON_ERROR_STOP=1", "-q", "-f", "-", input=sql, check=False)


def wait_ready(timeout: float = 180) -> None:
    # The image restarts Postgres once after its init scripts, so wait until auth.users is queryable twice.
    deadline, ok = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        ok = ok + 1 if psql(b"select 1 from auth.users limit 0;").returncode == 0 else 0
        if ok >= 2:
            return
        time.sleep(2)
    sys.exit("test database did not become ready")


def up() -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        sys.exit(f"no migrations in {MIGRATIONS}")
    docker("rm", "-f", NAME, check=False)
    docker("run", "-d", "--name", NAME, "-e", f"POSTGRES_PASSWORD={PASSWORD}",
           "-p", f"127.0.0.1:{PORT}:5432", IMAGE)
    wait_ready()
    compat = Path(__file__).with_name("test_db_auth_live.sql")  # live auth.uid()/jwt() definitions
    r = psql(compat.read_bytes(), user="supabase_admin")  # auth schema is not owned by postgres
    if r.returncode != 0:
        sys.exit(f"{compat.name} failed:\n{r.stderr.decode(errors='replace')}")
    print(f"applied {compat.name}")
    for f in files:
        r = psql(f.read_bytes())
        if r.returncode != 0:
            sys.exit(f"migration {f.name} failed:\n{r.stderr.decode(errors='replace')}")
        print(f"applied {f.name}")
    print(f"PULSE_TEST_DATABASE_URL={URL}")


def down() -> None:
    docker("rm", "-f", NAME, check=False)
    print(f"removed {NAME}")


if __name__ == "__main__":
    {"up": up, "down": down}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
