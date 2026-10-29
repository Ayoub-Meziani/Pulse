# Implementation plan

Last updated: 2026-10-29 by the backend workstream. Full design: `docs/conception.pdf`.

## Current state

| Area | Status |
|---|---|
| Repo | Created; first slice on branch `feat/api-measurement-slice` (not merged). |
| Backend slice | **Implemented and tested:** login, measurements (validate → store → rules → alerts), symptom reports (emergency rule), alerts list + detail with audit events, doctor patient list sorted by urgency, summary stats, permissions, demo seed, OpenAPI export. |
| Analysis | **Implemented and tested:** validation V1–V4, rules R-EMG-1, R-SEV-1/2/3, R-TGT-1, R-TRD-1, summary + trend direction. Test vectors T1–T16 covered. |
| ML pipeline | **Not started.** Waiting for the data/AI brief and a dataset decision (see below). |
| Frontend | **Not started.** `web/` to be created by the frontend developer. |
| Device integration | **None.** Provenance fields exist; readings are `manual` or `simulated`. |
| CI | Workflow added on this branch (pytest + contract check). Branch protection on `main` not enabled yet. |

## Owners and next tasks

### Ayoub — backend + integration (merge lead)
1. Review and merge `feat/api-measurement-slice`; enable branch protection on `main` (require PR + CI).
2. Alert transitions `POST /alerts/{id}/transition` with the state machine (conception section 6).
3. Incidents: `POST /patients/{id}/incidents`, `POST /incidents/{id}/actions` (idempotent batch), `PATCH`, `GET` report.
4. `GET /config/emergency` (numbers from config, `verified` flag, demo mode) and `GET /patients/{id}/emergency-card`.
5. Profile + trusted contacts, journal, doctor notes, care-plan PUT.
6. Serve the built frontend from FastAPI; deploy over HTTPS.

### Frontend developer
1. Create `web/` (React + Vite + TS per D1, or propose otherwise before starting).
2. Generate TS types from `contract/openapi.json`; build login, Add reading (with symptom check and
   recheck timer, see `docs/API_CONTRACT.md` "Frontend flow"), history chart, alerts, doctor patient list.
3. Emergency screen working offline from cached config/card (needs task 4 above for live data).

### Data / AI developer
1. Read `api/app/analysis/` and its tests; own changes there.
2. Add French/Arabic alert strings in `analysis/texts.py` (same keys).
3. ML pipeline (mandatory): choose a defensible target and dataset **after checking availability and
   licence**; baseline + candidate model, leakage-safe split, metrics, saved artefact, inference function
   in its own module (e.g. `ml/` or `api/app/ml/`, agree with Ayoub). Output for doctor view only,
   never input to safety rules. Document in `docs/ML_PIPELINE.md`.
4. Simulator scenarios for the demo (rising, crisis) reusing `app.seed` patterns.

## Dependencies and blockers

- **Data/AI brief not received yet** → ML target, dataset and `docs/ML_PIPELINE.md` blocked.
- **Emergency number confirmation (D3)** → needed before the demo, not before coding.
- **Teammates' GitHub usernames** → needed for `CODEOWNERS` and branch-protection reviewers.
- **Hardware** → none identified; device adapter work blocked until a real device and its documented
  output are known.
- Frontend live emergency data depends on backend tasks 3–4.
