"""Guard [review H3]: ring simulation must not change the blood-pressure data that mbp-v1 and the demo use.

Fingerprints taken on 30 Oct 2026, before any ring change. If one of these fails, BP data changed:
bump GENERATOR_VERSION, retrain mbp-v1 and update the fingerprints deliberately.
"""
import hashlib
import re
from datetime import date

from pulse_data import simulate

FINGERPRINTS = {
    # Deliberately updated 30 Oct 2026 for pulse-sim-v2 (BP variation calibrated on real home BP); models retrained.
    "readings.csv": "70ecbc9b0dcf2da7f6374632b1aee4b8058febdce2d545a87cddc9f39672e705",
    "daily_context.csv": "2935a6dd22f873b135b1ebc1e3b80fceec3d36affbbaa9100cc15736904235f4",
    # BP readings of the demo seed (the measurements insert). Profiles, devices and ring rows may change.
    "seed_measurements": "fc9bc7976c9da7c49d1ec3781bebca0596027a3c753293afb1ecb38b2fe1724d",
}


class FixedDate(date):  # birth_year in the seed depends on today's year
    @classmethod
    def today(cls):
        return cls(2026, 10, 30)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_bp_csv_files_unchanged(tmp_path):
    simulate.write_ml_csv(tmp_path)
    for name in ("readings.csv", "daily_context.csv"):
        assert sha((tmp_path / name).read_bytes()) == FINGERPRINTS[name], name


def test_holdout_cohort_is_unseen(tmp_path):
    """The 30-day backtest cohort (other seed + prefix) shares no patient key or BP series with training."""
    import csv
    simulate.write_ml_csv(tmp_path / "train", patients=5, days=10)
    simulate.write_ml_csv(tmp_path / "holdout", patients=5, days=10, seed=2026, prefix="H")
    rows = {k: list(csv.DictReader(open(tmp_path / k / "readings.csv"))) for k in ("train", "holdout")}
    keys = {k: {r["patient_key"] for r in v} for k, v in rows.items()}
    assert not keys["train"] & keys["holdout"] and all(k.startswith("H") for k in keys["holdout"])
    series = {k: [(r["systolic"], r["diastolic"]) for r in v] for k, v in rows.items()}
    assert series["train"] != series["holdout"]


def test_ring_samples_pass_the_table_checks():
    """Same metric/unit pairs and plausible ranges as the wearable_samples CHECKs (M6), episodes included."""
    import random
    allowed = {"heart_rate": ("bpm", 25, 250), "hrv_rmssd": ("ms", 1, 300), "spo2": ("percent", 50, 100),
               "skin_temperature": ("celsius", 20, 45)}
    rng = random.Random(0)
    for conditions in ((), ("copd",), ("obstructive_sleep_apnea",), ("atrial_fibrillation", "diabetes")):
        rp = simulate.ring_profile(rng, conditions)
        for episode in (None, *simulate.RING_EPISODES):
            for metric, value, unit, minute in simulate.ring_day_samples(rng, rp, effect=25.0, episode=episode):
                u, lo, hi = allowed[metric]
                assert unit == u and lo <= value <= hi and 0 <= minute < 1440
    assert len(simulate.wearable_rows()) == len(simulate.WEARABLE_KEYS) * simulate.SEED_RING_DAYS * 62


def test_live_situations_pass_the_table_checks():
    """Minute-level live nights (pulse_data.live_sim) use the wearable_samples metric/unit pairs and ranges."""
    import random
    from pulse_data import live_sim
    allowed = {"heart_rate": ("bpm", 25, 250), "hrv_rmssd": ("ms", 1, 300), "spo2": ("percent", 50, 100),
               "skin_temperature": ("celsius", 20, 45)}
    for situation in live_sim.SITUATIONS:
        samples, truth = live_sim.night(random.Random(situation), situation)
        assert truth["situation"] == situation and len(samples) == live_sim.NIGHT_MINUTES * 2 + 72 * 2
        for metric, value, unit, minute in samples:
            u, lo, hi = allowed[metric]
            assert unit == u and lo <= value <= hi and 0 <= minute < live_sim.NIGHT_MINUTES
        if situation in ("oxygen_falling", "heart_rate_climbing", "fever_starting"):
            assert truth["onset"] is not None and truth["metric"]


def test_cloud_ring_refresh_only_touches_simulated_demo_rings():
    script = simulate.cloud_ring_demo_sql()
    deletes = [line for line in script.splitlines() if line.startswith("delete")]
    assert script.startswith("--") and "do $ring_demo$ begin" in script and script.endswith("end $ring_demo$;\n")
    assert deletes == [deletes[0]] and "source = 'simulated'" in deletes[0] and "public.wearable_samples" in deletes[0]
    assert all(simulate.demo_id(k + ":ring") in deletes[0] for k in simulate.WEARABLE_KEYS)
    assert "insert into public.measurements" not in script and "on conflict (id) do nothing" in script
    parts = simulate.cloud_ring_demo_parts()
    assert sum(p.count("'simulated', 'sim-ring-") for p in parts) == script.count("'simulated', 'sim-ring-")
    assert "delete from" in parts[0] and not any("delete from" in p for p in parts[1:])   # delete only in part 1
    assert all("do nothing" in p and p.rstrip().endswith("end $ring_demo$;") for p in parts)


def test_chronic_conditions_shape_the_ring_values():
    import random
    import statistics
    def nights(conditions, n=60):
        rng = random.Random(1)
        rp = simulate.ring_profile(random.Random(2), conditions)
        days = [simulate.ring_day_samples(rng, rp, 0.0) for _ in range(n)]
        return [[v for m, v, _, _ in d if m == "spo2"] for d in days], rp
    healthy, rp = nights(())
    copd, rp_copd = nights(("copd",))
    osa, _ = nights(("obstructive_sleep_apnea",))
    assert rp_copd.spo2 == rp.spo2 - 4                          # COPD: lower personal SpO2, same person otherwise
    dips = lambda ns, base: statistics.mean(sum(v < base - 4 for v in n) for n in ns)  # noqa: E731
    assert dips(osa, rp.spo2) >= 2 > dips(healthy, rp.spo2)     # sleep apnea: repeated >= 4 % desaturations
    assert simulate.ring_profile(random.Random(2), ("diabetes",)).hrv < rp.hrv   # lower HRV with diabetes


def test_seed_bp_readings_unchanged(monkeypatch):
    monkeypatch.setattr(simulate, "date", FixedDate)
    block = re.search(r"insert into public\.measurements .*?;\n\n", simulate.build_seed_sql("test-only"), flags=re.S)
    assert sha(block.group(0).encode()) == FINGERPRINTS["seed_measurements"]
