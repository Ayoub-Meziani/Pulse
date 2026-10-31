"""Compare two `pg_dump --schema-only` files statement by statement.

Used by docs/engineering/PULSE_DATABASE_SYNC_POLICY.md to check that the migrations on branch `AI`
produce exactly the live Supabase schema. Formatting differences between the
Supabase CLI dump and plain pg_dump (comments, quoting, ownership, IF NOT EXISTS,
CREATE OR REPLACE, platform default privileges of supabase_admin) are ignored.

Usage: python scripts/compare_schemas.py live_schema.sql migrations_schema.sql
Exit code 0 = identical, 1 = differences (printed).
"""
from __future__ import annotations

import re
import sys

IGNORED_PREFIXES = ("SET ", "SELECT pg_catalog", "ALTER SCHEMA", "COMMENT ON SCHEMA public",
                    "CREATE SCHEMA", "RESET ")


def statements(path: str) -> set[str]:
    lines = [line for line in open(path, encoding="utf-8").read().splitlines()
             if not line.startswith("--") and not line.startswith("\\")]
    out = set()
    for stmt in re.split(r";\s*\n", "\n".join(lines)):
        s = re.sub(r"\s+", " ", stmt.replace('"', "")).strip()
        if not s or s.startswith(IGNORED_PREFIXES) or " OWNER TO " in s or "FOR ROLE supabase_admin" in s:
            continue
        s = re.sub(r"^CREATE OR REPLACE ", "CREATE ", s).replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")
        out.add(s)
    return out


def main() -> int:
    live, migrated = statements(sys.argv[1]), statements(sys.argv[2])
    print(f"live {len(live)} statements, migrations {len(migrated)}, identical {len(live & migrated)}")
    for title, diff in (("ONLY IN LIVE", live - migrated), ("ONLY IN MIGRATIONS", migrated - live)):
        print(f"== {title}: {len(diff)}")
        for s in sorted(diff):
            print("  ", s[:400])
    return 0 if live == migrated else 1


if __name__ == "__main__":
    sys.exit(main())
