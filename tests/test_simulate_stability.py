"""Guard [review H3]: ring simulation must not change the blood-pressure data that mbp-v1 and the demo use.

Fingerprints taken on 30 Oct 2026, before any ring change. If one of these fails, BP data changed:
bump GENERATOR_VERSION, retrain mbp-v1 and update the fingerprints deliberately.
"""
import hashlib
import re
from datetime import date

from pulse_data import simulate

FINGERPRINTS = {
    "readings.csv": "5f16e5d9a5f57675e4b9767729a6e07cc095370ab0cfb8106941fed89cc4c734",
    "daily_context.csv": "9e330b0f3a62699211da9ad8c4abbc0fd451947b8a33d4f4590f214ed850a835",
    "seed_without_wearable_samples": "687e5615367a397d2aa1fbce5fb9f5efb14c070eec56115ccb2d18c6a0de8453",
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


def test_ring_samples_pass_the_table_checks():
    """Same metric/unit pairs and plausible ranges as the wearable_samples CHECKs (M6), episodes included."""
    import random
    allowed = {"heart_rate": ("bpm", 25, 250), "hrv_rmssd": ("ms", 1, 300), "spo2": ("percent", 50, 100),
               "skin_temperature": ("celsius", 20, 45)}
    rng = random.Random(0)
    rp = simulate.ring_profile(rng)
    for episode in (None, *simulate.RING_EPISODES):
        for metric, value, unit, minute in simulate.ring_day_samples(rng, rp, effect=25.0, episode=episode):
            u, lo, hi = allowed[metric]
            assert unit == u and lo <= value <= hi and 0 <= minute < 1440
    assert len(simulate.wearable_rows()) == len(simulate.WEARABLE_KEYS) * simulate.SEED_RING_DAYS * 62


def test_seed_unchanged_except_ring_samples(monkeypatch):
    monkeypatch.setattr(simulate, "date", FixedDate)
    sql = re.sub(r"insert into public\.wearable_samples .*?;\n\n", "", simulate.build_seed_sql("test-only"), flags=re.S)
    assert sha(sql.encode()) == FINGERPRINTS["seed_without_wearable_samples"]
