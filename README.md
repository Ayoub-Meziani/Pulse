# PULSE

Hypertension monitoring, early warning and emergency support. **Hackathon prototype, not a medical device.**

Patients record blood-pressure readings; PULSE explains each reading against a target, flags trends,
and switches to an emergency flow when a reading is dangerously high or a red-flag symptom is reported.
The patient's own doctor reviews alerts and incidents later in a doctor dashboard.

## Status

| Part | State |
|---|---|
| Backend API (`api/`) | First slice implemented and tested: readings, validation, alert rules, symptoms, alerts, doctor list, summary |
| Frontend (`web/`) | Not started |
| ML pipeline | Not started |
| Device integration | None; demo readings are labelled `simulated` |

See `IMPLEMENTATION_PLAN.md` for owners and next tasks, and `CLAUDE.md` for team rules.

## Run the backend

```bash
cd api
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m app.seed --reset
uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000/api/v1/docs. Run tests with `pytest` (from `api/`).

Demo accounts (fictional, local only), password `demo1234`:
`amina@pulse.demo` (doctor), `karim@pulse.demo`, `nadia@pulse.demo`, `youssef@pulse.demo` (assigned patients),
`samir@pulse.demo` (unassigned patient).

## Docs

- `docs/conception.pdf` — full conception
- `docs/API_CONTRACT.md` and `contract/openapi.json` — API contract
- `docs/SAFETY_AND_LIMITATIONS.md` — alert rules and what PULSE does not do
- `docs/decisions.md` — decisions log
