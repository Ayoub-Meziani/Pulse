# API contract (v1)

**Source of truth:** `api/app/schemas.py` and the routers → generated `contract/openapi.json`
(`python -m app.export_openapi`; CI fails if it is stale). Interactive docs: `http://127.0.0.1:8000/api/v1/docs`.
Human-readable summary, endpoint list, frontend flow rules and database/ML contracts: `PULSE_INTEGRATION_CONTRACTS.md`.

- Base path `/api/v1`, JSON, ids are uuid strings, timestamps ISO 8601 with offset.
- Auth: `POST /auth/login` → `Authorization: Bearer <access_token>`; `POST /auth/refresh`.
- Errors: `{"error": {"code", "message", "details"}}`.
- Status: every route works except `GET /patients/{id}/daily`, which returns **501 `not_implemented`** with its
  final response schema in OpenAPI.
- Journal: `GET|POST /patients/{id}/journal` (patient writes; patient and assigned doctor read; optional `category`
  filter) and `POST /journal/{id}/review` (assigned doctor; repeating it keeps the first review). Entries are the
  patient's own words (food, activity, symptoms, medication, questions): never analysed, never an alert input (D21).
- Readings and symptom reports return the rule evaluation (`evaluation.show_emergency`, `requires_symptom_check`,
  `recheck_after_seconds`) in the same response. The frontend never computes rules except the offline
  fallback described by `GET /config/emergency` → `client_fallback`.
- `POST /patients/{id}/measurements` accepts an optional client-generated `id` (uuid) for safe retries: the same id
  and values return the stored reading with status 200 and change no alert; other values or another patient's id are 409 (D17).
- `GET /patients/{id}/symptom-reports`, `/devices` and `/wearable-samples` are read only (patient or assigned doctor).
  Wearable data is optional and never feeds rules, alerts or emergency guidance; `measurement_id` of a symptom report
  is always null until the link is stored (B24) (D18).
- `GET /patients/{id}/summary` adds `count_7d_measured`, `count_7d_simulated`, `count_7d_estimated`. They split `count_7d`
  (valid readings of the last 7 days), so they add up to it; `needs_review` and invalid readings are in none of them
  (`count_needs_review_7d`, `count_invalid_7d`). Averages, `pct_above_target_7d` and `trend` still use valid readings of
  any provenance, simulated ones included; they are descriptive and never create alerts (D19, D20).
