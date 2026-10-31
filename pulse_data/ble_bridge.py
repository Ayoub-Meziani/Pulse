"""LIVE Bluetooth heart-rate bracelet -> public.wearable_samples (REAL data, source 'device_sync'). Local stack only.

    python -m pulse_data.ble_bridge --scan
    python -m pulse_data.ble_bridge --patient-email patient.a@demo.pulse.test [--address AA:BB:CC:DD:EE:FF] [--interval 5]

Any device with the standard Bluetooth Heart Rate Service (0x180D): e.g. Polar Verity Sense / H10, a Coospo armband,
a watch in "broadcast heart rate" mode. Disconnect it from its phone app first (most accept one connection at a time).
Every --interval seconds the median heart rate of the notifications received is stored; every 5 minutes, when the
device sends RR intervals, their RMSSD is stored as hrv_rmssd (many optical bands send none: no HRV then).
measured_at = the database's now(), the clock the live monitor's 2-minute freshness gate uses. The device row is the
patient's wearable whose external_device_id is the Bluetooth address, labelled "<name> (Bluetooth)", added on first use.
A consumer sensor, not a medical device: like every ring sample, never read by the rules (D18). No SpO2, temperature or
blood pressure: no affordable bracelet streams them on a standard profile. Reconnects until Ctrl+C. Prints counts only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from collections import Counter

import psycopg

from .ingest import LOCAL_DB, WEARABLE_UNITS, resolve_patient
from .localdb import require_local

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
HRV_EVERY = 300            # seconds of RR intervals behind one RMSSD value
MIN_RR = 30                # plausible intervals needed for one RMSSD value
RR_RANGE = (300, 2000)     # ms (200-30 bpm); outside is a missed or extra beat
SCAN_SECONDS = 10
INSERT = ("insert into public.wearable_samples (patient_id, device_id, metric, value, unit, measured_at, source)"
          " values (%s, %s, %s, %s, %s, now(), 'device_sync')")


def parse_hrm(data: bytes) -> tuple[int | None, list[float]]:
    """Heart Rate Measurement (0x2A37) -> (bpm, RR intervals in ms). bpm is None when the sensor reports no skin
    contact or 0."""
    flags = data[0]
    hr, i = (int.from_bytes(data[1:3], "little"), 3) if flags & 0x01 else (data[1], 2)
    if flags & 0x06 == 0x04:   # contact detection supported, no contact
        return None, []
    if flags & 0x08:           # energy expended, unused
        i += 2
    rr = [int.from_bytes(data[j:j + 2], "little") * 1000 / 1024 for j in range(i, len(data) - 1, 2)] \
        if flags & 0x10 else []
    return (hr or None), rr


def rmssd(rr: list[float]) -> float | None:
    """RMSSD (ms) of successive RR intervals; None with fewer than MIN_RR plausible ones."""
    # ponytail: out-of-range beats are dropped, no ectopic-beat correction; add artefact filtering before real HRV use.
    ok = [x for x in rr if RR_RANGE[0] <= x <= RR_RANGE[1]]
    if len(ok) < MIN_RR:
        return None
    return round(statistics.fmean((b - a) ** 2 for a, b in zip(ok, ok[1:])) ** 0.5, 2)


def bracelet_device(conn, patient_id: str, address: str, name: str | None) -> str:
    """The patient's wearable with this Bluetooth address, added on first use."""
    found = conn.execute("select id from public.devices where patient_id = %s and external_device_id = %s",
                         (patient_id, address)).fetchone()
    if found:
        return str(found[0])
    return str(conn.execute(
        "insert into public.devices (patient_id, device_type, bp_capability, external_device_id, label)"
        " values (%s, 'wearable', 'none', %s, %s) returning id",
        (patient_id, address, f"{name or 'Bracelet'} (Bluetooth)")).fetchone()[0])


def store(conn, patient_id: str, device_id: str, metric: str, value: float) -> int:
    try:
        conn.execute(INSERT, (patient_id, device_id, metric, value, WEARABLE_UNITS[metric]))
        return 1
    except psycopg.errors.CheckViolation:   # outside the database's plausible range: skip this value only
        return 0


async def heart_rate_devices() -> list:
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=SCAN_SECONDS, return_adv=True, service_uuids=[HR_SERVICE])
    return sorted(found.values(), key=lambda d: -d[1].rssi)


async def find(address: str | None):
    if address:
        from bleak import BleakScanner

        return await BleakScanner.find_device_by_address(address, timeout=SCAN_SECONDS)
    devices = await heart_rate_devices()
    return devices[0][0] if devices else None


async def bridge(conn, patient_id: str, address: str | None, interval: float, counts: Counter) -> None:
    from bleak import BleakClient
    from bleak.exc import BleakError

    hr: list[int] = []
    rr: list[float] = []

    def on_measurement(_, data: bytearray) -> None:
        bpm, intervals = parse_hrm(bytes(data))
        if bpm is not None:
            hr.append(bpm)
            rr.extend(intervals)

    while True:
        device = await find(address)
        if device is None:
            print(json.dumps({"status": "no heart-rate device found, scanning again"}), flush=True)
            continue
        device_id = bracelet_device(conn, patient_id, device.address, device.name)
        hr.clear()
        rr.clear()
        try:
            async with BleakClient(device) as client:
                await client.start_notify(HR_MEASUREMENT, on_measurement)
                print(json.dumps({"status": "connected", "device": device.name}), flush=True)
                hrv_due = report_due = time.monotonic()
                while client.is_connected:
                    await asyncio.sleep(interval)
                    if hr:
                        counts["heart_rate"] += store(conn, patient_id, device_id, "heart_rate", statistics.median(hr))
                        hr.clear()
                    now = time.monotonic()
                    if now - hrv_due >= HRV_EVERY:
                        if (v := rmssd(rr)) is not None:
                            counts["hrv_rmssd"] += store(conn, patient_id, device_id, "hrv_rmssd", v)
                        rr.clear()
                        hrv_due = now
                    if now - report_due >= 60:
                        print(json.dumps({"samples_inserted": dict(counts)}), flush=True)
                        report_due = now
        except (BleakError, OSError, asyncio.TimeoutError) as e:
            print(json.dumps({"status": "disconnected, reconnecting", "error": type(e).__name__}), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="list nearby heart-rate devices and exit")
    ap.add_argument("--patient-email", help="the patient who wears the bracelet")
    ap.add_argument("--address", help="Bluetooth address (default: the strongest heart-rate device found)")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between stored heart-rate values")
    a = ap.parse_args()
    if a.scan:
        found = asyncio.run(heart_rate_devices())
        print(json.dumps([{"name": d.name, "address": d.address, "rssi": adv.rssi} for d, adv in found], indent=2))
        return
    if not a.patient_email:
        ap.error("--patient-email is required (or use --scan)")
    url = os.environ.get("DATABASE_URL", LOCAL_DB)
    require_local(url)
    counts: Counter[str] = Counter()
    with psycopg.connect(url, autocommit=True) as conn:
        patient_id = resolve_patient(conn, a.patient_email)
        try:
            asyncio.run(bridge(conn, patient_id, a.address, a.interval, counts))
        except KeyboardInterrupt:
            pass
    print(json.dumps({"samples_inserted": dict(counts), "source": "device_sync"}))


if __name__ == "__main__":
    main()
