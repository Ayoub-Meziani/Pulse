# Decisions log

Status: **proposed** = in the code, team can still change it · **open** = waiting for the team ·
**approved** = agreed. Numbering follows `docs/conception.pdf` section 19.

| ID | Decision | Status | Notes |
|---|---|---|---|
| D1 | Backend: Python 3.11+, FastAPI, SQLAlchemy 2, SQLite file. Frontend: React + Vite + TypeScript (recommended, not created yet). | proposed (2026-10-29) | Repo was empty, so no stack to preserve. Python chosen so the data/ML work and the rules share one language. Changing it later costs the backend slice. |
| D2 | Default target 140/90 until a doctor sets a care plan | proposed | Clinician to confirm (135/85 is the usual home-reading alternative). Single constant in `analysis/types.py`. |
| D3 | Emergency number on the main button | open | Confirm 14 or 1021 with a medical mentor before the demo. Never test-call. |
| D4 | Red-flag symptom list = AHA 7 symptoms | proposed | `analysis/texts.py`. |
| D5 | Hosting | open | HTTPS needed for phone GPS. |
| D6 | UI French; emergency screen French + Arabic | open | Alert strings are English for now in `analysis/texts.py`; FR/AR to be added there. |
| D8 | ML scope | open | Waiting for the data/AI brief. ML stays out of the safety path. |
| D11 | Repo `Ayoub-Meziani/pulse`, `main` protected, Ayoub merges | proposed | Branch protection not yet enabled on GitHub (needs the owner). |
| D12 | Contract source of truth = `api/app/schemas.py` → `contract/openapi.json` | proposed | CI checks the exported file is current. |
| D13 | No migration tool for now; schema created at startup, demo DB rebuilt with `python -m app.seed --reset` | proposed | Add Alembic before any data must survive a schema change. |
| D14 | Auth: seeded demo accounts, JWT (HS256), PBKDF2 password hashes; no registration | proposed | Demo password documented in README. |
| D15 | Measurement provenance: `source` ∈ manual/device/imported/simulated + `source_ref` + `external_id` (dedupe → 409) | proposed | Any device/CSV adapter posts through the same endpoint. |
| D16 | Alert wording returned by the API in English for now | proposed | Frontend shows `reason` / `next_step`; localisation to follow in the same file. |
