"""Start the API against the LOCAL dev stack: loads .dev/api.env (written by dev_stack.py) and runs uvicorn.

    python scripts/dev_api.py            # http://127.0.0.1:8000/api/v1/docs
    python scripts/dev_api.py --port 8001
    python scripts/dev_api.py --worker     # the escalation worker, same environment (PULSE_ESCALATION_ENABLED)

It never migrates, seeds or resets anything, and refuses an env file that does not point at 127.0.0.1.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".dev" / "api.env"

if __name__ == "__main__":
    if not ENV.exists():
        sys.exit("No .dev/api.env: run `python scripts/dev_stack.py up` first.")
    env = dict(line.split("=", 1) for line in ENV.read_text(encoding="utf-8").splitlines()
               if line and not line.startswith("#"))
    if "127.0.0.1" not in env.get("PULSE_DATABASE_URL", ""):
        sys.exit("Refusing to start: .dev/api.env does not point at the local dev database.")
    if "--worker" in sys.argv:
        print("[dev] escalation worker (local dev stack)")
        sys.exit(subprocess.call([sys.executable, "-m", "app.escalation_worker"], cwd=ROOT / "api",
                                 env={**os.environ, **env}))
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else "8000"
    print(f"[dev] API on http://127.0.0.1:{port}/api/v1/docs (local dev stack)")
    sys.exit(subprocess.call([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
                              "--host", "127.0.0.1", "--port", port], cwd=ROOT / "api", env={**os.environ, **env}))
