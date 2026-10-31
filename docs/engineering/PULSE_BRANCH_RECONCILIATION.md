# Branch reconciliation (2026-10-30)

All facts VERIFIED with `git fetch --all` and `git log/ls-tree/diff` on 2026-10-30. Nothing was merged, rebased or force-pushed.

## 1. Branches and commits

| Branch | Tip | Author | Base | Contents | Pushed |
|---|---|---|---|---|---|
| `main` | `02dc64a` | Ayoub-Meziani | — | Initial commit: README, LICENSE, Node `.gitignore` | yes |
| `feat/api-measurement-slice` (PR #1, open) | `82f7473` | Claude | `main` | FastAPI + SQLite slice (10 ops, 39 tests), docs, CI, conception, handoff | yes |
| `docs/backend-architecture` | this branch | Claude | `82f7473` | `PULSE_*.md` architecture, plan, contracts, blockers, Supabase changelog, this report | yes |
| `feat/api-contract-v1` | `fb0acc9` | Claude | `82f7473` | Contract v1 (34 ops, 49 schemas), 501 stubs, emergency config, 101 tests | **local only** (awaiting approval) |
| `feat/web-scaffold` | `acb3e04` | Claude | `82f7473` | `web/` React + TS scaffold (typed client, login, Add-reading flow) | **local only** |
| `AI` | `a004329` | Chaboutiar07 (data/AI) | `main` | `supabase/` (config, 2 migrations), `pulse_data/` (ingest, simulate), `tests/` (test_db, test_ingest), `samples/`, `requirements.txt`, `docs/data/` (9 docs + `export/pulse_schema.sql`) | yes |
| `feature/frontend` | `8d264a9` | ik07072007 (frontend) | `main` | `frontend/` React 19 + **JavaScript** + Tailwind 4 + react-router 8 + recharts; 6 pages with hard-coded demo data | yes |

```
02dc64a main
├── 54937fa ─ 82f7473 feat/api-measurement-slice (PR #1)
│                ├── d359e70 ─ 815034e ─ … docs/backend-architecture
│                ├── fb0acc9 feat/api-contract-v1 (local)
│                └── acb3e04 feat/web-scaffold (local)
├── a004329 AI
└── 8d264a9 feature/frontend
```

## 2. Overlaps and conflicts

| Pair | File overlap | Merge risk |
|---|---|---|
| `AI` ↔ backend branches | None (`supabase/`, `pulse_data/`, `tests/`, `samples/`, `docs/data/`, root `requirements.txt` do not exist on backend branches) | None. Note: root `tests/` (data) vs `api/tests/` (backend) are separate test suites with separate dependencies. |
| `feature/frontend` ↔ others | None (`frontend/`) | None |
| `feature/frontend` ↔ `feat/web-scaffold` | Different folders (`frontend/` vs `web/`), **two competing frontend apps** | Decision needed (below) |
| `feat/api-contract-v1` ↔ PR #1 | Replaces the SQLite models/services/seed and their API tests | Intended; PR #1 keeps the originals in history |

## 3. `AI` branch vs the live Supabase project

| Check | Result | Evidence |
|---|---|---|
| Migration files | `20261029120000_core_schema.sql`, `20261029120100_access_policies.sql` | `git ls-tree origin/AI` |
| Live migration history | same two versions, same order | `supabase migration list --linked` |
| Apply on the live Postgres version | both apply cleanly (`ON_ERROR_STOP`) on `public.ecr.aws/supabase/postgres:17.11.0.003` (same build as the live project) | throwaway container, removed afterwards |
| Schema equality | **273 of 273 normalized statements identical** in `public` + `private` (tables, columns, CHECKs, FKs, indexes, functions, triggers, RLS policies, grants); 0 only-live, 0 only-migrations | `pg_dump --schema-only` of the throwaway DB vs `supabase db dump --linked`, compared after removing comments, ownership, quoting and `IF NOT EXISTS` |
| Auth trigger | `on_auth_user_created` on `auth.users` present in both | dumps |
| Seed | not committed; generator `pulse_data/simulate.py seed` reads the password from `PULSE_DEMO_PASSWORD` | code on `AI` |
| `rules.py` | not present (removed as requested) | `git ls-tree` |
| ML | none | `git ls-tree` |

**Conclusion: the `AI` branch migrations are the exact source of the live schema. They are the single migration history; nothing needs to be re-sent or recreated.**

## 4. The two frontends — decision needed

| | `feature/frontend` (frontend developer) | `feat/web-scaffold` (Claude, local) |
|---|---|---|
| Language | JavaScript (JSX) | TypeScript |
| UI | 6 screens: patient dashboard, doctor dashboard, patient details, alerts, profile, layout; Tailwind; charts | Login + Add-reading flow only, plain CSS |
| API | none (hard-coded demo data) | typed `openapi-fetch` client from `contract/openapi.json`, Vite proxy `/api` |
| Safety flow | none yet (no symptom check, recheck timer or emergency screen) | reading → symptom check → recheck timer → emergency placeholder, unit-tested |

**Recommendation:** `frontend/` (the frontend developer's app) is the only app. Do not push `feat/web-scaffold` as a second app. The frontend developer ports from it what saves time: `src/api/client.ts` + generated `schema.d.ts` (Vite compiles `.ts` inside a JS project without extra setup), `src/flow.ts` + its tests, and the Vite proxy block. `CLAUDE.md` ownership changes from `web/` to `frontend/`.

Gaps in `frontend/` against contract v1 (for the frontend developer):
- Profile: `firstName/lastName` → `full_name`; `age` → `birth_year` (M5, pending review); `emergencyContact` → trusted contacts; `doctorName` → `regular_doctor_name` (read-only), `doctorPhone` not stored (use `regular_clinic`); patient's own `phone` not stored.
- Patient dashboard "État du capteur" card: no device integration exists; show "Saisie manuelle" instead of a sensor status.
- Alerts page: alerts come from `GET /patients/{id}/alerts`; unread = `open`; there are no informational "new measurement recorded" notifications in the API.
- Doctor dashboard: `age` from `PatientListItem.age` (null until M5 is applied and the patient enters a birth year); sort is done by the API.
- Missing screens for the MVP: login, Add reading + symptom check + recheck timer, emergency screen (offline cache, `tel:` to `primary_number_id`, trusted contact, card), urgent "Urgence" button.

## 5. Recommended merge order (Ayoub decides)

1. PR #1 `feat/api-measurement-slice` → `main` (baseline docs, CI, rules).
2. `AI` → `main` as a PR (no conflicts; its own test suite).
3. `feat/api-contract-v1` → `main` after push + review.
4. `feature/frontend` → `main` once it uses the contract (or earlier as UI-only; no conflicts).
5. `docs/backend-architecture` → `main` (documentation).
