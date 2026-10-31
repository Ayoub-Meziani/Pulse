# Run PULSE locally

The full application (React frontend → FastAPI → Supabase Postgres + Supabase Auth) runs on one machine,
bound to `127.0.0.1`. Nothing here touches the shared cloud project `pulse`.

```
browser ──► Vite dev server :5173 ──/api──► FastAPI :8000 ──► Postgres :55442 (local, Supabase image)
                                                     └──► Supabase Auth (GoTrue, ES256) via gateway :55451
```

## Prerequisites

- Docker (Docker Desktop on Windows), running.
- Python 3.11+ and Node.js 22+.
- Backend dependencies: `cd api && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"`
  (macOS/Linux: `.venv/bin/pip`). Run the Python commands below with that interpreter.
- Frontend dependencies: `cd frontend && npm ci`.

## First time: create the local stack and the demo accounts

```bash
python scripts/dev_stack.py up     # local Postgres + Auth + gateway; applies the migrations verified live (M1–M8)
python scripts/dev_seed.py         # three FICTIONAL demo accounts and their data (once per stack)
```

`up` writes `.dev/api.env` (generated local secrets); `dev_seed.py` writes `.dev/demo-credentials.txt`.
`.dev/` is git-ignored. The passwords are never printed: open `.dev/demo-credentials.txt` to read them.

| Account | Role | Demo data (all fictional) |
|---|---|---|
| `patient.a@demo.pulse.test` | Patient | 20 manual readings over 10 days (mostly normal, two above the general target), one symptom report, journal entries (food, activity, a question; one read by the doctor), a care plan (target 135/85), a follow-up advice from the doctor, a trusted contact. No wearable. |
| `patient.b@demo.pulse.test` | Patient | 24 **simulated** readings (labelled), then manual readings: a severe reading with a symptom check and a recheck (open severe alert), and a trend alert. One recorded emergency episode (screen opened, contact call tapped, outcome). A journal entry. A **simulated** ring with heart-rate and SpO₂ samples. |
| `medecin@demo.pulse.test` | Doctor | Assigned to Patient A and Patient B only. |

## Every time: start the services

Three terminals (or background processes):

```bash
python scripts/dev_stack.py start          # if the containers were stopped
python scripts/dev_api.py                  # API  http://127.0.0.1:8000  (docs: /api/v1/docs, health: /api/v1/health)
cd frontend && npm run dev                 # app  http://localhost:5173
```

Open **http://localhost:5173** and sign in with a demo account. (Some browsers refuse the dev server's
modules on `http://127.0.0.1:5173`; use `localhost`.)

No command above migrates, resets or seeds anything. Demo mode is on: the emergency button dials a
non-reachable demo number (`+213 000 00 00 00`), never 14 or 1021.

## Stop

- Frontend and API: Ctrl+C in their terminals.
- Stack, keeping its data: `python scripts/dev_stack.py stop`.
- Remove the stack and its data: `python scripts/dev_stack.py down` (asks you to type `yes`), then
  `up` + `dev_seed.py` to start fresh.

## Tests

```bash
python scripts/test_db.py up live      # throwaway test databases (ports 55433 / 55432)
python scripts/test_db.py up latest
cd api
PULSE_TEST_DATABASE_URL=postgresql+psycopg://postgres:pulse-test-only@127.0.0.1:55433/postgres .venv/Scripts/python -m pytest -q
PULSE_TEST_DATABASE_URL=postgresql+psycopg://postgres:pulse-test-only@127.0.0.1:55432/postgres .venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest -q      # without a database: contract and unit tests only
.venv/Scripts/python -m app.export_openapi && git diff --exit-code -- ../contract/openapi.json
cd ../frontend && npm run lint && npm test && npm run build
```

## Notes and limits

- Why not `supabase start`: on the team's Windows machine the CLI's database start fails
  (`PULSE_DATABASE_SYNC_POLICY.md` §4). `dev_stack.py` uses the same official images (Postgres
  17.11.0.003, GoTrue v2.197.0, Kong 2.8.1). Auth signs ES256 tokens like the cloud project, so the API
  verifies them through JWKS exactly as in production.
- The stack applies only the migrations verified on the live project (`LIVE_UNTIL` in `scripts/test_db.py`).
  A migration awaiting review (such as `20261030170000_live_early_warning`, "M9", on branch `AI`) is never applied.
- No ML job runs locally: the doctor's "Estimation" tab shows "Aucune estimation disponible"
  (`model_unavailable`). Experimental estimates are doctor-only and never feed alerts.
- Alert texts (`reason`, `next_step`) are English until the clinician-reviewed French version exists.
- Running the API against the shared cloud project needs its credentials, given out of band; never put them
  in the repository.

## A second, independent local stack (another worktree or session)

```bash
PULSE_DEV_INSTANCE=int PULSE_DEV_MIGRATIONS=all PULSE_DEV_WEB_ORIGIN=http://localhost:5174 python scripts/dev_stack.py up
PULSE_DEV_INSTANCE=int python scripts/dev_seed.py
PULSE_ESCALATION_ENABLED=1 python scripts/dev_api.py --port 8001     # API
PULSE_ESCALATION_ENABLED=1 python scripts/dev_api.py --worker        # escalation worker
PULSE_API_URL=http://127.0.0.1:8001 npx vite --port 5174 --strictPort  # from frontend/
```

`PULSE_DEV_INSTANCE` gives the stack its own containers, network and ports (+100: database 55542, gateway 55551).
`PULSE_DEV_MIGRATIONS=all` also applies migrations that are not live yet (local review only). Each worktree keeps
its own `.dev/`.
