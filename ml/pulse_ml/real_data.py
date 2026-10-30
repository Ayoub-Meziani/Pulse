"""REAL public datasets: download into git-ignored data/external/<source>/ (+ MANIFEST.json) and load them.

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.real_data fetch [nhanes|mendeley_hbpm|apnea_ecg|all]

Terms, respected by every user of this module:
- nhanes: NCHS data user agreement. Statistical reporting and analysis only; no attempt to identify anyone;
  no linkage with identifiable data. Only aggregated statistics and trained models leave data/external/.
- mendeley_hbpm: CC BY-NC 3.0. Non-commercial use, credit the authors. Not redistributed.
- apnea_ecg: Open Data Commons Attribution 1.0 (PhysioNet). Credit the authors.
Raw files are never committed or uploaded. Everything derived is labelled real:<source>.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .train import ROOT

EXTERNAL = ROOT / "data" / "external"
UA = {"User-Agent": "PULSE-hackathon-research/0.1 (non-commercial)"}
NHANES_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/"
NHANES_FILES = ("P_DEMO", "P_BPXO", "P_BMX", "P_SMQ", "P_DIQ", "P_BPQ", "P_TCHOL", "P_MCQ", "P_KIQ_U")
APNEA_BASE = "https://physionet.org/files/apnea-ecg/1.0.0/"
APNEA_RECORDS = ("a01r", "a02r", "a03r", "a04r", "b01r", "c01r", "c02r", "c03r")   # the 8 records with SpO2
MENDELEY_API = "https://data.mendeley.com/public-api/datasets/pjcv33hpp7/files?folder_id=root&version=1"

SOURCES = {
    "nhanes": {
        "name": "NHANES 2017-March 2020 pre-pandemic (CDC / NCHS)",
        "licence": "NCHS data user agreement: statistical analysis only; no re-identification; no linkage "
                   "(https://www.cdc.gov/nchs/data_access/restrictions.htm)",
        "credit": "National Center for Health Statistics, NHANES 2017-March 2020 pre-pandemic data files",
    },
    "mendeley_hbpm": {
        "name": "Data for: Trends and seasonality extracting from Home Blood Pressure Monitoring readings",
        "licence": "CC BY-NC 3.0 (non-commercial, attribution)",
        "credit": "Dvornik O, Chuiko G, Baganov Y, Shyian I (2017), Mendeley Data v1, doi:10.17632/pjcv33hpp7.1",
    },
    "apnea_ecg": {
        "name": "Apnea-ECG Database 1.0.0 (PhysioNet)",
        "licence": "Open Data Commons Attribution License v1.0",
        "credit": "Penzel T, Moody GB, Mark RG, Goldberger AL, Peter JH. The Apnea-ECG Database. "
                  "Computers in Cardiology 2000;27:255-258; Goldberger AL et al. PhysioNet, Circulation 2000",
    },
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        return r.read()


def _save(source: str, items: list[tuple[str, str, str | None]]) -> dict:
    """items: (file name, url, expected sha256 or None). Keeps existing files; refuses changed content."""
    folder = EXTERNAL / source
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        **SOURCES[source], "files": {}}
    new = 0
    for name, url, expected in items:
        path = folder / name
        if path.exists():
            have = _sha256(path.read_bytes())
            known = manifest["files"].get(name, {}).get("sha256")
            if known and known != have:
                raise SystemExit(f"{source}/{name} changed on disk since download; refusing to continue")
            manifest["files"].setdefault(name, {"url": url, "sha256": have, "bytes": path.stat().st_size,
                                                "downloaded_at": None})
            continue
        data = _get(url)
        digest = _sha256(data)
        if expected and expected != digest:
            raise SystemExit(f"{source}/{name}: sha256 does not match the publisher's value")
        path.write_bytes(data)
        manifest["files"][name] = {"url": url, "sha256": digest, "bytes": len(data),
                                   "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        new += 1
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"source": source, "files": len(items), "downloaded": new}


def fetch(source: str) -> dict:
    if source == "nhanes":
        return _save(source, [(f"{n}.xpt", f"{NHANES_BASE}{n}.xpt", None) for n in NHANES_FILES])
    if source == "mendeley_hbpm":
        files = json.loads(_get(MENDELEY_API))
        return _save(source, [(f["filename"], f["content_details"]["download_url"], f["content_details"]["sha256_hash"])
                              for f in files])
    if source == "apnea_ecg":
        return _save(source, [(f"{r}.{ext}", f"{APNEA_BASE}{r}.{ext}", None)
                              for r in APNEA_RECORDS for ext in ("hea", "dat")])
    raise SystemExit(f"unknown source {source}")


# ---------------------------------------------------------------- loaders (tidy, documented columns)

def _xpt(name: str) -> pd.DataFrame:
    path = EXTERNAL / "nhanes" / f"{name}.xpt"
    if not path.exists():
        raise SystemExit("NHANES not downloaded: python -m pulse_ml.real_data fetch nhanes")
    return pd.read_sas(path, format="xport", encoding="infer")


NHANES_COLUMNS = {  # NHANES variable -> PULSE name (checked against the CDC codebooks, 30 Oct 2026)
    "P_DEMO": {"SEQN": "seqn", "RIAGENDR": "sex_code", "RIDAGEYR": "age", "WTMECPRP": "weight"},
    "P_BPXO": {"SEQN": "seqn", **{f"BPXOSY{i}": f"sys{i}" for i in (1, 2, 3)},
               **{f"BPXODI{i}": f"dia{i}" for i in (1, 2, 3)}, **{f"BPXOPLS{i}": f"pulse{i}" for i in (1, 2, 3)}},
    "P_BMX": {"SEQN": "seqn", "BMXBMI": "bmi", "BMXWAIST": "waist"},
    "P_SMQ": {"SEQN": "seqn", "SMQ020": "smoked_100", "SMQ040": "smoke_now"},
    "P_DIQ": {"SEQN": "seqn", "DIQ010": "diabetes_told"},
    "P_BPQ": {"SEQN": "seqn", "BPQ020": "hbp_told", "BPQ050A": "bp_med_now", "BPQ080": "high_chol_told"},
    "P_MCQ": {"SEQN": "seqn", "MCQ160B": "chf_told", "MCQ160F": "stroke_told", "MCQ160P": "copd_told"},
    "P_KIQ_U": {"SEQN": "seqn", "KIQ022": "kidney_told"},
}


def load_nhanes() -> pd.DataFrame:
    """One row per examined participant. Yes/no answers become 1 / 0 (refused / don't know -> NaN)."""
    df = None
    for name, cols in NHANES_COLUMNS.items():
        raw = _xpt(name)
        missing = [c for c in cols if c not in raw.columns]
        if missing:
            raise SystemExit(f"{name}: expected NHANES variables missing {missing}; check the CDC codebook")
        part = raw[list(cols)].rename(columns=cols)
        df = part if df is None else df.merge(part, on="seqn", how="left")
    for c in ("diabetes_told", "hbp_told", "bp_med_now", "high_chol_told", "chf_told", "stroke_told", "copd_told",
              "kidney_told", "smoked_100"):
        df[c] = df[c].map({1.0: 1.0, 2.0: 0.0, 3.0: 0.0})   # DIQ010 3 = borderline -> not diagnosed
    df["female"] = (df.sex_code == 2).astype(float)
    df["smoking"] = np.select([df.smoked_100 == 0, df.smoke_now.isin([1.0, 2.0]), df.smoke_now == 3.0],
                              ["never", "current", "former"], default=None)
    return df


def valid_mean(df: pd.DataFrame, kind: str, low: float, high: float) -> pd.Series:
    """Mean of the valid readings of one kind (sys / dia / pulse); NaN unless >= 2 are valid."""
    vals = df[[f"{kind}{i}" for i in (1, 2, 3)]]
    vals = vals.where((vals >= low) & (vals <= high))
    if kind in ("sys", "dia"):
        ok = df[[f"sys{i}" for i in (1, 2, 3)]].to_numpy() > df[[f"dia{i}" for i in (1, 2, 3)]].to_numpy()
        vals = vals.where(ok)
    return vals.mean(axis=1).where(vals.notna().sum(axis=1) >= 2)


def load_mendeley() -> pd.DataFrame:
    folder = EXTERNAL / "mendeley_hbpm"
    if not folder.exists():
        raise SystemExit("Mendeley data not downloaded: python -m pulse_ml.real_data fetch mendeley_hbpm")
    col = lambda f: pd.read_excel(folder / f, header=None, engine="xlrd")[0]  # noqa: E731
    return mendeley_frame(col("Systolic_Blood_Pressure_data.xls"), col("Diastolic_Blood_Pressure_data.xls"),
                          col("Heart_Rate_data.xls"))


def mendeley_frame(sys_: pd.Series, dia: pd.Series, hr: pd.Series) -> pd.DataFrame:
    """The dataset has no dates: one measurement (mean of 3 trials) every 3 days over 384 days (its description)."""
    if not (len(sys_) == len(dia) == len(hr)):
        raise ValueError("Mendeley columns have different lengths")
    return pd.DataFrame({"day": np.arange(len(sys_)) * 3, "systolic": sys_.astype(float),
                         "diastolic": dia.astype(float), "pulse": hr.astype(float)})


def load_apnea_spo2(record: str) -> tuple[np.ndarray, float]:
    import wfdb
    rec = wfdb.rdrecord(str(EXTERNAL / "apnea_ecg" / record))
    idx = [i for i, n in enumerate(rec.sig_name) if n.lower().startswith("spo2")]
    if not idx:
        raise SystemExit(f"{record}: no SpO2 channel ({rec.sig_name})")
    return rec.p_signal[:, idx[0]].astype(float), float(rec.fs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["fetch"])
    ap.add_argument("source", choices=[*SOURCES, "all"])
    a = ap.parse_args()
    for s in SOURCES if a.source == "all" else [a.source]:
        print(json.dumps(fetch(s)))


if __name__ == "__main__":
    main()
