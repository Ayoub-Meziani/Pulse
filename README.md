# PULSE

Hypertension monitoring, early warning and emergency support. **Hackathon prototype, not a medical device.**

Patients record blood-pressure readings; PULSE explains each reading against a target, flags trends,
and switches to an emergency flow when a reading is dangerously high or a red-flag symptom is reported.
The patient's own doctor reviews alerts and incidents later in a doctor dashboard.

## Status

| Part | State |
|---|---|
| Backend API (`api/`) | Contract v1: all routes and schemas defined (`contract/openapi.json`); alert rules tested; `GET /config/emergency` works; other routes return 501 until the Supabase integration |
| Database | Supabase project `pulse`; schema = `supabase/migrations/` (branch `AI`) |
| Frontend (`frontend/`, branch `feature/frontend`) | Screens with demo data; API integration pending |
| ML pipeline | Not started |
| Device integration | None; demo readings are labelled `simulated` |

See `PULSE_BACKEND_ARCHITECTURE.md`, `PULSE_INTEGRATION_CONTRACTS.md` and `CLAUDE.md`.

## Run the backend

```bash
cd api
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000/api/v1/docs. Run tests with `pytest` (from `api/`).

## Docs

- `docs/conception.pdf` — full conception
- `docs/API_CONTRACT.md` and `contract/openapi.json` — API contract
- `docs/SAFETY_AND_LIMITATIONS.md` — alert rules and what PULSE does not do
- `docs/decisions.md` — decisions log
