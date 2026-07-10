"""
taskC_common.py  —  shared utilities for the Task C counterfactual benchmark.

Task C predicts the counterfactual scalar outcome Y under the opposite treatment.
Treatment T is binary: PCI (T=1) vs conservative management / control (T=0). CABG
episodes are surgical revascularization, not PCI, and there are too few to match, so
they are excluded from the Task C cohort.

This module centralizes:
  - the candidate-outcome accessors (build_dataset.py wrote an `outcomes` block),
  - the pre-treatment covariate matrix X used by BOTH the outcome selector and the
    propensity/embedding matcher (so the two agree on what X is),
  - a propensity model P(T=1|X) with overlap diagnostics,
  - covariate-balance (SMD) helpers.

Imported by select_outcome.py, build_propensity_matches.py, and score_taskC.py.
"""

import json
import numpy as np
from pathlib import Path

# NOTE: encode_features (pulls in pandas) and sklearn are imported LAZILY inside the
# functions that need them, so this module can be imported by the GPU runner (torch-only
# env) without requiring the full scientific stack.

BENCH = Path(__file__).parent.parent
EPISODES = BENCH / "data" / "episodes.json"

# Candidate scalar outcomes (must match OUTCOME_SPECS keys in build_dataset.py).
CANDIDATE_OUTCOMES = [
    "peak_troponin_72h", "delta_creatinine_72h", "peak_lactate_72h", "peak_ckmb_72h",
]
PRIMARY_OUTCOME_DEFAULT = "peak_troponin_72h"

# Each outcome's underlying labevents label + a short human-readable name (used in the
# direction prompt + confidence scoring). Task C records both the numeric value AND the
# rising/falling/stable direction (with an activation-derived confidence) for these.
OUTCOME_MARKER_LABEL = {
    "peak_troponin_72h": "Troponin T",
    "peak_ckmb_72h": "Creatine Kinase, MB Isoenzyme",
    "peak_lactate_72h": "Lactate",
    "delta_creatinine_72h": "Creatinine",
}
OUTCOME_DISPLAY = {
    "peak_troponin_72h": "troponin",
    "peak_ckmb_72h": "CK-MB",
    "peak_lactate_72h": "lactate",
    "delta_creatinine_72h": "creatinine",
}
# Short JSON ids the model returns / predictions are keyed by (match run_taskC DESCRIPTORS).
OUTCOME_ID = {
    "peak_troponin_72h": "troponin",
    "peak_ckmb_72h": "ck_mb",
    "peak_lactate_72h": "lactate",
    "delta_creatinine_72h": "creatinine",
}
# Lower outcome value = better (less injury / less renal insult) for all lab outcomes.
LOWER_IS_BETTER = True
# A change of < this fraction of baseline counts as "stable".
DIRECTION_STABLE_REL = 0.15

# Fixed, documented clinical-relevance prior for criterion (c) of the selector.
# Troponin/creatinine = direct, interpretable peri-PCI outcomes; CK-MB redundant with
# troponin; lactate is a nonspecific global-perfusion marker, drawn selectively.
CLINICAL_RELEVANCE_PRIOR = {
    "peak_troponin_72h": 1.0,
    "delta_creatinine_72h": 0.9,
    "peak_ckmb_72h": 0.6,
    "peak_lactate_72h": 0.5,
}

# Key chemistry/CBC labs used as confounders (matched case-insensitively against the
# dataset's `label` strings; absent ones are imputed at the column median).
KEY_LABS = [
    "Creatinine", "Sodium", "Potassium", "Chloride", "Bicarbonate", "Anion Gap",
    "Urea Nitrogen", "Glucose", "Calcium", "Magnesium", "Hemoglobin", "Hematocrit",
    "Platelet Count", "White Blood Cells",
]

_DIR2NUM = {"rising": 1.0, "stable": 0.0, "falling": -1.0}


# ── episode / outcome accessors ─────────────────────────────────────────────
def load_episodes(path=EPISODES):
    data = json.loads(Path(path).read_text())
    return data, data["episodes"]


def taskC_cohort(episodes):
    """Task C cohort = PCI (treated) + control (untreated). Excludes CABG."""
    return [e for e in episodes if e["intervention"]["type"] in ("pci", "control")]


def treatment_of(ep):
    """T = 1 for PCI, 0 for control."""
    return 1 if ep["intervention"]["type"] == "pci" else 0


def outcome_value(ep, key):
    """Scalar outcome value or None if missing."""
    o = ep.get("outcomes", {}).get(key)
    if not o or o.get("missing", True):
        return None
    return o.get("value")


def outcome_present(ep, key):
    return outcome_value(ep, key) is not None


def marker_baseline(ep, key):
    """Pre-index baseline level of the outcome's underlying marker (for direction)."""
    label = OUTCOME_MARKER_LABEL.get(key)
    bs = ep.get("baseline_summary", {}).get(label)
    if bs and bs.get("last_pre_value") is not None:
        return float(bs["last_pre_value"])
    # delta outcomes store their own baseline; peaks of non-cardiac markers fall back to labs_all
    o = ep.get("outcomes", {}).get(key, {})
    if o.get("baseline") is not None:
        return float(o["baseline"])
    v = _lab_lookup(_latest_labs(ep), label) if label else None
    return float(v) if v is not None else None


def direction_from_value(value, key, baseline):
    """rising / falling / stable for an outcome value, relative to baseline (delta
    outcomes are already baseline-relative). Returns None if undecidable."""
    if value is None:
        return None
    if key.startswith("delta_"):
        scale = abs(baseline) if baseline else 1.0
        rel = value / scale if scale else value
    else:
        if baseline is None:
            return None
        rel = (value - baseline) / abs(baseline) if baseline else (value - baseline)
    if abs(rel) < DIRECTION_STABLE_REL:
        return "stable"
    return "rising" if rel > 0 else "falling"


def outcome_direction(ep, key):
    """Observed (factual) direction of the outcome for this episode."""
    return direction_from_value(outcome_value(ep, key), key, marker_baseline(ep, key))


# ── covariate matrix ────────────────────────────────────────────────────────
def _latest_labs(ep):
    """{lab_name: latest_value} from the pre-index labs_all summary."""
    labs = ep.get("clinical_context", {}).get("labs_all", {})
    return {name: s.get("latest") for name, s in labs.items() if s.get("latest") is not None}


def _lab_lookup(latest, name):
    """Case-insensitive exact-or-substring lookup of a lab's latest value."""
    if name in latest:
        return latest[name]
    nl = name.lower()
    for k, v in latest.items():
        if k.lower() == nl:
            return v
    for k, v in latest.items():
        if nl in k.lower():
            return v
    return None


def build_covariate_matrix(episodes):
    """Pre-treatment covariate matrix for the Task C cohort.

    Returns (X, feature_names, episode_ids, T) where X is (n, d) float with NaNs
    imputed at per-column medians. Features: comorbidity one-hot, troponin baseline
    level/slope/direction, n_comorbidities, SOFA-like severity, and KEY_LABS latest
    values. (Age/sex are absent from this dataset — a stated confounding limitation.)
    """
    from encode_features import compute_severity_score   # lazy (pulls pandas)
    cohort = taskC_cohort(episodes)
    comorbid_keys = sorted(cohort[0]["comorbidities"].keys()) if cohort else []
    feat_names = (
        [f"comorbid_{k}" for k in comorbid_keys]
        + ["n_comorbidities", "trop_baseline", "trop_slope", "trop_dir", "severity"]
        + [f"lab_{l}" for l in KEY_LABS]
    )
    rows, ids, T = [], [], []
    for ep in cohort:
        latest = _latest_labs(ep)
        bs = ep.get("baseline_summary", {}).get("Troponin T", {})
        row = [float(ep["comorbidities"][k]) for k in comorbid_keys]
        row += [
            float(ep.get("n_comorbidities", 0)),
            float(bs.get("last_pre_value", np.nan)),
            float(bs.get("slope_per_h", 0.0) or 0.0),
            _DIR2NUM.get(bs.get("direction", "stable"), 0.0),
            float(compute_severity_score(latest)),
        ]
        row += [(_lab_lookup(latest, l) if _lab_lookup(latest, l) is not None else np.nan)
                for l in KEY_LABS]
        rows.append([float(x) if x is not None else np.nan for x in row])
        ids.append(ep["episode_id"])
        T.append(treatment_of(ep))
    X = np.array(rows, dtype=float)
    # Impute NaNs at per-column medians (fall back to 0 for all-NaN columns).
    for j in range(X.shape[1]):
        col = X[:, j]
        if np.all(np.isnan(col)):
            X[:, j] = 0.0
            continue
        med = np.nanmedian(col)
        col[np.isnan(col)] = med
        X[:, j] = col
    return X, feat_names, ids, np.array(T, dtype=int)


# ── propensity model ────────────────────────────────────────────────────────
def fit_propensity(X, T, seed=0):
    """Logistic-regression propensity P(T=1|X) on standardized covariates.
    Returns dict with per-row propensity, logit, AUC, and the fitted scaler/model."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    clf = LogisticRegression(max_iter=2000, C=1.0, random_state=seed).fit(Xs, T)
    p = np.clip(clf.predict_proba(Xs)[:, 1], 1e-4, 1 - 1e-4)
    logit = np.log(p / (1 - p))
    auc = float(roc_auc_score(T, p)) if len(set(T.tolist())) > 1 else float("nan")
    return {"propensity": p, "logit": logit, "auc": auc, "scaler": scaler, "model": clf, "Xs": Xs}


# ── covariate balance (SMD) ─────────────────────────────────────────────────
def smd(a, b):
    """Standardized mean difference between two 1-D arrays (pooled SD). |SMD|<0.1 good."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    s1, s2 = a.std(ddof=1) if len(a) > 1 else 0.0, b.std(ddof=1) if len(b) > 1 else 0.0
    pooled = np.sqrt((s1 ** 2 + s2 ** 2) / 2.0)
    if pooled == 0:
        return 0.0
    return float(abs(a.mean() - b.mean()) / pooled)


def balance_report(X, T, feat_names, mask=None):
    """Per-feature |SMD| between treated and control. mask (bool array) restricts to a
    matched subset; None = full sample. Returns {feature: smd} + mean/max summary."""
    idx = np.ones(len(T), bool) if mask is None else np.asarray(mask, bool)
    treated = X[idx & (T == 1)]
    control = X[idx & (T == 0)]
    per = {}
    for j, name in enumerate(feat_names):
        per[name] = round(smd(treated[:, j], control[:, j]), 4)
    vals = [v for v in per.values() if v == v]
    return {"per_feature": per,
            "mean_abs_smd": round(float(np.mean(vals)), 4) if vals else None,
            "max_abs_smd": round(float(np.max(vals)), 4) if vals else None,
            "n_treated": int((idx & (T == 1)).sum()),
            "n_control": int((idx & (T == 0)).sum())}
