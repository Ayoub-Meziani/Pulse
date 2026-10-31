# PULSE data & AI/ML workstream: implementation plan

## Scope
Data/analysis owner's part of PULSE: database, ingestion, validation, synthetic/demo data, then analytics, deterministic alerts and a real ML pipeline. Backend and frontend teammates consume the Supabase tables (docs/API_CONTRACT.md).

## Architecture
```
manual entry / CSV / (future device)  ->  adapter (ingest.py, format checks)
   ->  measurements (DB trigger: plausibility policy pulse-v1, flags, status)  ->  RLS-protected tables
   ->  [next] analytics + deterministic rules -> alerts
   ->  [next] ML dataset -> training/eval -> model artifact -> inference -> ml_predictions
```
Raw/validated measurements, patient-reported data, clinician-authored data, rule alerts and (future) ML predictions live in separate tables. Synthetic rows are always labelled `simulated`.

## Status
| phase | status |
|---|---|
| 0 Repo audit | done: no prior repo; starter kit + conception report reused |
| 1 Data model, migrations, RLS, contracts | **done**: 2 migrations, docs/DATA_DICTIONARY.md, docs/API_CONTRACT.md |
| 2 Ingestion (manual, CSV, simulator), dedup, validation | **done**: device adapter blocked on hardware |
| Synthetic data (seed, ML set, sample) | **done**, labelled |
| 3 Trend analytics + deterministic alerts | next |
| 4 ML pipeline (mandatory) | after 3: dataset decision in docs/DATA_SOURCES.md |
| 5 Lifestyle context analytics | tables done; analytics later |
| 6 Integration with backend/frontend | contract published; waiting for teammates |
| 7 Demo | seed scenarios ready |

## Decisions
- Supabase (Postgres 17 + Auth + RLS); local stack for dev/test on ports 553xx.
- Starter `sql/schema.sql` superseded by migrations (single schema source). Fixed: `data_quality_review` alert class, flagged-not-rejected readings, provenance, dedup, BP targets in care plans, RLS.
- Validation policy lives in one DB trigger so every write path shares it.
- Clients may only insert `manual` readings; imports/device sync/rule alerts are server-side.

## Blockers / open items
- No BP device chosen: real adapter not built (docs/DEVICE_INTEGRATION.md).
- No open multi-patient longitudinal home-BP dataset found: ML will start on labelled synthetic data (docs/DATA_SOURCES.md).
- ~~Alert thresholds and emergency wording need clinician review; emergency number must be verified~~: done 30 Oct 2026 (medical mentor review; number **14**). Validation limits (`pulse-v1`) remain engineering defaults.
- Backend teammate to confirm: who owns the shared Supabase project and applies migrations.

## Next concrete task
Superseded by the team contract (`docs/engineering/PULSE_INTEGRATION_CONTRACTS.md` §3–4): analytics and alert rules are backend-owned. Data/AI next: migration M3 `backend_alignment`, migration M4 `ml_predictions`, then the ML pipeline in `ml/` (next-day morning mean BP, doctor-only).
