"""Local development stack for the full app: Supabase Postgres + Supabase Auth (GoTrue) + gateway.

Everything is local, bound to 127.0.0.1, on a private Docker network. It never points at a shared or
cloud project. The database gets exactly the migrations verified live (up to LIVE_UNTIL in test_db.py,
so a migration that is not live yet is never applied here).

    python scripts/dev_stack.py up        # create the stack (fresh database) and write .dev/api.env
    python scripts/dev_stack.py stop      # stop the containers, keep the data
    python scripts/dev_stack.py start     # start them again
    python scripts/dev_stack.py status
    python scripts/dev_stack.py down      # remove the containers and their data (asks to type 'yes')

`up` does not create accounts or data: demo accounts are a separate, explicit step
(python scripts/dev_seed.py). Why not `supabase start`: on this team's Windows machine the CLI's
database start fails (PULSE_DATABASE_SYNC_POLICY.md §4); this script uses the same official images.

Auth signs ES256 tokens like the cloud project, so the API's JWKS verification is the production path.
Local secrets (database password, signing key) are generated per stack and stay in .dev/ (git-ignored).
"""
from __future__ import annotations

import base64
import json
import secrets
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from test_db import IMAGES, LIVE_UNTIL, docker, ensure_image, migrations, psql, wait_ready

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / ".dev"
STATE = DEV / "stack.json"
API_ENV = DEV / "api.env"
NETWORK = "pulse-dev"
DB, AUTH, GATEWAY = "pulse-dev-db", "pulse-dev-auth", "pulse-dev-gateway"
DB_PORT, GATEWAY_PORT = 55442, 55451
AUTH_IMAGE = "public.ecr.aws/supabase/gotrue:v2.197.0"
GATEWAY_IMAGE = "public.ecr.aws/supabase/kong:2.8.1"
SUPABASE_URL = f"http://127.0.0.1:{GATEWAY_PORT}"
DEMO_NUMBER = "+213 000 00 00 00"  # not a reachable number: the local demo must never call anyone
CONTAINERS = (GATEWAY, AUTH, DB)


def _b64(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


def es256_jwk() -> dict:
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig", "key_ops": ["sign", "verify"],
            "kid": str(uuid.uuid4()), "x": _b64(pub.x), "y": _b64(pub.y), "d": _b64(key.private_numbers().private_value)}


def gateway_config() -> str:
    # Same path layout as Supabase: /auth/v1/* -> Auth. Nothing else is exposed.
    return json.dumps({"_format_version": "2.1", "services": [{
        "name": "auth-v1", "url": f"http://{AUTH}:9999/",
        "routes": [{"name": "auth-v1", "strip_path": True, "paths": ["/auth/v1/"]}]}]})


def run(*args: str) -> None:
    r = docker(*args, check=False)
    if r.returncode != 0:
        sys.exit(f"docker {args[0]} failed: {r.stderr.decode(errors='replace').strip()[:600]}")


def wait_http(url: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)
    sys.exit(f"{url} did not answer in time; see `docker logs {AUTH}` and `docker logs {GATEWAY}`")


def exists(name: str) -> bool:
    return docker("container", "inspect", name, check=False).returncode == 0


def up() -> None:
    if any(exists(c) for c in CONTAINERS):
        sys.exit("The dev stack already exists. Use `start`, or `down` first to rebuild it from scratch.")
    DEV.mkdir(exist_ok=True)
    (DEV / ".gitignore").write_text("*\n", encoding="utf-8")  # belt and braces: nothing here is committed
    password = secrets.token_urlsafe(24)
    jwk = es256_jwk()
    image = ensure_image()
    docker("network", "create", NETWORK, check=False)

    run("run", "-d", "--name", DB, "--network", NETWORK, "-e", f"POSTGRES_PASSWORD={password}",
        "-p", f"127.0.0.1:{DB_PORT}:5432", image)
    print(f"[dev] database {image}")
    wait_ready(DB)
    r = psql(DB, f"alter role supabase_auth_admin with login password '{password}';".encode(), user="supabase_admin")
    if r.returncode != 0:
        sys.exit(f"could not prepare the auth role: {r.stderr.decode(errors='replace')[:400]}")

    run("run", "-d", "--name", AUTH, "--network", NETWORK,
        "-e", "GOTRUE_API_HOST=0.0.0.0", "-e", "PORT=9999", "-e", f"API_EXTERNAL_URL={SUPABASE_URL}",
        "-e", "GOTRUE_DB_DRIVER=postgres", "-e", "GOTRUE_DB_NAMESPACE=auth",
        "-e", f"GOTRUE_DB_DATABASE_URL=postgres://supabase_auth_admin:{password}@{DB}:5432/postgres",
        "-e", "GOTRUE_SITE_URL=http://127.0.0.1:5173", "-e", "GOTRUE_URI_ALLOW_LIST=http://127.0.0.1:5173",
        "-e", f"GOTRUE_JWT_SECRET={secrets.token_urlsafe(48)}", "-e", f"GOTRUE_JWT_KEYS={json.dumps([jwk])}",
        "-e", f"GOTRUE_JWT_ISSUER={SUPABASE_URL}/auth/v1", "-e", "GOTRUE_JWT_AUD=authenticated",
        "-e", "GOTRUE_JWT_EXP=3600", "-e", "GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated",
        "-e", "GOTRUE_JWT_ADMIN_ROLES=service_role",
        "-e", "GOTRUE_EXTERNAL_EMAIL_ENABLED=true", "-e", "GOTRUE_MAILER_AUTOCONFIRM=true",
        "-e", "GOTRUE_DISABLE_SIGNUP=false",  # local only; accounts are created by dev_seed.py
        AUTH_IMAGE)
    run("run", "-d", "--name", GATEWAY, "--network", NETWORK, "-p", f"127.0.0.1:{GATEWAY_PORT}:8000",
        "-e", "KONG_DATABASE=off", "-e", f"KONG_DECLARATIVE_CONFIG_STRING={gateway_config()}",
        "-e", "KONG_DNS_ORDER=LAST,A,CNAME", "-e", "KONG_PROXY_ACCESS_LOG=/dev/stdout",
        GATEWAY_IMAGE)
    wait_http(f"{SUPABASE_URL}/auth/v1/health")
    print("[dev] auth ready (ES256), gateway on", SUPABASE_URL)

    # After Auth's own migrations: the live project's auth helpers, then the verified PULSE migrations.
    compat = Path(__file__).with_name("test_db_auth_live.sql")
    for name, sql, user in [(compat.name, compat.read_bytes(), "supabase_admin")] + \
                           [(f.name, f.read_bytes(), "postgres") for f in migrations(LIVE_UNTIL)]:
        r = psql(DB, sql, user=user)
        if r.returncode != 0:
            sys.exit(f"{name} failed:\n{r.stderr.decode(errors='replace')[:800]}")
        print(f"[dev] applied {name}")

    STATE.write_text(json.dumps({"db_password": password, "live_until": LIVE_UNTIL}), encoding="utf-8")
    API_ENV.write_text("\n".join([
        "# Generated by scripts/dev_stack.py for the LOCAL dev stack only. Never commit, never reuse elsewhere.",
        "PULSE_ENV=dev",
        f"PULSE_DATABASE_URL=postgresql+psycopg://postgres:{password}@127.0.0.1:{DB_PORT}/postgres",
        f"SUPABASE_URL={SUPABASE_URL}",
        "SUPABASE_ANON_KEY=local-dev-gateway-needs-no-key",
        "PULSE_DEMO_MODE=true",
        f"PULSE_DEMO_NUMBER={DEMO_NUMBER}",
        ""]), encoding="utf-8")
    print(f"[dev] wrote {API_ENV.relative_to(ROOT)} (git-ignored). Migrations up to {LIVE_UNTIL}.")
    print("[dev] next: python scripts/dev_seed.py  (demo accounts), then start the API and the frontend")


def start() -> None:
    for name in (DB, AUTH, GATEWAY):
        run("start", name)
    wait_http(f"{SUPABASE_URL}/auth/v1/health")
    print("[dev] started")


def stop() -> None:
    for name in CONTAINERS:
        docker("stop", name, check=False)
    print("[dev] stopped (data kept)")


def status() -> None:
    for name in CONTAINERS:
        r = docker("inspect", "-f", "{{.State.Status}}", name, check=False)
        print(f"{name}: {r.stdout.decode().strip() if r.returncode == 0 else 'absent'}")


def down() -> None:
    if input("Remove the LOCAL dev stack and all its data? Type 'yes': ").strip() != "yes":
        sys.exit("cancelled")
    for name in CONTAINERS:
        docker("rm", "-f", name, check=False)
    docker("network", "rm", NETWORK, check=False)
    for f in (STATE, API_ENV, DEV / "demo-credentials.txt"):
        f.unlink(missing_ok=True)
    print("[dev] removed")


if __name__ == "__main__":
    commands = {"up": up, "start": start, "stop": stop, "status": status, "down": down}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in commands:
        sys.exit(__doc__)
    commands[cmd]()
