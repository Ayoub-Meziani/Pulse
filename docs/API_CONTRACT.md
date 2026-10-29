# API contract (v1)

**Source of truth:** `api/app/schemas.py` → generated `contract/openapi.json`.
Interactive docs when the server runs: `http://127.0.0.1:8000/api/v1/docs`.
This page is a summary; if it disagrees with `openapi.json`, `openapi.json` wins.

- Base path `/api/v1`, JSON, timestamps ISO 8601 UTC (display in Africa/Algiers time on the client).
- Auth: `POST /auth/login` → `Authorization: Bearer <token>`.
- Errors: `{"error": {"code", "message", "details"}}` with 401 / 403 / 404 / 409 / 422.

## Implemented

| Method + path | Who | Notes |
|---|---|---|
| `GET /health` | anyone | |
| `POST /auth/login` | anyone | email + password → token + user |
| `GET /me` | any user | |
| `GET /patients` | doctor | assigned patients, most urgent active alert first, then oldest last reading |
| `POST /patients/{id}/measurements` | the patient | validate → store → rules → `{measurement, evaluation, alert, trend_alert}` |
| `GET /patients/{id}/measurements?from&to&limit` | patient (own), assigned doctor | newest first; `from`/`to` must include a timezone |
| `GET /patients/{id}/summary` | patient (own), assigned doctor | 7/30-day stats, trend, target |
| `POST /patients/{id}/symptom-reports` | the patient | red-flag symptom → `evaluation.show_emergency = true` |
| `GET /patients/{id}/alerts?state=active\|all` | patient (own), assigned doctor | |
| `GET /alerts/{id}` | owner, assigned doctor | includes the audit `events` |

## Measurement provenance (device / import adapter)

Every reading carries `source` (`manual` | `device` | `imported` | `simulated`), optional `source_ref`
(device id, file name, simulator scenario) and optional `external_id`. A repeated
`(patient, source, external_id)` returns **409 `duplicate_measurement`** with `details.existing_id`.
Any future device or CSV importer must post through this endpoint with the correct `source`.
No hardware integration exists yet.

## Frontend flow for a reading

1. POST the reading. Show `evaluation.reason` and `evaluation.next_step`, plus the source tag.
2. If `evaluation.requires_symptom_check`: show the 7-symptom checklist and POST `symptom-reports`
   (empty list = none of these).
3. If any response has `evaluation.show_emergency`: open the Emergency screen immediately.
4. If `recheck_after_seconds` is set and no symptoms were reported: show the timer, then POST the recheck.

## Planned next (not implemented yet)

Alert state transitions (`POST /alerts/{id}/transition`), incidents and incident actions,
emergency config (`GET /config/emergency`) and emergency card, profile and trusted contacts,
journal, doctor notes, care-plan editing, simulator/reset dev endpoints, ML forecast output.
Shapes for these are described in `docs/conception.pdf` section 11 and will be added to
`schemas.py` through coordinated PRs.
