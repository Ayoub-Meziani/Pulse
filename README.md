# PULSE

Hypertension monitoring, early warning and emergency support. **Hackathon prototype, not a medical device.**

Patients record blood-pressure readings; PULSE explains each reading against a target, flags trends,
and switches to an emergency flow when a reading is dangerously high or a red-flag symptom is reported.
The patient's own doctor reviews alerts and incidents later in a doctor dashboard.

## Status

| Part | State |
|---|---|
| Backend API (`api/`) | FastAPI on Supabase Postgres + Auth: readings, symptoms, alerts, summaries, profile, care plan, contacts, emergency card and events, doctor notes, devices and wearable samples, stored predictions (doctor only). Still 501: `/daily`, `/journal`. Contract: `contract/openapi.json` |
| Database | Supabase; schema = `supabase/migrations/` (M1–M8 verified live). Local development uses a local stack, never the shared project |
| Frontend (`frontend/`) | React + Vite on the real API: patient (dashboard, reading and symptom flow, emergency screen, history, alerts, profile), doctor (assigned patients and their record), minimal admin |
| ML | Stored experimental estimates are shown to doctors only and never used by alerts; no model runs in the API |
| Devices | Optional; wearable data is advisory and never triggers an alert. Simulated data is always labelled |

Not deployed. See `docs/LOCAL_DEVELOPMENT.md` to run everything locally with fictional demo accounts.

## Run locally

```bash
python scripts/dev_stack.py up      # local Supabase Postgres + Auth (once)
python scripts/dev_seed.py          # fictional demo accounts (once); passwords in .dev/demo-credentials.txt
python scripts/dev_api.py           # API  http://127.0.0.1:8000/api/v1/docs
cd frontend && npm ci && npm run dev  # app  http://localhost:5173
```

Details, prerequisites and tests: `docs/LOCAL_DEVELOPMENT.md`.

## Docs

- `docs/conception.pdf` — full conception
- `docs/API_CONTRACT.md` and `contract/openapi.json` — API contract
- `docs/SAFETY_AND_LIMITATIONS.md` — alert rules and what PULSE does not do
- `docs/decisions.md` — decisions log
- `docs/LOCAL_DEVELOPMENT.md` — run the app locally
- `docs/incidents/` — incident records
