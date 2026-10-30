"""Train live-v1 and test it minute by minute on UNSEEN nights (all synthetic, labelled).

    ..\\.venv\\Scripts\\python -m pulse_data.live_sim --out data/live/train --nights 700 --seed 11      (repo root)
    ..\\.venv\\Scripts\\python -m pulse_data.live_sim --out data/live/test --nights 700 --seed 2027
    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.live_test

Train (seed 11): forecasts of HR / SpO2 / skin temperature at +10 and +20 minutes (ridge on the past-only features
of live.py) and P(restless night) at the 30-minute checkpoints (logistic regression).
Test (seed 2027: other people, other nights): every night goes through the engine. Per situation: caught or not,
minutes of warning before the limit was really crossed (lead time), the existing "limit crossed now" rule (median of
the 10-minute window so far) for comparison, warnings on nights with nothing planted, forecast error vs "same as now"
and a straight-line trend, restless-night accuracy by hour, and the engine's time per new minute (a real
minute-by-minute replay, which must give exactly the same warnings). -> artifacts/live-v1/
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import live
from .train import ARTIFACTS, ROOT

LIVE_DATA = ROOT / "data" / "live"
PERSONAL = ("heart_rate", "spo2", "hrv_rmssd", "skin_temperature")
CROSSING = ("oxygen_falling", "heart_rate_climbing", "fever_starting")
QUIET_SITUATIONS = ("normal_night", "false_alarm_traps", "bad_sleep")


def load(split: str):
    s = pd.read_csv(LIVE_DATA / split / "samples.csv")
    if not (s.is_synthetic.astype(str).str.lower() == "true").all():
        raise SystemExit("refusing: live data contains rows not labelled synthetic")
    nights = pd.read_csv(LIVE_DATA / split / "nights.csv", keep_default_na=False).set_index("night_id")
    tables = {nid: live.table(g[["minute", "metric", "value"]]) for nid, g in s.groupby("night_id")}
    return tables, nights


def ctx_of(row) -> live.Context:
    return live.Context(personal={m: float(row[f"prev_{m}"]) for m in PERSONAL},
                        conditions=tuple(c for c in str(row.conditions).split(";") if c))


THRESHOLDS = [round(x, 2) for x in np.arange(0.30, 0.96, 0.05)]
MAX_FALSE_PER_NIGHT = 0.05          # per metric, on held-out training nights: chooses each warning threshold


def crossing_label(f: pd.DataFrame, row, metric: str) -> pd.Series:
    """1 while a real deterioration of this metric is under way and the limit will be crossed within 20 minutes."""
    if row.metric != metric or row.crossing == "":
        return pd.Series(0, index=f.index)
    m = np.asarray(f.index)
    c, o = int(row.crossing), int(row.onset)
    return pd.Series(((m >= o) & (m < c) & (c - m <= live.WARN_WITHIN)).astype(int), index=f.index)


def fit(tables, nights) -> dict:
    ids = sorted(tables)
    np.random.default_rng(7).shuffle(ids)
    fit_ids, val_ids = ids[: int(0.8 * len(ids))], ids[int(0.8 * len(ids)):]
    forecast, warn = {}, {}
    for metric in live.METRICS:
        parts = []
        for nid in fit_ids:
            row = nights.loc[nid]
            f = live.warn_frame(tables[nid], metric, ctx_of(row))
            if f is None:
                continue
            f = f.assign(y_cross=crossing_label(f, row, metric),
                         **{f"y{h}": f["last"].shift(-h) - f["last"] for h in live.HORIZONS})
            parts.append(f.iloc[::2])
        d = pd.concat(parts)
        for h in live.HORIZONS:
            ok = d[live.FEATURES + [f"y{h}"]].notna().all(axis=1)
            forecast[(metric, h)] = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=7).fit(
                d.loc[ok, live.FEATURES], d.loc[ok, f"y{h}"])
        ok = d[live.WARN_FEATURES].notna().all(axis=1) & (d["margin"] > 0)
        warn[metric] = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=7).fit(
            d.loc[ok, live.WARN_FEATURES], d.loc[ok, "y_cross"])
    bundle = {"forecast": forecast, "warn": warn, "threshold": {}, "features": live.FEATURES,
              "warn_features": live.WARN_FEATURES}
    bundle["threshold"], bundle["threshold_selection"] = choose_thresholds(tables, nights, val_ids, bundle)
    rows = [{**live.sleep_features(t.iloc[:c + 1], ctx_of(nights.loc[nid])), "y": int(nights.loc[nid].restless)}
            for nid in fit_ids for t in [tables[nid]] for c in range(live.SLEEP_FROM, 360, live.SLEEP_EVERY)]
    sd = pd.DataFrame(rows)
    bundle["sleep"] = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(sd[live.SLEEP_FEATURES], sd.y)
    bundle["sleep_features"] = live.SLEEP_FEATURES
    bundle["split"] = {"fit_nights": len(fit_ids), "threshold_nights": len(val_ids)}
    return bundle


def _rule(cand: np.ndarray) -> list[int]:
    """The live rule on one night: candidate 2 minutes in a row, then quiet for 30 minutes."""
    out, last = [], -10 ** 9
    for i in range(1, len(cand)):
        if cand[i] and cand[i - 1] and i - last >= live.QUIET_MINUTES:
            out.append(i)
            last = i
    return out


def choose_thresholds(tables, nights, val_ids, bundle) -> tuple[dict, dict]:
    """Per metric, on held-out TRAINING nights: the threshold with the most deteriorations warned before the limit
    is crossed, keeping false warnings <= 0.05 per night (else the threshold with the fewest); on a tie, the
    stricter (higher) threshold."""
    chosen, report = {}, {}
    for metric in live.METRICS:
        nights_p = []
        for nid in val_ids:
            row = nights.loc[nid]
            f = live.warn_frame(tables[nid], metric, ctx_of(row))
            if f is None:
                continue
            ok = (f[live.WARN_FEATURES].notna().all(axis=1) & (f["margin"] > 0)).to_numpy()
            p = np.zeros(len(f))
            if ok.any():
                p[ok] = bundle["warn"][metric].predict_proba(f.loc[ok, live.WARN_FEATURES])[:, 1]
            nights_p.append((row, np.asarray(f.index), p))
        grid = []
        for th in THRESHOLDS:
            hits = crossed = false = 0
            for row, minutes, p in nights_p:
                warns = [minutes[i] for i in _rule(p >= th)]
                mine = row.metric == metric and row.crossing != ""
                if mine:
                    crossed += 1
                    hits += any(int(row.onset) <= w < int(row.crossing) for w in warns)
                false += sum(not (mine and w >= int(row.onset)) for w in warns)
            grid.append({"threshold": th, "warned_before_crossing": round(hits / max(crossed, 1), 3),
                         "false_per_night": round(false / max(len(nights_p), 1), 3)})
        ok = [g for g in grid if g["false_per_night"] <= MAX_FALSE_PER_NIGHT]
        best = max(ok, key=lambda g: (g["warned_before_crossing"], g["threshold"])) if ok else \
            min(grid, key=lambda g: g["false_per_night"])
        chosen[metric] = best["threshold"]
        report[metric] = {"chosen": best, "grid": grid}
    return chosen, report


def now_rule_minute(t: pd.DataFrame, metric: str, ctx: live.Context, start: int = 0) -> int | None:
    """The existing live rule (ring.live_flags): median of the 10-minute window so far (>= 2 samples) past the
    reference. Returns the first minute >= start when it fires."""
    lim = live.limit_for(metric, ctx)
    if lim is None or metric == "skin_temperature":
        return None
    s = t[metric]
    so_far = s.groupby(np.asarray(t.index) // 10).expanding(min_periods=2).median().droplevel(0)
    hit = so_far[(so_far < lim[1]) if lim[0] == "low" else (so_far > lim[1])]
    hit = hit[hit.index >= start]
    return int(hit.index[0]) if len(hit) else None


def evaluate(tables, nights, bundle) -> dict:
    per_night = []
    for nid, t in tables.items():
        row, ctx = nights.loc[nid], ctx_of(nights.loc[nid])
        warns = live.night_warnings(t, ctx, bundle)
        sit, onset = row.situation, int(row.onset) if row.onset != "" else None
        crossing = int(row.crossing) if row.crossing != "" else None
        rec = {"night": nid, "situation": sit, "warnings": len(warns),
               "spo2_warnings": sum(w["metric"] == "spo2" for w in warns)}
        if sit in CROSSING:
            m = row.metric
            mine = [w["window_start"] for w in warns if w["metric"] == m and w["window_start"] >= onset]
            first = min(mine) if mine else None
            now = now_rule_minute(t, m, ctx, onset)
            rec.update(metric=m, crossed=crossing is not None, first_warning=first, crossing=crossing, now_rule=now,
                       early=first is not None and crossing is not None and first < crossing,
                       lead=crossing - first if first is not None and crossing is not None and first < crossing else None,
                       unrelated=len(warns) - len(mine))
        if sit == "sleep_apnea":
            rec["apnea_flagged"] = rec["spo2_warnings"] > 0 or now_rule_minute(t, "spo2", ctx) is not None
        probs = {c: live.sleep_risk(t.iloc[:c + 1], ctx, bundle) for c in range(live.SLEEP_FROM, 360, live.SLEEP_EVERY)}
        warned = [c for c, p in probs.items() if p >= live.SLEEP_P]
        rec.update(restless=int(row.restless), sleep_warned=bool(warned), sleep_first=warned[0] if warned else None,
                   **{f"p{c}": p for c, p in probs.items()})
        per_night.append(rec)
    df = pd.DataFrame(per_night)

    situations = {}
    for sit, g in df.groupby("situation"):
        s = {"nights": len(g), "early_warnings_per_night": round(float(g.warnings.mean()), 2),
             "nights_with_any_early_warning": round(float((g.warnings > 0).mean()), 3)}
        if sit in CROSSING:
            c = g[g.crossed]
            caught = c.early | (c.now_rule.notna() & ((c.now_rule - c.crossing) <= 30))
            s.update(metric=g.metric.iat[0], crossed_limit=len(c),
                     warned_before_crossing=round(float(c.early.mean()), 3),
                     lead_minutes_median=float(c.lead.median()) if c.early.any() else None,
                     lead_minutes_iqr=[float(c.lead.quantile(q)) for q in (0.25, 0.75)] if c.early.any() else None,
                     caught_early_or_within_30_min=round(float(caught.mean()), 3),
                     now_rule_minutes_after_crossing_median=(float((c.now_rule - c.crossing).median())
                                                             if c.now_rule.notna().any() else None),
                     unrelated_warnings_per_night=round(float(g.unrelated.mean()), 2))
        if sit == "sleep_apnea":
            s["nights_flagged_low_oxygen"] = round(float(g.apnea_flagged.mean()), 3)
        s["restless_warning_share"] = round(float(g.sleep_warned.mean()), 3)
        situations[sit] = s

    sleep = {}
    for c in (60, 120, 180):
        y, p = df.restless.to_numpy(), df[f"p{c}"].to_numpy()
        sleep[f"{c // 60 + 0:02d}:00"] = {"auroc": round(float(roc_auc_score(y, p)), 3),
                                          "accuracy_at_0.5": round(float(accuracy_score(y, p >= 0.5)), 3)}
    bad = df[df.situation == "bad_sleep"]
    sleep["restless_nights_warned"] = round(float(bad.sleep_warned.mean()), 3)
    sleep["first_warning_time_median"] = (f"{int(bad.sleep_first.median()) // 60:02d}:{int(bad.sleep_first.median()) % 60:02d}"
                                          if bad.sleep_warned.any() else None)
    sleep["other_nights_warned"] = round(float(df[df.situation != "bad_sleep"].sleep_warned.mean()), 3)
    return {"situations": situations, "sleep": sleep, "per_night": df}


def forecast_accuracy(tables, nights, bundle) -> dict:
    out = {}
    for metric in live.METRICS:
        err = {h: {"live-v1": [], "same_as_now": [], "straight_line_trend": []} for h in live.HORIZONS}
        for nid, t in tables.items():
            f = live.feature_frame(t[metric], ctx_of(nights.loc[nid]).personal.get(metric))
            for h in live.HORIZONS:
                y = f["last"].shift(-h)
                ok = (f[live.FEATURES + ["last"]].notna().all(axis=1) & y.notna()).to_numpy()
                if not ok.any():
                    continue
                last, yy = f["last"].to_numpy()[ok], y.to_numpy()[ok]
                pred = last + bundle["forecast"][(metric, h)].predict(f.loc[ok, live.FEATURES])
                err[h]["live-v1"].append(np.abs(pred - yy))
                err[h]["same_as_now"].append(np.abs(last - yy))
                err[h]["straight_line_trend"].append(np.abs(last + f["slope10"].to_numpy()[ok] * h - yy))
        out[metric] = {f"+{h} min": {k: round(float(np.concatenate(v).mean()), 3) for k, v in e.items()}
                       for h, e in err.items()}
    return out


def replay_check(tables, nights, bundle, n: int = 20) -> dict:
    """The live way: feed one minute at a time (last 60 minutes only), as monitor --follow does. Must equal the
    whole-night result, and shows the time per new minute."""
    ids = list(nights[nights.situation == "oxygen_falling"].index[:n])
    same, times = True, []
    for nid in ids:
        t, ctx = tables[nid], ctx_of(nights.loc[nid])
        expected = [(w["metric"], w["window_start"]) for w in live.night_warnings(t, ctx, bundle)]
        got, last = [], {}
        for i in range(len(t)):
            t0 = time.perf_counter()
            for w in live.latest_warnings(t.iloc[max(0, i - live.HISTORY_MINUTES + 1): i + 1], ctx, bundle, last):
                got.append((w["metric"], w["window_start"]))
                last[w["metric"]] = w["window_start"]
            times.append((time.perf_counter() - t0) * 1000)
        same &= sorted(got) == sorted(expected)
    return {"nights": len(ids), "minutes": len(times), "same_warnings_as_whole_night": bool(same),
            "ms_per_new_minute_mean": round(float(np.mean(times)), 2),
            "ms_per_new_minute_p95": round(float(np.percentile(times, 95)), 2)}


def example(per_night: pd.DataFrame, tables, nights) -> dict:
    """One oxygen_falling night with an early warning near the median lead time (for the report chart)."""
    c = per_night[(per_night.situation == "oxygen_falling") & per_night.early]
    r = c.iloc[(c.lead - c.lead.median()).abs().argsort().iloc[0]]
    t, row = tables[r.night], nights.loc[r.night]
    s3 = t["spo2"].rolling(3, min_periods=2).median()
    return {"night": r.night, "conditions": row.conditions, "limit": float(row.limit_spo2), "onset": int(row.onset),
            "warning_minute": int(r.first_warning), "crossing": int(r.crossing),
            "now_rule_minute": None if pd.isna(r.now_rule) else int(r.now_rule),
            "spo2_3min_median": [None if pd.isna(v) else round(float(v), 2) for v in s3.to_numpy()]}


def main() -> None:
    train_t, train_n = load("train")
    test_t, test_n = load("test")
    bundle = fit(train_t, train_n)
    ev = evaluate(test_t, test_n, bundle)
    meta = {
        "model_version": live.MODEL_VERSION,
        "trained_on": "synthetic:live_sim seed 11 (minute-level ring nights)", "tested_on": "synthetic:live_sim seed 2027",
        "validation": "SIMULATOR-ONLY: every figure comes from 700 + 700 simulated nights; not real-world or clinical "
                      "validation",
        "clinician_review": "pending for every threshold and parameter (ml/MODEL_CARD.md, Pending clinician review)",
        "train_nights": len(train_t), "test_nights": len(test_t),
        "test_situations": test_n.situation.value_counts().to_dict(),
        "forecast": {"metrics": list(live.METRICS), "horizons_min": list(live.HORIZONS), "features": live.FEATURES,
                     "model": "gradient boosting on past-only features, predicts the change from now"},
        "early_warning_rule": f"value still inside its limit and P(limit crossed within {live.WARN_WITHIN} min) >= the "
                              "metric's threshold, 2 minutes in a row; at most 1 per metric per "
                              f"{live.QUIET_MINUTES} min (gradient-boosting classifier)",
        "thresholds": bundle["threshold"], "split": bundle["split"],
        "threshold_selection": {m: v["chosen"] for m, v in bundle["threshold_selection"].items()},
        "limits": "SpO2 94 % (COPD 88 %), resting HR 100 bpm (or the doctor's live band), skin temperature "
                  f"personal normal + {live.FEVER_RISE} C",
        "situations": ev["situations"], "restless_night": ev["sleep"],
        "forecast_mae": forecast_accuracy(test_t, test_n, bundle),
        "replay_minute_by_minute": replay_check(test_t, test_n, bundle),
        "example_oxygen_falling": example(ev["per_night"], test_t, test_n),
        "limitations": "Synthetic minute-level nights: slopes, wake-up bouts and artefacts are assumptions; no real "
                       "minute-level ring data exists for the team. Advisory for the doctor only; never an alert.",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out = ARTIFACTS / live.MODEL_VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out / "model.joblib")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("situations", "restless_night", "forecast_mae", "replay_minute_by_minute")},
                     indent=2))


if __name__ == "__main__":
    main()
