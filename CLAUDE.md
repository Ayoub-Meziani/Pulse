# PULSE — working instructions for every Claude Code session

PULSE is a hypertension monitoring and emergency-support **prototype** built in a 36-hour hackathon by a
3-person team. It is not a medical device. GitHub (`Ayoub-Meziani/pulse`) is the source of truth.

## Before any task

1. Read this file, `docs/engineering/IMPLEMENTATION_PLAN.md`, `docs/decisions.md`, and the docs for the area you touch
   (`docs/API_CONTRACT.md`, `docs/SAFETY_AND_LIMITATIONS.md`, `docs/conception.pdf`).
2. Inspect the actual code before assuming file names, routes, models or commands.
3. Keep the existing stack and working code unless there is evidence a change is needed.
4. **If the task depends on the database, follow `docs/engineering/PULSE_DATABASE_SYNC_POLICY.md` first** (see below).

## Database synchronization (mandatory, permanent)

The shared database is Supabase project `pulse` (ref `nfmfdhpxipdndggxtqho`); its schema comes only from
`supabase/migrations/` on branch `AI` (owned by the data/AI developer). Previous verifications are never current.
Before any database-dependent task: fetch all branches, inspect new `AI` commits and migrations, check the remote
migration history, compare the migrations with the live schema (`scripts/compare_schemas.py`), verify the objects
the task touches, assess impact on models / API / frontend / ML, update the docs and `docs/engineering/PULSE_SUPABASE_CHANGELOG.md`,
and **report discrepancies before proceeding**. After any migration is applied: verify history, live schema and
grants, and record it. Never silently apply `AI` migrations, never recreate or rewrite migration history, never
reconstruct migrations from a dump, and never make a destructive database change without Ayoub's explicit approval.
Read-only verification is always allowed; any direct non-destructive change must be logged and reported to Ayoub.
Full procedure and commands: `docs/engineering/PULSE_DATABASE_SYNC_POLICY.md`.

## Ownership (stay inside your area)

| Area | Owner | Paths |
|---|---|---|
| Backend + integration (merge lead) | Ayoub | `api/app/` except `analysis/`, `contract/`, `docs/`, `.github/`, this file |
| Data / analytics / ML | Data/AI developer | `api/app/analysis/`, future `ml/`, their tests |
| Frontend | Frontend developer | `frontend/` (React + Vite; the single frontend app) |

Editing outside your area needs coordination with Ayoub first.

## Git rules

- Work on a feature branch (`feat/<area>-<topic>`, `fix/...`). Never commit or push to `main`.
- Never merge, deploy, force-push, reset, or delete branches without Ayoub's explicit approval.
- Do not overwrite teammates' work. Pull/rebase on `main` before opening a PR.
- Before committing: review `git diff`, check for secrets and unrelated changes. Small, reviewable PRs.

## Contracts (integration rules)

- **The API contract is `api/app/schemas.py`**, exported to `contract/openapi.json`.
  **Persisted models are `api/app/models.py`.** These are shared contracts.
- Do not change them in a way that breaks another workstream. Propose the change in the PR
  description (or `docs/decisions.md`), coordinate with Ayoub, then regenerate the contract:
  `python -m app.export_openapi` (CI fails if `contract/openapi.json` is stale).
- The frontend uses the OpenAPI contract; it must not invent fields or keep separate mock datasets
  once the real API is running. All views read the same persisted data.
- The backend calls `app.analysis` functions; it never re-implements validation or alert rules.

## Safety and honesty rules (non-negotiable)

- Never claim a call, SMS, share, device connection, sensor reading, notification, or external
  integration succeeded unless it was implemented and verified. Log "call button tapped", never "call made".
- Label data accurately: `manual`, `device`, `imported`, `simulated`. Never present synthetic data as real.
- Deterministic safety rules (`app/analysis/rules.py`) stay independent of any ML model. A forecast is
  never a measurement, diagnosis, emergency decision, or guarantee of safety, and must never delay
  urgent guidance. The emergency screen and incident record must work when ML is unavailable.
- No diagnoses, no prescriptions, no advice to start/stop/change medication, no implied clinical validation.
  Patient-facing wording lives in `app/analysis/texts.py` for clinician review.
- Never commit `.env` files, credentials, tokens or real patient data. Demo data is fictional.
- Never run destructive commands against a shared database. Destructive local commands only on the local dev stack
  (`scripts/dev_stack.py`) or the throwaway test databases (`scripts/test_db.py`).
- Never dial or test real emergency numbers.

## Working style

- Write or update tests for meaningful changes and report real results.
  In reports, separate: implemented and tested / implemented, untested / mocked or simulated / blocked.
- Prefer small vertical slices that run end to end over large untested code.
- Optimise for a working, honest demo.

## Commands (verified)

All backend commands run from `api/`.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:create_app --factory --reload    # http://127.0.0.1:8000/api/v1/docs
pytest                              # rules + contract tests
python -m app.export_openapi        # regenerate contract/openapi.json after schema changes
```

Local full stack (Supabase Postgres + Auth on 127.0.0.1, fictional demo accounts): see
`docs/LOCAL_DEVELOPMENT.md` (`scripts/dev_stack.py`, `scripts/dev_seed.py`, `scripts/dev_api.py`).
Frontend (from `frontend/`): `npm ci`, `npm run dev`, `npm run lint`, `npm test`, `npm run build`.
Backend tests need the throwaway databases: `python scripts/test_db.py up live|latest` (see the same doc).
Still 501: `/patients/{id}/daily`.

Settings via environment variables: `PULSE_ENV` (default `dev`), `PULSE_DEMO_MODE` (default on),
`PULSE_DEMO_NUMBER` (required outside dev when demo mode is on), `PULSE_EMERGENCY_NUMBERS` (JSON),
`PULSE_PRIMARY_NUMBER_ID`, `PULSE_ML_MODEL_VERSION` (default `mbp-v1`), `PULSE_DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_ANON_KEY`.

Not set up yet (do not invent commands for them): type checking, a deployment, ML training in this repo's CI.