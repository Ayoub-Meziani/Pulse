"""wrisk-v1: trained on REAL people (NHANES 2017-March 2020). P(BP uncontrolled despite treatment).

    cd ml && ..\\.venv\\Scripts\\python -m pulse_ml.wrisk

Population: adults (18+) who report taking prescribed BP medicine now (BPQ050A) and have >= 2 valid exam
readings. Label: mean exam BP >= 140/90, systolic OR diastolic (sensitivity analysis: 130/80).
Features: only what PULSE stores (age, sex, BMI, waist, smoking, diabetes, high cholesterol, kidney disease,
COPD, heart failure, stroke). Survey weights are used as sample weights; metrics are reported weighted and
unweighted on held-out people. US population and office-type BP: NOT validated for Algerian patients.
Advisory context for the doctor only; never an alert, never a treatment suggestion.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .classify import scores
from .real_data import SOURCES, load_nhanes, valid_mean
from .train import ARTIFACTS, SEED, split_patients

MODEL_VERSION = "wrisk-v1"
FEATURES = ["age", "female", "bmi", "waist", "smoking_current", "smoking_former", "diabetes", "high_cholesterol",
            "kidney_disease", "copd", "heart_failure", "stroke"]
# PULSE condition_codes -> feature (same meaning as the NHANES "ever told by a doctor" questions)
CONDITION_FEATURE = {"diabetes": "diabetes", "dyslipidemia": "high_cholesterol",
                     "chronic_kidney_disease": "kidney_disease", "copd": "copd", "heart_failure": "heart_failure",
                     "stroke_history": "stroke"}


def nhanes_examples(df: pd.DataFrame, threshold=(140, 90)) -> pd.DataFrame:
    df = df.assign(systolic=valid_mean(df, "sys", 50, 300), diastolic=valid_mean(df, "dia", 25, 200))
    t = df[(df.age >= 18) & (df.bp_med_now == 1) & df.systolic.notna() & df.diastolic.notna() & (df.weight > 0)]
    return pd.DataFrame({
        "person": t.seqn.astype(int).astype(str), "weight": t.weight,
        "age": t.age, "female": t.female, "bmi": t.bmi, "waist": t.waist,
        "smoking_current": (t.smoking == "current").astype(float).where(t.smoking.notna()),
        "smoking_former": (t.smoking == "former").astype(float).where(t.smoking.notna()),
        "diabetes": t.diabetes_told, "high_cholesterol": t.high_chol_told, "kidney_disease": t.kidney_told,
        "copd": t.copd_told, "heart_failure": t.chf_told, "stroke": t.stroke_told,
        "label": ((t.systolic >= threshold[0]) | (t.diastolic >= threshold[1])).astype(int),
    })


def pulse_patient_features(age: float | None, sex: str | None, bmi: float | None, waist: float | None,
                           smoking: str | None, condition_codes) -> dict:
    """A PULSE patient as one wrisk-v1 row (NaN where unknown; the pipeline imputes)."""
    codes = set(condition_codes or ())
    f = {"age": age, "female": None if sex is None else float(sex == "female"), "bmi": bmi, "waist": waist,
         "smoking_current": None if smoking is None else float(smoking == "current"),
         "smoking_former": None if smoking is None else float(smoking == "former")}
    f.update({feat: float(code in codes) for code, feat in CONDITION_FEATURE.items()})
    return {k: (np.nan if v is None else float(v)) for k, v in f.items()}


def candidates() -> dict:
    return {"logistic_regression": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                                 LogisticRegression(max_iter=2000)),
            "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                                     random_state=SEED)}


def _fit(model, X, y, w):
    key = "logisticregression__sample_weight" if hasattr(model, "steps") else "sample_weight"
    return model.fit(X, y, **{key: w / w.mean()})


def calibration(prob: np.ndarray, y: np.ndarray, bins: int = 5) -> list[dict]:
    edges = np.quantile(prob, np.linspace(0, 1, bins + 1))
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (prob >= lo) & (prob <= hi)
        out.append({"predicted_mean": round(float(prob[m].mean()), 3), "observed_rate": round(float(y[m].mean()), 3),
                    "n": int(m.sum())})
    return out


def fit_and_evaluate(ex: pd.DataFrame, sensitivity: pd.DataFrame | None = None):
    split = split_patients(ex.person)
    part = {k: ex[ex.person.isin(v)] for k, v in split.items()}
    val_auc, fitted = {}, {}
    for name, model in candidates().items():
        fitted[name] = _fit(model, part["train"][FEATURES], part["train"].label, part["train"].weight)
        p = model.predict_proba(part["val"][FEATURES])[:, 1]
        val_auc[name] = round(float(roc_auc_score(part["val"].label, p, sample_weight=part["val"].weight)), 4)
    best = max(val_auc, key=val_auc.get)
    model, test = fitted[best], part["test"]
    y, w, pts = test.label.to_numpy(), test.weight.to_numpy(), test.person.to_numpy()
    prob = model.predict_proba(test[FEATURES])[:, 1]
    agesex = _fit(candidates()["logistic_regression"], part["train"][["age", "female"]], part["train"].label,
                  part["train"].weight).predict_proba(test[["age", "female"]])[:, 1]
    meta = {
        "model_version": MODEL_VERSION, "algorithm": best, "features": FEATURES,
        "trained_on": f"real:nhanes ({SOURCES['nhanes']['name']})", "credit": SOURCES["nhanes"]["credit"],
        "terms": SOURCES["nhanes"]["licence"],
        "population": "US adults 18+ taking prescribed BP medicine, >= 2 valid exam readings",
        "label": "mean exam BP >= 140/90 (systolic OR diastolic) = uncontrolled",
        "split": {"method": "person-level 70/15/15", "seed": SEED, **{f"{k}_people": len(v) for k, v in part.items()},
                  "test_uncontrolled_rate_weighted": round(float(np.average(y, weights=w)), 3)},
        "validation_auroc_weighted": val_auc,
        "test": {"model": {**scores(prob, y, pts),
                           "auroc_weighted": round(float(roc_auc_score(y, prob, sample_weight=w)), 3),
                           "calibration_quintiles": calibration(prob, y)},
                 "baseline_age_sex": {**scores(agesex, y, pts),
                                      "auroc_weighted": round(float(roc_auc_score(y, agesex, sample_weight=w)), 3)}},
        "limitations": "US population (not Algerian); office-type exam BP (not home BP); self-reported diagnoses; "
                       "cross-sectional (one visit): an association with control, not a forecast. Advisory only.",
    }
    if best == "logistic_regression":
        lr = model.steps[-1][1]
        scale = model.steps[1][1].scale_
        meta["odds_ratio_per_unit"] = {f: round(float(np.exp(c / s)), 3) for f, c, s in zip(FEATURES, lr.coef_[0], scale)}
    if sensitivity is not None:
        s_part = sensitivity[sensitivity.person.isin(split["test"])]
        s_model = _fit(candidates()[best], sensitivity[sensitivity.person.isin(split["train"])][FEATURES],
                       sensitivity[sensitivity.person.isin(split["train"])].label,
                       sensitivity[sensitivity.person.isin(split["train"])].weight)
        meta["sensitivity_130_80"] = {
            "test_auroc_weighted": round(float(roc_auc_score(s_part.label, s_model.predict_proba(s_part[FEATURES])[:, 1],
                                                             sample_weight=s_part.weight)), 3),
            "uncontrolled_rate_weighted": round(float(np.average(s_part.label, weights=s_part.weight)), 3)}
    return {"model": model, "features": FEATURES}, meta


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    df = load_nhanes()
    bundle, meta = fit_and_evaluate(nhanes_examples(df), nhanes_examples(df, (130, 80)))
    meta["trained_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = ARTIFACTS / MODEL_VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out / "model.joblib")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    t = meta["test"]
    print(json.dumps({"algorithm": meta["algorithm"], "split": meta["split"], "validation": meta["validation_auroc_weighted"],
                      "test_model": {k: t["model"][k] for k in ("auroc", "auroc_ci95", "auroc_weighted", "brier",
                                                                "balanced_accuracy")},
                      "test_age_sex_baseline": {k: t["baseline_age_sex"][k] for k in ("auroc", "auroc_weighted", "brier")},
                      "calibration": t["model"]["calibration_quintiles"], "sensitivity_130_80": meta.get("sensitivity_130_80"),
                      "odds_ratios": meta.get("odds_ratio_per_unit")}, indent=2))


if __name__ == "__main__":
    main()
