# Staging project `pulse-staging`: setup procedure (prepared, not executed)

Status: **nothing has been created and no cost has been incurred.** This document was prepared on 2026-10-31
from Ayoub's Q7 decision. Every step marked **[AUTH]** needs Ayoub's explicit go-ahead at that moment.

## 1. Decided configuration (Ayoub, Q7)

| Setting | Value |
|---|---|
| Organization | `lwiza` (the same organization as production `pulse`, ref `nfmfdhpxipdndggxtqho`) |
| Project name | `pulse-staging` |
| Region | `eu-west-3` (Paris), the same as production |
| Credentials | Separate from production: its own database password, publishable key and JWT signing key. Never shared with production or stored in the repository |
| Auth | Public sign-up **disabled**; **ES256** JWT signing key (the API rejects HS256); email confirmation off for provisioned accounts |
| Data | Fictional only, created through Auth and the API (the same scenarios as `scripts/dev_seed.py`) |
| Schema | Mirror of production, **M1–M9** (`20261029120000` … `20261030170000`) |

## 2. Cost (Supabase pricing and billing pages, checked 2026-10-30; confirm on the day)

| Option | What it costs | Constraint |
|---|---|---|
| Free | $0 | **Two active free projects per user**, counted across every organization where that user is Owner or Administrator. Ayoub already has two active projects (`qabas` and `pulse`), so a free `pulse-staging` created by him requires pausing one of them. A free project pauses after 1 week of inactivity, and has a 500 MB database |
| Pro (organization `lwiza`) | $25/month per organization, which includes $10 of compute credit. Each extra project adds about $10/month (Micro compute, billed hourly) | The credit covers one Micro project. If production already uses it, staging adds about $10/month. Pro projects do not pause. The spend cap is on by default |

**To check before choosing (dashboard, Ayoub):** `lwiza` → Billing (current plan, spend cap) and Team (who is
Owner or Administrator). I could not read either from the CLI.

Sources: <https://supabase.com/pricing>, <https://supabase.com/docs/guides/platform/billing-faq>,
<https://supabase.com/docs/guides/platform/billing-on-supabase>.

## 3. Permissions

- On the Free and Pro plans, an organization member's role applies to **every** project in the organization.
  Everyone in `lwiza` would see both `pulse` and `pulse-staging`. Per-project roles belong to a higher tier
  (to confirm on the plan page).
- Isolation therefore rests on four things: separate credentials and keys, no shared `.env`, a dedicated CLI folder
  per project, and a small number of Owner/Administrator accounts.
- **Recommendation (needs Ayoub's approval; no role is changed here):**
  - keep Ayoub as the only Owner of `lwiza`;
  - make the other members Developer or Read-only;
  - only Owner/Administrator accounts can run `db push`, change Auth settings or create projects.

## 4. Secrets and environment variables

Keep secrets in a password manager and in the host's environment. Locally, use the git-ignored file
`.dev/staging.env`. `.dev/` and `*.env` are ignored.

| Variable | Staging value |
|---|---|
| `PULSE_ENV` | `staging` |
| `PULSE_DATABASE_URL` | Session pooler URI of `pulse-staging` (`aws-1-eu-west-3.pooler.supabase.com:5432`; the password is set at creation) |
| `SUPABASE_URL` | `https://<staging ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Staging publishable key (used only by the login proxy) |
| `PULSE_DEMO_MODE` / `PULSE_DEMO_NUMBER` | `true` / a team phone number (never an emergency number) |
| `PULSE_ML_MODEL_VERSION` | Unset (`mbp-v1`, so estimates are unavailable) |
| Never set | The service-role key in the API, or any production value |

## 5. Procedure

1. **[AUTH] Create the project.** Ayoub creates it in the dashboard (`lwiza` → New project → `pulse-staging`,
   eu-west-3, generated password stored in the password manager), or explicitly authorizes Claude Code to run
   `supabase projects create` with the plan he has chosen. Record the ref in `.dev/staging-ref` (git-ignored).
2. **Positive target check** (read-only), repeated before every write step:
   - `supabase projects list` shows the name `pulse-staging` in organization `lwiza`;
   - the ref ≠ `nfmfdhpxipdndggxtqho`.
   If either check fails, stop.
3. **Auth settings** (dashboard):
   - disable sign-up;
   - enable an ES256 signing key (Authentication → JWT signing keys);
   - set the site URL to the staging frontend URL.
   Verify with `GET /auth/v1/settings` (`disable_signup: true`) and JWKS (`alg: ES256`).
4. **[AUTH] Migrations.**
   1. Work in a scratch folder **outside the repository** that holds a copy of `supabase/config.toml` and the
      nine files M1–M9 from `main`, byte-identical (git blobs; M9 = `687c42f`).
   2. Link and check: `supabase link --project-ref <staging ref>`, then `supabase migration list --linked`.
      The list must be empty.
   3. Dry run: `supabase db push --linked --dry-run`. Review the output.
   4. Apply: `supabase db push --linked`.
5. **Verification** (read-only):
   - `migration list --linked` shows exactly M1–M9;
   - a schema-only dump compared with `scripts/compare_schemas.py` against the `live` test DB (which is M1–M9
     since 2026-10-31) shows 0 differences;
   - RLS is enabled on every table, there are no `anon` grants, and the auth trigger is present.
   Record the result in `PULSE_SUPABASE_CHANGELOG.md` and in sync policy §5.
6. **[AUTH] Accounts.**
   - Create Patient A, Patient B and the doctor with the Auth admin API (from Ayoub's machine) or in the dashboard.
     Store the generated passwords in the password manager.
   - Set roles and the doctor assignment in SQL.
   - Load the fictional data through the staging API. A guarded staging variant of `dev_seed.py`, which refuses
     to run unless the ref check passes, is the next tooling task.
7. **Run the API and frontend against staging.** For phase D they can run locally with `.dev/staging.env`; a
   public host with HTTPS is a separate decision. Then run the acceptance script and the browser scenarios in
   `docs/PULSE_V1_STAGING_HANDOFF.md` §9, and record the results.

## 6. Rollback and teardown

- Before any real use, a mistake is fixed by deleting the project and starting again. **[AUTH]** Deleting a project
  is irreversible, so only Ayoub does it.
- After it is in use, follow the same rules as production: forward migrations only, and never rewrite the
  migration history.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The CLI links one project per folder, so a wrong folder targets production | Dedicated scratch folder; ref check before each write; never link from the repository folder |
| Access is organization-wide | Few Owner/Administrator accounts; separate credentials |
| A free project pauses after inactivity | Pro, or unpause before each test session |
| Staging drifts from production | Same M1–M9 files; schema comparison after each migration; changelog rows |
| Health data in a project hosted outside Algeria | Fictional data only. Real patient data would need an ANPDP authorization for transfer abroad (`docs/ALGERIA_EMERGENCY_FEASIBILITY.md` §6) |
