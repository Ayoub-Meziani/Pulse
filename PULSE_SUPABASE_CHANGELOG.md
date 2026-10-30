# Supabase project change log — `pulse` (org `lwiza`, ref `nfmfdhpxipdndggxtqho`)

Every direct action on the shared cloud project is recorded here: what, why, objects affected, result, verification, and whether the data/AI developer must update their migrations or code.
Rule: schema changes go through `supabase/migrations/` files and `supabase db push`, never through dashboard edits, so the repository and the cloud never diverge.

| # | Date (UTC) | Who | Action | Why | Objects affected | Result | Verification | Data/AI dev must update? |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-30 ~01:40–03:30 | Claude Code (Ayoub's CLI login) | **Read-only inspection**: `supabase link` (scratch folder outside the repo), `gen types --linked`, `migration list --linked`, `inspect db table-stats/vacuum-stats --linked`, `db dump --linked -s public,private` and `-s auth` (schema only, no data), `GET /auth/v1/settings` and JWKS with the publishable key | Verify the real database against the data/AI documentation (architecture §12) | None. Side effect: the CLI creates/refreshes the temporary login role `cli_login_postgres` used for linked commands (standard CLI behaviour) | Success (one dump attempt failed on Docker image download, retried) | Outputs kept locally in Claude's scratchpad (`supa/schema.sql`, `supa/auth_schema.sql`, `supa/types_public.ts`); not committed | No |

## Changes deliberately **not** made (need Ayoub or the data/AI developer)

| Change | Why not applied directly | Owner |
|---|---|---|
| Disable public sign-up | Requires dashboard (session expired; I do not sign in on Ayoub's behalf) or Management API token; `supabase config push` would overwrite the full remote auth config from a local file that does not exist | Ayoub (blockers B16) |
| Migration M3 (`backend_alignment`) | Architecture not yet approved; migration must be a file in `supabase/migrations/` alongside the two existing files, which are not in the repository yet. Pushing from here would create a migration history the data/AI developer does not have | Data/AI developer after approval (contracts §3.1) |
| Seed data | Sign-up still enabled; seed generator still uses a hard-coded password (REPORTED) | Data/AI developer after B9 and B16 |
