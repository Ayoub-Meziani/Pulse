# Tasks each developer can start now (2026-10-30)

Shared contracts: `contract/openapi.json` (branch `feat/api-contract-v1`, once pushed), `PULSE_INTEGRATION_CONTRACTS.md`, `supabase/migrations/` (branch `AI`). One owner per path; Ayoub merges into `main`.

## Ayoub — backend + integration

| # | Task | Input | Output / done when |
|---|---|---|---|
| 1 | Approve and push `feat/api-contract-v1`; open its PR | local `fb0acc9` | `contract/openapi.json` on GitHub for the frontend |
| 2 | Disable public sign-up on `pulse` (Dashboard → Authentication → Sign In / Providers) | — | `GET /auth/v1/settings` shows `disable_signup: true` |
| 3 | Merge order: PR #1 → `AI` → contract v1 (reconciliation §5) | open PRs | `main` contains `supabase/migrations` and contract v1 |
| 4 | `feat/api-supabase` steps 1–3: test-DB scripts, fixtures, `db.py`, mapped models, JWKS auth, login/refresh, `/me`, permissions | `PULSE_DB_INTEGRATION_PLAN.md` §1–§4 | auth + A8 permission tests green on the test container |
| 5 | Steps 4–5: measurements + symptoms + alerts with rules in the same response | §1, §5 | crisis scenario 186/118 → symptom check → chest pain → emergency, one alert |
| 6 | Steps 6–8: doctor list, summary, profile, contacts, card, emergency events, notes, predictions | §1 | matching contract tests return 2xx instead of 501 |

## Data/AI developer

| # | Task | Input | Output / done when |
|---|---|---|---|
| 1 | ~~Migration **M3 `backend_alignment`**~~ **Done and live** (verified); M5 `birth_year` awaits Ayoub's review, then `db push` + changelog row | as a new file after `20261029120100` (contents: `PULSE_DB_INTEGRATION_PLAN.md` §6 / contracts §3.1) with tests in `tests/test_db.py`; PR to `main`; do **not** `db push` before approval | live schema = `AI` branch | PR with migration + tests; after approval `db push` to `pulse` and a line in `PULSE_SUPABASE_CHANGELOG.md` |
| 2 | Fix `docs/data/DATA_SCHEMA.md`: `alerts.resolution_note` exists; state the `actions_attempted` element shape `{client_action_id, action, at, detail, confirmed}` | — | doc updated |
| 3 | ML pipeline in `ml/` per contracts §4: BP-history features only, patient-level split, persistence + 7-day-mean baselines, linear + HistGradientBoosting, MAE/RMSE with CIs labelled "synthetic", `MODEL_CARD.md`, `metadata.json` | synthetic set from `pulse_data.simulate csv` | reproducible `python -m pulse_ml.train`; metrics file |
| 4 | ~~Migration **M4** + batch job~~ **Done** (M4 live, `pulse_ml.predict` on `AI`); remaining ML follow-ups in `PULSE_ML_REVIEW.md` | contracts §3.1 (M4), §4 | rows with `status ok/insufficient_history` on the local DB |
| 5 | Seed scenarios for the demo (controlled / rising / severe event / sparse) incl. profiles and trusted contacts; local only until sign-up is off | `simulate.py seed` | seed loads on the local DB; then on `pulse` with Ayoub's go |

Do not: write to `alerts` from data tools (the backend rules own them), edit applied migrations, push `seed.sql`.

## Frontend developer

| # | Task | Input | Output / done when |
|---|---|---|---|
| 1 | Confirm `frontend/` as the single app (B19); add a Vite proxy `/api → http://127.0.0.1:8000` | `feat/web-scaffold` `web/vite.config.ts` as reference | dev server proxies to the API |
| 2 | API layer: `openapi-fetch` client + types generated from `contract/openapi.json` (JS project can still import `.ts`), token in `sessionStorage`, refresh on 401 | `web/src/api/client.ts` as reference | one module all pages use; no hard-coded demo data in pages that have an endpoint |
| 3 | **Emergency screen** (product priority 1): fetch and cache `GET /config/emergency` (works today), `tel:` to `primary_number_id`, DEMO banner when `demo_mode`, trusted-contact call/share, emergency card from cache, offline fallback rules from `client_fallback`; action logging wording "tapped/opened" | contracts §2.4–§2.5 | works with network off after one load |
| 4 | Login + Add reading → result → symptom check (13 codes, 7 red flags shown first) → recheck timer → emergency; handle 501 with a "bientôt disponible" message | `web/src/flow.ts` + tests as reference | flow unit-tested; ready when backend step 5 lands |
| 5 | Align existing screens with the contract: profile fields, alerts from the API (unread = `open`), doctor list from `GET /patients` (15 s polling), replace "État du capteur" with "Saisie manuelle" | reconciliation §4 | no field that the API cannot provide |

Integration checkpoints: C1 contract pushed → C3 backend parity on the test DB → C4 emergency path end to end → C5 ML visible → C6 demo from reset (contracts §5).
