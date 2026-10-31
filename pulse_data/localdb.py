"""Local-only guard: the data tools write to this machine's database, never to a shared one."""
from __future__ import annotations

import os

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def require_local(url: str, hint: str = "") -> None:
    """SystemExit unless every host the connection could reach is this machine. Follows libpq: the URL's host /
    hostaddr, else PGHOST / PGHOSTADDR, else localhost; comma-separated lists; a path is a local socket."""
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(url)
    hosts = (info.get("host") or os.environ.get("PGHOST") or "localhost").split(",")
    hosts += [h for h in (info.get("hostaddr") or os.environ.get("PGHOSTADDR") or "").split(",") if h]
    bad = [h for h in hosts if h.strip().lower() not in LOCAL_HOSTS and not h.strip().startswith("/")]
    if bad:
        raise SystemExit(f"refusing a non-local database ({', '.join(bad)}); {hint or 'local stack only'}")
