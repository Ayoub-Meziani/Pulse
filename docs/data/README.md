# PULSE: data layer

Hypertension monitoring prototype (36-hour hackathon). This part of the repo holds the **database, ingestion and data** for PULSE (`supabase/`, `pulse_data/`, `tests/`, `samples/`). Alert rules and summaries live in the backend (`api/app/analysis/`); ML comes next (`ml/`). Run commands from the repo root.
**Not a clinically validated medical device. All bundled data is fictional and labelled `simulated`.**

## Layout
| path | what |
|---|---|
| `supabase/migrations/` | schema, validation trigger, audit trail, row-level security |
| `supabase/seed.sql` | generated demo data (git-ignored; regenerate) |
| `pulse_data/ingest.py` | CSV adapter + batch import CLI |
| `pulse_data/simulate.py` | labelled synthetic data: seed, ML dataset, sample CSV |
| `tests/` | ingestion, database/RLS tests |
| `docs/data/` | data dictionary, schema, device integration, data sources, data-layer contract, inventories |

## Setup (Windows, from this folder)
```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```
Docker Desktop must be running. Use Supabase CLI **2.122.0** through npx (the globally installed 2.40.7 references a corrupted cached image on this machine):
```
npx -y supabase@2.122.0 start -x realtime,storage-api,imgproxy,edge-runtime,logflare,vector,supavisor
npx -y supabase@2.122.0 db reset      # LOCAL ONLY: rebuilds the pulse DB from migrations + seed
```
PULSE runs on ports **55321** (API), **55322** (DB), **55323** (Studio), so it can run next to other local Supabase projects on the default 543xx ports.
`db reset` wipes only this project's local container. Never run it against a linked/remote project.

## Demo accounts (password = whatever `PULSE_DEMO_PASSWORD` was when the seed was generated; never committed)
Generate the seed first (it is git-ignored): `set PULSE_DEMO_PASSWORD=<choose one>` then `.venv\Scripts\python -m pulse_data.simulate seed`.
| email | role | scenario |
|---|---|---|
| dr.leila.demo@pulse.test | doctor | assigned to Amina, Karim, Nadia |
| admin.demo@pulse.test | admin | reads everything |
| amina.demo@pulse.test | patient | controlled, near target |
| karim.demo@pulse.test | patient | rising trend with gaps |
| nadia.demo@pulse.test | patient | severe reading (186/118, repeated) + chest pain report 2 days ago |
| yacine.demo@pulse.test | patient | unassigned, sparse, one double entry + one invalid entry |

## Commands
```
.venv\Scripts\python -m pytest -v                       # all tests (DB tests skip if the stack is down)
.venv\Scripts\python -m pulse_data.simulate seed     # regenerate supabase/seed.sql, then db reset
.venv\Scripts\python -m pulse_data.simulate csv      # data/synthetic/ for the ML phase (git-ignored)
.venv\Scripts\python -m pulse_data.ingest import-csv --patient yacine.demo@pulse.test --file samples\readings_sample.csv --provenance simulated
```
Studio (browse tables): http://127.0.0.1:55323

## Applying to a team Supabase project
The team project is `pulse` (ref `nfmfdhpxipdndggxtqho`); both migrations are applied. New migrations: PR approved by the backend lead, then `npx supabase@2.122.0 link --project-ref <ref>` and `npx supabase@2.122.0 db push`. Seed `pulse` only after public sign-up is switched off, with the password from `PULSE_DEMO_PASSWORD`. Migrations are append-only: add a new file, never edit an applied one.
New tables in later migrations must repeat the pattern in `..._access_policies.sql` (enable RLS, revoke anon, grant only what's needed); Supabase's default grants are otherwise wide open.
