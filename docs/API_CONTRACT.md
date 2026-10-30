# API contract (v1)

**Source of truth:** `api/app/schemas.py` and the routers → generated `contract/openapi.json`
(`python -m app.export_openapi`; CI fails if it is stale). Interactive docs: `http://127.0.0.1:8000/api/v1/docs`.
Human-readable summary, endpoint list, frontend flow rules and database/ML contracts: `PULSE_INTEGRATION_CONTRACTS.md`.

- Base path `/api/v1`, JSON, ids are uuid strings, timestamps ISO 8601 with offset.
- Auth: `POST /auth/login` → `Authorization: Bearer <access_token>`; `POST /auth/refresh`.
- Errors: `{"error": {"code", "message", "details"}}`.
- Status: `GET /health` and `GET /config/emergency` work. Every other route returns **501 `not_implemented`**
  with its final response schema already in OpenAPI, so clients can be built against the types now.
- Readings and symptom reports return the rule evaluation (`evaluation.show_emergency`, `requires_symptom_check`,
  `recheck_after_seconds`) in the same response. The frontend never computes rules except the offline
  fallback described by `GET /config/emergency` → `client_fallback`.
