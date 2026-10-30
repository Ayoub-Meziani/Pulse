"""Create the three FICTIONAL demo accounts in the LOCAL dev stack (scripts/dev_stack.py) and their data.

    python scripts/dev_seed.py

- Refuses to run unless .dev/api.env points at 127.0.0.1 (never a shared or cloud project).
- Accounts are created through Supabase Auth (signup on the local Auth server), never by writing password
  hashes. Passwords are random, written only to .dev/demo-credentials.txt (git-ignored) and never printed.
- Readings, symptoms, care plan, notes and contacts go through the real API (in-process, real tokens), so the
  deterministic rules create the alerts exactly as they would for a real patient.
- Only what the API cannot write is inserted directly, all labelled simulated: Patient B's simulated history and
  a simulated ring (device + samples). Roles, names and doctor assignments are set by SQL, as an administrator
  would provision them.
- Run once per fresh stack. Re-running stops when the accounts already exist.

Accounts (all fictional, emails on the reserved .test domain):
  patient.a@demo.pulse.test  Patient A  manual readings only, normal and above target, symptom history, no wearable
  patient.b@demo.pulse.test  Patient B  simulated history + manual severe reading (open alert) + simulated ring
  medecin@demo.pulse.test    Doctor     assigned to A and B only
"""
from __future__ import annotations

import json
import random
import secrets
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_db import psql

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / ".dev"
API_ENV = DEV / "api.env"
CREDENTIALS = DEV / "demo-credentials.txt"
DB = "pulse-dev-db"
ACCOUNTS = [
    ("patient_a", "patient.a@demo.pulse.test", "Nadia Benali (démo)", "patient"),
    ("patient_b", "patient.b@demo.pulse.test", "Karim Haddad (démo)", "patient"),
    ("doctor", "medecin@demo.pulse.test", "Dr Leïla Mansouri (démo)", "doctor"),
]


def load_env() -> dict:
    if not API_ENV.exists():
        sys.exit("No .dev/api.env: run `python scripts/dev_stack.py up` first.")
    env = dict(line.split("=", 1) for line in API_ENV.read_text(encoding="utf-8").splitlines()
               if line and not line.startswith("#"))
    for key in ("PULSE_DATABASE_URL", "SUPABASE_URL"):
        if "127.0.0.1" not in env.get(key, ""):
            sys.exit(f"Refusing to seed: {key} is not a local (127.0.0.1) address.")
    return env


def sql(statement: str) -> str:
    r = psql(DB, statement.encode())
    if r.returncode != 0:
        sys.exit(f"SQL failed: {r.stderr.decode(errors='replace')[:600]}")
    return r.stdout.decode()


def signup(supabase_url: str, email: str, password: str) -> str:
    req = urllib.request.Request(f"{supabase_url}/auth/v1/signup", method="POST",
                                 data=json.dumps({"email": email, "password": password}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"signup of {email} failed ({e.code}); is the stack fresh? {e.read()[:200]!r}")
    return (body.get("user") or body)["id"]


def main() -> None:
    env = load_env()
    if CREDENTIALS.exists():
        sys.exit("Demo accounts already exist for this stack (.dev/demo-credentials.txt).")
    import os
    os.environ.update({k: v for k, v in env.items()})
    sys.path.insert(0, str(ROOT / "api"))
    from fastapi.testclient import TestClient

    from app.main import create_app

    api = TestClient(create_app())
    passwords, ids = {}, {}
    for key, email, name, role in ACCOUNTS:
        passwords[key] = secrets.token_urlsafe(12)
        ids[key] = signup(env["SUPABASE_URL"], email, passwords[key])
        sql(f"update public.profiles set role = '{role}', display_name = '{name}' where id = '{ids[key]}';")
    a, b, doc = ids["patient_a"], ids["patient_b"], ids["doctor"]
    sql(f"insert into public.doctor_patient_assignments (doctor_id, patient_id) values ('{doc}', '{a}'), ('{doc}', '{b}');"
        f"insert into public.patient_profiles (user_id, regular_doctor_id) values ('{a}', '{doc}'), ('{b}', '{doc}') "
        f"on conflict (user_id) do update set regular_doctor_id = excluded.regular_doctor_id;")

    def token(key):
        email = next(e for k, e, _, _ in ACCOUNTS if k == key)
        r = api.post("/api/v1/auth/login", json={"email": email, "password": passwords[key]})
        if r.status_code != 200:
            sys.exit(f"login of the demo {key} failed: {r.status_code}")
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def call(method, path, headers, body=None, ok=(200, 201)):
        r = api.request(method, f"/api/v1{path}", headers=headers, json=body)
        if r.status_code not in ok:
            sys.exit(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ha, hb, hd = token("patient_a"), token("patient_b"), token("doctor")

    # Doctor: care plan, follow-up advice (visible to the patient), private note (doctor only).
    call("PUT", f"/patients/{a}/care-plan", hd, {"target_systolic": 135, "target_diastolic": 85,
         "monitoring_readings_per_day": 2,
         "clinician_guidance": "Mesurez votre tension le matin et le soir, assis, après 5 minutes de repos."})
    call("POST", f"/patients/{a}/notes", hd, {
        "note": "Note privée de démonstration : profil stable, revoir les mesures du soir.",
        "advice": "Continuez à noter vos mesures matin et soir jusqu'au prochain rendez-vous.",
        "follow_up_at": (now + timedelta(days=7)).isoformat()})

    # Patient A: manual readings over ten days (entered through the API like a patient would).
    rng = random.Random(7)
    for days in range(10, 0, -1):
        for hour in (7, 20):
            at = (now - timedelta(days=days)).replace(hour=hour, minute=rng.randint(0, 40))
            s, d = rng.randint(118, 132), rng.randint(74, 84)
            if (days, hour) in {(4, 20), (2, 7)}:
                s, d = 146 + days, 93  # above the general target
            call("POST", f"/patients/{a}/measurements", ha, {
                "id": str(uuid.uuid4()), "systolic": s, "diastolic": d, "pulse": rng.randint(64, 80),
                "measured_at": at.isoformat(), "body_position": "sitting", "rested_5_min": True,
                "context": "Saisie de démonstration (données fictives)"})
    call("POST", f"/patients/{a}/symptom-reports", ha, {"symptoms": ["dizziness"],
         "notes": "Démo : léger vertige en se levant."})
    call("POST", f"/patients/{a}/trusted-contacts", ha, {"name": "Samir Benali (démo)", "relationship": "Frère",
         "phone": "+213 000 00 00 01", "contact_consented": True})

    # Patient B: fourteen days of SIMULATED history (labelled), then manual readings through the API.
    values = []
    for days in range(14, 2, -1):
        for hour in (8, 21):
            at = (now - timedelta(days=days)).replace(hour=hour, minute=rng.randint(0, 50))
            values.append(f"('{b}', {rng.randint(132, 152)}, {rng.randint(84, 96)}, {rng.randint(70, 88)}, "
                          f"'{at.isoformat()}', 'simulated', 'simulated', 'unknown')")
    sql("insert into public.measurements (patient_id, systolic, diastolic, pulse, measured_at, source, provenance, "
        "method) values " + ",".join(values) + ";")
    severe_at = (now - timedelta(days=2)).replace(hour=9, minute=10)
    first = call("POST", f"/patients/{b}/measurements", hb, {"id": str(uuid.uuid4()), "systolic": 182, "diastolic": 112,
                 "pulse": 92, "measured_at": severe_at.isoformat(), "body_position": "sitting",
                 "context": "Saisie de démonstration (données fictives)"})
    call("POST", f"/patients/{b}/symptom-reports", hb, {"symptoms": [], "measurement_id": first["measurement"]["id"]})
    call("POST", f"/patients/{b}/measurements", hb, {"id": str(uuid.uuid4()), "systolic": 174, "diastolic": 106,
         "pulse": 88, "measured_at": (severe_at + timedelta(minutes=4)).isoformat(), "body_position": "sitting",
         "context": "Mesure de contrôle (démo)"})
    for days, (s, d) in ((1, (148, 94)), (0, (142, 90))):
        call("POST", f"/patients/{b}/measurements", hb, {"id": str(uuid.uuid4()), "systolic": s, "diastolic": d,
             "pulse": 80, "measured_at": (now - timedelta(days=days, hours=2)).isoformat(),
             "context": "Saisie de démonstration (données fictives)"})

    # Patient B: a SIMULATED ring. Heart rate and SpO2 are never blood pressure and never feed an alert.
    ring = uuid.uuid4()
    sql(f"insert into public.devices (id, patient_id, device_type, bp_capability, manufacturer, model, label) values "
        f"('{ring}', '{b}', 'simulator', 'simulated', 'PULSE', 'Simulateur', 'Bague simulée (démo)');")
    samples = []
    for days in range(7, 0, -1):
        for hour in (1, 3, 5):
            at = (now - timedelta(days=days)).replace(hour=hour, minute=0)
            samples.append(f"('{b}', '{ring}', 'heart_rate', {rng.randint(56, 66)}, 'bpm', '{at.isoformat()}', 'simulated')")
            samples.append(f"('{b}', '{ring}', 'spo2', {rng.randint(94, 98)}, 'percent', '{at.isoformat()}', 'simulated')")
    sql("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source) values "
        + ",".join(samples) + ";")

    CREDENTIALS.write_text("\n".join(
        ["# LOCAL demo accounts (fictional). Generated by scripts/dev_seed.py. Never commit or share publicly.", ""]
        + [f"{role:8} {email:32} {passwords[key]}" for key, email, _, role in ACCOUNTS]) + "\n", encoding="utf-8")
    counts = sql("select (select count(*) from public.measurements) readings, (select count(*) from public.alerts) alerts, "
                 "(select count(*) from public.wearable_samples) samples;")
    print("[seed] demo accounts created:", ", ".join(email for _, email, _, _ in ACCOUNTS))
    print("[seed] passwords written to .dev/demo-credentials.txt (git-ignored, not printed)")
    print("[seed] totals:", " ".join(counts.split()))


if __name__ == "__main__":
    main()
