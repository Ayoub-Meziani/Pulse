"""Write the API contract to contract/openapi.json (run from api/: python -m app.export_openapi).

CI regenerates this file and fails if it differs from the committed one, so a
contract change is always visible in the pull request.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .main import create_app

OUT = Path(__file__).resolve().parents[2] / "contract" / "openapi.json"


def main() -> None:
    app = create_app(Settings(env="dev", database_url="sqlite://", jwt_secret="x" * 32, jwt_minutes=1))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
