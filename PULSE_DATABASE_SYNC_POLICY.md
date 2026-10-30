# PULSE database synchronization policy (permanent)

Applies to every person and every Claude Code session working on PULSE. Established by Ayoub (integration lead), 2026-10-30.

The data/AI developer keeps changing branch `AI` and may add migrations at any time. **A previous verification is never assumed current.** The shared database is the Supabase project `pulse` (org `lwiza`, ref `nfmfdhpxipdndggxtqho`).

## 1. Before every database-dependent task

"Database-dependent" = anything that reads or writes tables, maps models, changes endpoints backed by the database, changes API fields that mirror columns, or touches ML inputs/outputs.

| Step | What | How (verified commands) |
|---|---|---|
| 1 | Fetch all branches | `git fetch --all --prune` |
| 2 | Inspect latest `AI` and new migrations | `git log --oneline <last-verified-AI-commit>..origin/AI`; `git ls-tree --name-only origin/AI supabase/migrations/`; `git diff <last-verified-AI-commit> origin/AI -- supabase/ pulse_data/ docs/data/` |
| 3 | Remote migration history | From a scratch folder **outside the repo**: `supabase link --project-ref nfmfdhpxipdndggxtqho`, then `supabase migration list --linked` |
| 4 | Migrations vs actual remote schema | (a) `supabase db dump --linked -s public,private -f live.sql` (schema only; it pulls the Postgres image that matches the remote). (b) Throwaway container of that same image: `docker run -d --name pulse-verify -e POSTGRES_PASSWORD=<throwaway> <image>`; apply every file of `origin/AI:supabase/migrations/` in order with `psql -v ON_ERROR_STOP=1` (Git Bash: `export MSYS_NO_PATHCONV=1`); `pg_dump --schema-only --no-owner --schema=public --schema=private > migrations.sql`. (c) `python scripts/compare_schemas.py live.sql migrations.sql` must report 0 differences. (d) `docker rm -f pulse-verify`. |
| 5 | Verify the objects the task touches | In the dumps: tables, columns and types, CHECK constraints, FKs, indexes, functions, triggers (`-s auth` dump for `on_auth_user_created`), RLS policies, grants (incl. default privileges) |
| 6 | Impact analysis | Backend models/mappings (`PULSE_DB_INTEGRATION_PLAN.md` §1), API schemas (`api/app/schemas.py`), frontend contract (`contract/openapi.json`), ML (`ml_predictions`, features) |
| 7 | Update documents | `PULSE_DB_INTEGRATION_PLAN.md`, `PULSE_INTEGRATION_CONTRACTS.md`, `PULSE_BACKEND_ARCHITECTURE.md` §12, `PULSE_BLOCKERS_AND_REQUIREMENTS.md`; record the verification in `PULSE_SUPABASE_CHANGELOG.md` |
| 8 | Report discrepancies **before** proceeding | Any difference between `AI` migrations, remote history, remote schema and our documents is reported to Ayoub; work that depends on the differing objects waits |

Shortcut allowed only when step 2 shows no new commit on `origin/AI` **and** step 3 shows the same remote history as the last recorded verification: then steps 4–5 may be limited to the objects the task touches. When in doubt, run the full check.

## 2. After a migration is applied to `pulse`

1. Confirm the push succeeded (`supabase db push` output, no error).
2. `supabase migration list --linked`: the new version is present remotely and matches the file name on the branch it came from.
3. Dump the live schema and compare with the migrations (step 4 above): 0 differences.
4. Inspect the new or changed objects (step 5), including RLS enabled on new tables and **no grants to `anon`** (the live default privileges grant ALL on new `public` objects unless the migration revokes them).
5. Record it in `PULSE_SUPABASE_CHANGELOG.md`: what, why, objects, result, verification, and whether others must update.

## 3. Ownership and safety

| Rule | |
|---|---|
| Migration authorship | The **data/AI developer** writes and documents migrations (`supabase/migrations/`, `docs/data/`), with tests. Backend needs are requested through them. |
| Approval | **Ayoub** approves any change to the shared architecture and every migration before it reaches `pulse`. |
| Applying | Only after approval, by the person named in the approval, with `supabase db push`. **Never silently apply migrations from `AI`.** |
| History | Never recreate, rewrite or reorder migration history; never edit an applied migration; never reconstruct migrations from a dump; never treat an old dump as current. |
| Destructive changes | `DROP`, `TRUNCATE`, `DELETE` of data, column type narrowing, `db reset` on a linked/remote project, removing RLS or policies, or anything hard to reverse: **stop, describe the risk, get Ayoub's explicit approval first.** |
| Read-only verification | Always allowed (link, migration list, inspect, schema-only dump, public auth settings). |
| Direct non-destructive changes | Allowed when necessary, but each one is recorded in `PULSE_SUPABASE_CHANGELOG.md` and reported to Ayoub, who keeps the data/AI developer synchronized. Prefer a migration file over any direct change so the repository stays the single history. |
| Seed data | Fictional only; never `supabase/seed.sql` with a known password on a shared project; demo password from `PULSE_DEMO_PASSWORD`. |
| Credentials | Never read secrets from credential stores, never sign in to dashboards on someone's behalf, never commit keys. The API holds no service-role key. |

## 3b. Backend test database

`python scripts/test_db.py up` recreates the throwaway test database: same image as the live project, then
`scripts/test_db_auth_live.sql` (the live project's `auth.uid()`, `auth.role()`, `auth.email()`, `auth.jwt()`,
because the plain image ships older helpers), then every file of `supabase/migrations/` in order. During each
sync (step 5), compare these four functions with the live `-s auth` dump and update the file if they differ.
The test database contains every migration on the branch, including ones not yet applied to `pulse`
(e.g. M5 until it is pushed); say so when reporting test results.

## 4. Known practical issues (Ayoub's Windows machine)

- Supabase CLI 2.54.11 `db start` fails (container closes connections); use the throwaway-container method above or `npx supabase@2.122.0`.
- The first `db dump --linked` downloads a large Postgres image; slow network: retry.
- The direct database host has no IPv4 route; use the session pooler (`aws-1-eu-west-3.pooler.supabase.com:5432`).

## 5. Last full verification (update on every run)

| Date (UTC) | `origin/AI` | Remote migration history | Live vs migrations | By |
|---|---|---|---|---|
| 2026-10-30 | `a004329` | `20261029120000`, `20261029120100` | 273/273 statements identical (`public`, `private`); auth trigger present | Claude Code (read-only) |
| 2026-10-30 (later) | `fcad8a2` | M1–M4: `…120000`, `…120100`, `20261030120000` (M3), `20261030120100` (M4); **M5 `20261030130000` not applied** (awaiting review) | M1–M4 → 292/292 identical; M5 applies cleanly on top in a throwaway container | Claude Code (read-only) |
