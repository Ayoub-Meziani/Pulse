# Device integration

## Status (29 Oct 2026)
**No physical device is integrated.** The team has no device yet.

| path | status | provenance written |
|---|---|---|
| Manual entry (frontend → Supabase insert) | implemented, RLS-tested | `source=manual`, `provenance=measured` |
| CSV import (`python -m pulse_data.ingest import-csv`) | implemented, tested | `source=csv_import`, provenance **stated by the operator** |
| Simulator (`pulse_data.simulate`) | implemented; feeds the seed | `source/provenance=simulated`, device type `simulator` |
| Ring CSV import (`python -m pulse_data.ingest import-wearable-csv`) | implemented, tested (31 Oct) | `wearable_samples.source` = `simulated` or `csv_import`, **stated by the operator** |
| Live simulated ring (`python -m pulse_data.stream --patient-email …`) | implemented (demo) | `source=simulated` |
| Live Bluetooth heart-rate bracelet (`python -m pulse_data.ble_bridge --patient-email …`; any device with the standard Heart Rate Service 0x180D) | implemented (31 Oct; local stack only; tested without hardware) | `wearable_samples.source=device_sync`: heart rate every 5 s, HRV (RMSSD) every 5 min when the device sends RR intervals; device `wearable`, labelled "<name> (Bluetooth)" |
| Real cuff / other real ring data | **not implemented** (ring / cuff CSV exports only) | — |

Never present simulated readings as a working hardware integration.

## Normalised reading (what every adapter produces)
`pulse_data.ingest.Reading`:
`measured_at` (aware datetime), `systolic`, `diastolic` (mmHg), `pulse` (bpm, optional), `measured_tz`, `external_id` (only if the device supplies one), `body_position`, `arm`, `context`, `quality_flags` (device-reported), `row` (source line).
Adapters only do format checks; plausibility is decided by the DB trigger (see DATA_DICTIONARY.md).
Batch import: `import_readings(conn, patient_id, readings, source=..., provenance=..., method=..., device_id=...)`.

## CSV format (cuff-app exports)
```
measured_at,systolic,diastolic,pulse,unit,position,arm,note
2026-10-14 06:27,132,88,75,mmHg,sitting,left,
```
Required: `measured_at` (ISO 8601; no offset → `--tz`), `systolic`, `diastolic`. Optional: `pulse`, `unit` (mmHg only; kPa rows are rejected, never converted silently), `external_id` (needs `--device`), `position`, `arm`, `note`. Lines starting with `#` are comments. Re-importing the same file is refused (SHA-256 per patient).

## Ring CSV format (ring / bracelet exports)
```
measured_at,metric,value,unit,external_id
2026-10-20T02:00:00+01:00,heart_rate,58,bpm,a1
```
Required: `measured_at`, `metric` (`heart_rate` bpm, `hrv_rmssd` ms, `spo2` percent, `skin_temperature` celsius), `value`. Optional: `unit` (defaults to the metric's; `%` and `°C` accepted), `external_id`. Value ranges are enforced by the database (a refused row is reported, the rest is kept). The patient's ring is used, or created if missing (`simulator` for `--source simulated`, `wearable` for real exports). A sample already stored for the same device (same `external_id`, or same metric at the same instant) is skipped, so re-importing never duplicates. Never an alert input. Presentation steps: `DEMO_RUNBOOK.pdf`.

## Adding a real blood-pressure cuff (recommended path)
Use an upper-arm cuff that is clinically validated (check validatebp.org / STRIDE BP lists) as the BP reference.
1. Identify the exact model and its export options: app CSV export, vendor cloud API (OAuth, needs vendor developer account), or Bluetooth.
2. Bluetooth cuffs that implement the standard **Blood Pressure Profile** (service 0x1810, characteristic *Blood Pressure Measurement* 0x2A35) can be read from Chrome on Android via Web Bluetooth. Map: systolic, diastolic (unit flag mmHg/kPa → reject kPa or convert explicitly and record it), timestamp (if present, else receive time + flag), pulse rate, measurement-status bits → `body_movement`, `cuff_fit_issue`, `irregular_pulse`, `improper_position`.
3. Create a `devices` row (`device_type=bp_cuff`, `bp_capability=measured`, manufacturer, model, serial as `external_device_id`).
4. Write an adapter `parse_<vendor>(payload) -> list[Reading]`, store the original in `raw_payload` if small, use the device's record id as `external_id` (dedup), `method=cuff_oscillometric`.
5. Insert through `import_readings(..., source="device_sync")` from server-side code (service role). Clients cannot write `device_sync` rows.
6. Add tests with recorded sample payloads (fictional values) before claiming the integration works.

## Smart ring / watch
Most rings/watches give heart rate, activity, sleep and at most **estimated** BP. Treat them as:
- estimated BP → `provenance=estimated`, `method=wearable_estimate` → always `needs_review` (`estimated_not_cuff`), never equivalent to a cuff;
- activity/sleep → `lifestyle_logs` with `source=device`.
Do not assume a ring measures blood pressure; check the manufacturer's documented capabilities and API first.

## Configure & test
```
.venv\Scripts\python -m pulse_data.ingest import-csv --patient yacine.demo@pulse.test --file samples\readings_sample.csv --provenance simulated
```
The sample is synthetic, so it is imported with `--provenance simulated`.
