"""
encode_features.py

Build severity embeddings and confounder features from episodes.

Output:
- Severity scores (SOFA-like or learned)
- Comorbidity vectors
- Pre-trend features (slope, direction, volatility)
- Baseline lab normalization
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent.parent
IN_DIR = Path(__file__).parent.parent / "data"
EPISODES_FILE = IN_DIR / "episodes.json"
OUT_DIR = IN_DIR
OUT_FILE = OUT_DIR / "encoded_features.json"

# ── Reference ranges for normalization ────────────────────────────────────────
HUMAN_REF = {
    "Creatinine": (0.5, 1.2),
    "BUN": (7.0, 25.0),
    "Potassium": (3.5, 5.0),
    "Sodium": (136, 145),
    "Bicarbonate": (22, 29),
    "Hemoglobin": (12.0, 17.5),
    "Glucose": (70, 99),
    "WBC": (4.5, 11.0),
    "Platelets": (150, 400),
    "INR": (0.9, 1.1),
    "Calcium": (8.5, 10.5),
    "Phosphorus": (2.5, 4.5),
    "Albumin": (3.5, 5.0),
    "Magnesium": (1.7, 2.2),
    "ALT": (7, 56),
    "Lactate": (0.5, 2.0),
    "Troponin I": (0, 0.04),
    "Hematocrit": (36, 52),
    "Chloride": (98, 107),
    "eGFR": (60, 120),
    "Anion Gap": (8, 16),
    "BNP": (0, 100),
}

# SOFA scoring components
SOFA_COMPONENTS = {
    "PaO2": (400, 300, 200, 100),  # thresholds for 1, 2, 3, 4 points
    "bilirubin": (1.2, 1.9, 5.9, 11.5),
    "creatinine": (1.1, 1.9, 3.5, 4.9),  # without renal replacement
    "platelets": (150, 100, 50, 20),
    "MAP": (70, 70, 70, 70),  # Need vasopressor use
    "Glasgow": (15, 13, 10, 6),
}

# Common chronic diagnoses (comorbidity)
COMORBIDITIES = {
    "diabetes": ["E11", "E10", "E13", "E14"],  # ICD-10 codes
    "hypertension": ["I10", "I11", "I12"],
    "ckd": ["N18"],
    "cad": ["I25"],
    "heart_failure": ["I50"],
    "copd": ["J44"],
    "asthma": ["J45"],
    "cancer": ["C"],
    "afib": ["I48"],
    "prior_mi": ["I21", "I22"],
}


def _z_score_normalize(value: float, ref_low: float, ref_high: float) -> float:
    """
    Normalize value to z-score within reference range.
    z = (value - ref_mid) / (ref_range / 4)
    """
    if ref_low is None or ref_high is None:
        return 0.0

    ref_mid = (ref_low + ref_high) / 2.0
    ref_range = ref_high - ref_low
    if ref_range == 0:
        return 0.0

    return (value - ref_mid) / (ref_range / 4.0)


def compute_severity_score(labs: Dict[str, float]) -> float:
    """
    Compute SOFA-like severity score from available labs.
    Returns score in [0, 24] (simplified SOFA).
    """
    sofa_score = 0

    # Creatinine component (renal)
    if "Creatinine" in labs:
        cr = labs["Creatinine"]
        if cr < 1.1:
            sofa_score += 0
        elif cr < 1.9:
            sofa_score += 1
        elif cr < 3.5:
            sofa_score += 2
        elif cr < 4.9:
            sofa_score += 3
        else:
            sofa_score += 4

    # Bilirubin component (hepatic)
    if "Bilirubin" in labs:  # would need to extract this; placeholder
        sofa_score += 0  # Simplified: not always available

    # Platelets component (coagulation)
    if "Platelets" in labs:
        plts = labs["Platelets"]
        if plts >= 150:
            sofa_score += 0
        elif plts >= 100:
            sofa_score += 1
        elif plts >= 50:
            sofa_score += 2
        elif plts >= 20:
            sofa_score += 3
        else:
            sofa_score += 4

    # WBC (infection proxy)
    if "WBC" in labs:
        wbc = labs["WBC"]
        if 4.5 <= wbc <= 11.0:
            sofa_score += 0
        elif wbc < 1.0:
            sofa_score += 2
        elif wbc > 20.0:
            sofa_score += 1

    return min(sofa_score, 24)  # Cap at 24


def compute_severity_bin(score: float) -> str:
    """Categorize SOFA score into severity bins."""
    if score < 4:
        return "mild"
    elif score < 7:
        return "moderate"
    elif score < 10:
        return "moderately_severe"
    else:
        return "severe"


def extract_pre_trend_features(pre_context: List[Dict]) -> Dict[str, Dict]:
    """
    Extract pre-trend features from pre-context labs.
    For each lab: slope (last 48h), direction, volatility.
    """
    pre_trend = {}

    # Organize labs by label
    labs_by_label = {}
    for measurement in pre_context:
        label = measurement["label"]
        if label not in labs_by_label:
            labs_by_label[label] = []
        labs_by_label[label].append({
            "time": datetime.fromisoformat(measurement["datetime"]),
            "value": measurement["value"],
        })

    # Compute trend for each lab
    for label, measurements in labs_by_label.items():
        if len(measurements) < 2:
            pre_trend[label] = {
                "slope": 0.0,
                "direction": "stable",
                "volatility": 0.0,
                "n_measurements": len(measurements),
            }
            continue

        measurements.sort(key=lambda x: x["time"])

        # Time in hours
        times = [(m["time"] - measurements[0]["time"]).total_seconds() / 3600 for m in measurements]
        values = [m["value"] for m in measurements]

        if times[-1] == 0:  # All same time
            pre_trend[label] = {
                "slope": 0.0,
                "direction": "stable",
                "volatility": 0.0,
                "n_measurements": len(measurements),
            }
            continue

        # Linear fit
        coeffs = np.polyfit(times, values, 1)
        slope = coeffs[0]  # per hour
        intercept = coeffs[1]

        # Volatility: std of residuals
        fitted = np.polyval(coeffs, times)
        residuals = np.array(values) - fitted
        volatility = float(np.std(residuals))

        # Direction
        if abs(slope) < 0.001:
            direction = "stable"
        elif slope > 0:
            direction = "rising"
        else:
            direction = "falling"

        pre_trend[label] = {
            "slope": round(float(slope), 4),  # per hour
            "slope_per_48h": round(float(slope * 48), 3),
            "direction": direction,
            "volatility": round(volatility, 4),
            "n_measurements": len(measurements),
        }

    return pre_trend


def extract_comorbidities(diagnoses: List[str]) -> Dict[str, int]:
    """
    Extract one-hot comorbidity vector from diagnoses.
    """
    comorbidity_vector = {k: 0 for k in COMORBIDITIES.keys()}

    for diag_code in diagnoses:
        # Extract ICD prefix
        if "/" in diag_code:
            icd_code = diag_code.split("/")[-1]
        else:
            icd_code = diag_code

        # Check each comorbidity group
        for comorbid_name, prefixes in COMORBIDITIES.items():
            for prefix in prefixes:
                if icd_code.startswith(prefix):
                    comorbidity_vector[comorbid_name] = 1
                    break

    return comorbidity_vector


def encode_episode(episode: Dict) -> Dict:
    """
    Encode one episode with all confounding features.
    """
    # Extract last available lab values (for severity)
    labs_latest = {}
    for lab_info in episode["pre_context"]["labs"]:
        label = lab_info["label"]
        if label not in labs_latest:
            labs_latest[label] = lab_info["value"]

    # Compute severity
    severity_score = compute_severity_score(labs_latest)
    severity_bin = compute_severity_bin(severity_score)

    # Extract pre-trend
    pre_trend = extract_pre_trend_features(episode["pre_context"]["labs"])

    # Extract comorbidities
    comorbidities = extract_comorbidities(episode["clinical_context"]["diagnoses"])

    # Normalize key labs to z-scores
    normalized_labs = {}
    for label, value in labs_latest.items():
        if label in HUMAN_REF:
            ref_low, ref_high = HUMAN_REF[label]
            z = _z_score_normalize(value, ref_low, ref_high)
            normalized_labs[label] = round(z, 3)

    return {
        "episode_id": episode["episode_id"],
        "patient_id": episode["patient_id"],
        "intervention": episode["intervention"],
        "severity": {
            "sofa_score": round(severity_score, 1),
            "severity_bin": severity_bin,
        },
        "comorbidities": comorbidities,
        "pre_trend": pre_trend,
        "normalized_labs": normalized_labs,
        "metadata": {
            "n_pre_measurements": episode["pre_context"]["n_measurements"],
            "n_trajectory_labs": len(episode["post_trajectory"]),
        },
    }


def main():
    logger.info(f"Loading episodes from {EPISODES_FILE}...")
    with open(EPISODES_FILE, "r") as f:
        manifest = json.load(f)

    episodes = manifest["episodes"]
    logger.info(f"Loaded {len(episodes)} episodes")

    # Encode each episode
    encoded_features = []
    for i, episode in enumerate(episodes):
        try:
            encoded = encode_episode(episode)
            encoded_features.append(encoded)
            if (i + 1) % 50 == 0:
                logger.info(f"  Encoded {i + 1}/{len(episodes)}...")
        except Exception as e:
            logger.error(f"Error encoding episode {episode['episode_id']}: {e}")

    logger.info(f"Successfully encoded {len(encoded_features)} episodes")

    # Severity distribution
    severity_dist = {}
    for ef in encoded_features:
        bin = ef["severity"]["severity_bin"]
        severity_dist[bin] = severity_dist.get(bin, 0) + 1
    logger.info(f"Severity distribution: {severity_dist}")

    # Comorbidity prevalence
    comorbidity_prevalence = {k: 0 for k in COMORBIDITIES.keys()}
    for ef in encoded_features:
        for comorbid, val in ef["comorbidities"].items():
            comorbidity_prevalence[comorbid] += val
    comorbidity_prevalence = {k: round(v / len(encoded_features), 3) for k, v in comorbidity_prevalence.items()}
    logger.info(f"Comorbidity prevalence: {comorbidity_prevalence}")

    # Save
    output_manifest = {
        "name": "causal_intervention_encoded_features_v1",
        "n_episodes": len(encoded_features),
        "severity_distribution": severity_dist,
        "comorbidity_prevalence": comorbidity_prevalence,
        "features": encoded_features,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(output_manifest, f, indent=2)

    logger.info(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
