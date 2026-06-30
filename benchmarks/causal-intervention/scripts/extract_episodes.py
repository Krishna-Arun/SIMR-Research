"""
extract_episodes.py

Extract intervention-anchored episodes from EHRSHOT/MIMIC data.

For each intervention (PCI, CABG, vasopressors, antibiotics, dialysis, etc.):
  - Pre-window: [-48h, 0] (all clinical context)
  - Post-window: [0, +48h] (trajectory to predict)
  - Adaptive resampling to fixed-length latent timeline

Output: episodes.json with 100+ cases
"""

import meds_reader
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timedelta, datetime
from collections import defaultdict
from typing import Optional, Tuple, List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent.parent
EHRSHOT_PATH = REPO_ROOT / "EHRSHOT Hackathon Project" / "meds_reader_omop_ehrshot"
CODES_META = EHRSHOT_PATH / "metadata" / "codes.parquet"
OUT_DIR = Path(__file__).parent.parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "episodes.json"
EPISODES_DIR = OUT_DIR / "episodes"
EPISODES_DIR.mkdir(parents=True, exist_ok=True)

# ── Intervention Taxonomy ─────────────────────────────────────────────────────
INTERVENTION_CODES = {
    # Cardiac
    "pci": ["CPT/92982", "CPT/92984", "CPT/92995", "CPT/92996"],  # Percutaneous coronary
    "cabg": ["CPT/33510", "CPT/33511", "CPT/33512"],  # Coronary artery bypass

    # Respiratory
    "intubation": ["CPT/31500"],  # Endotracheal intubation
    "extubation": ["CPT/31505"],  # Removal of endotracheal tube
    "ventilation": ["CPT/94002", "CPT/94003"],  # Mechanical ventilation

    # Renal
    "dialysis": ["CPT/90935", "CPT/90937"],  # Hemodialysis
    "crrt": ["CPT/90999"],  # Continuous renal replacement

    # Hemodynamic
    "vasopressor_norepi": ["STANFORD_SHC_DRUG/norepinephrine"],
    "vasopressor_epi": ["STANFORD_SHC_DRUG/epinephrine"],
    "vasopressor_vasopressin": ["STANFORD_SHC_DRUG/vasopressin"],
    "vasopressor_phenylephrine": ["STANFORD_SHC_DRUG/phenylephrine"],

    # Infection - Antibiotics (by class)
    "antibiotic_betalactam": ["STANFORD_SHC_DRUG/amoxicillin", "STANFORD_SHC_DRUG/ampicillin",
                              "STANFORD_SHC_DRUG/cephalexin", "STANFORD_SHC_DRUG/ceftriaxone"],
    "antibiotic_vanc": ["STANFORD_SHC_DRUG/vancomycin"],
    "antibiotic_fluoroquinolone": ["STANFORD_SHC_DRUG/ciprofloxacin", "STANFORD_SHC_DRUG/levofloxacin"],
}

LOINC_LAB_CODES = {
    "Troponin I": "LOINC/10839-9",
    "Creatinine": "LOINC/2160-0",
    "BUN": "LOINC/3094-0",
    "Potassium": "LOINC/2823-3",
    "Sodium": "LOINC/2951-2",
    "Bicarbonate": "LOINC/1963-8",
    "Hemoglobin": "LOINC/718-7",
    "Glucose": "LOINC/2345-7",
    "WBC": "LOINC/6690-2",
    "Platelets": "LOINC/777-3",
    "INR": "LOINC/6301-6",
    "Calcium": "LOINC/17861-6",
    "Phosphorus": "LOINC/2777-1",
    "Albumin": "LOINC/1751-7",
    "Magnesium": "LOINC/2601-3",
    "ALT": "LOINC/1742-6",
    "Lactate": "LOINC/2519-7",
    "BNP": "LOINC/42637-9",
    "eGFR": "LOINC/62238-1",
    "Hematocrit": "LOINC/20570-8",
    "Chloride": "LOINC/2075-0",
    "Anion Gap": "LOINC/33037-3",
}

LOINC_TO_LABEL = {v: k for k, v in LOINC_LAB_CODES.items()}

HUMAN_REF = {
    "Creatinine": (0.5, 1.2, "mg/dL"),
    "BUN": (7.0, 25.0, "mg/dL"),
    "Potassium": (3.5, 5.0, "mEq/L"),
    "Sodium": (136, 145, "mEq/L"),
    "Bicarbonate": (22, 29, "mEq/L"),
    "Hemoglobin": (12.0, 17.5, "g/dL"),
    "Glucose": (70, 99, "mg/dL"),
    "WBC": (4.5, 11.0, "K/uL"),
    "Platelets": (150, 400, "K/uL"),
    "INR": (0.9, 1.1, "ratio"),
    "Calcium": (8.5, 10.5, "mg/dL"),
    "Phosphorus": (2.5, 4.5, "mg/dL"),
    "Albumin": (3.5, 5.0, "g/dL"),
    "Magnesium": (1.7, 2.2, "mg/dL"),
    "ALT": (7, 56, "U/L"),
    "Lactate": (0.5, 2.0, "mmol/L"),
    "Troponin I": (0, 0.04, "ng/mL"),
    "Hematocrit": (36, 52, "%"),
    "Chloride": (98, 107, "mEq/L"),
    "eGFR": (60, 120, "mL/min/1.73m2"),
    "Anion Gap": (8, 16, "mEq/L"),
    "BNP": (0, 100, "pg/mL"),
}

VITAL_CODES = {
    "systolic_bp": "SNOMED/72313002",
    "diastolic_bp": "SNOMED/1091811000",
    "heart_rate": "SNOMED/364075005",
    "respiratory_rate": "SNOMED/86290005",
    "temperature": "SNOMED/386725007",
    "o2_saturation": "SNOMED/431314004",
}

# ── Utility Functions ─────────────────────────────────────────────────────────
def _flag(label: str, value: float) -> Optional[str]:
    ref = HUMAN_REF.get(label)
    if ref is None or value is None:
        return None
    lo, hi, _ = ref
    if value < lo:
        return "low"
    if value > hi:
        return "abnormal"
    return None


def _resample_trajectory(timestamps: List[datetime],
                        values: List[float],
                        target_length: int = 96) -> Tuple[List[float], List[str]]:
    """
    Resample trajectory to fixed-length timeline using linear interpolation.

    Args:
        timestamps: measurement times (sorted)
        values: measurement values
        target_length: desired output length

    Returns:
        resampled_values, resampled_times (ISO format)
    """
    if len(timestamps) < 2:
        return [values[0]] * target_length, [timestamps[0].isoformat()] * target_length

    # Time range in seconds
    t_start = timestamps[0]
    t_end = timestamps[-1]
    total_seconds = (t_end - t_start).total_seconds()

    if total_seconds == 0:
        return [values[0]] * target_length, [t_start.isoformat()] * target_length

    # Convert timestamps to relative seconds
    t_rel = [(t - t_start).total_seconds() for t in timestamps]

    # Target timeline
    target_times_rel = np.linspace(0, total_seconds, target_length)
    target_datetimes = [t_start + timedelta(seconds=float(s)) for s in target_times_rel]

    # Linear interpolation
    resampled_values = np.interp(target_times_rel, t_rel, values).tolist()
    resampled_times = [t.isoformat() for t in target_datetimes]

    return resampled_values, resampled_times


def build_episode(subject_id: int,
                 events: List,
                 intervention_type: str,
                 intervention_time: datetime,
                 intervention_code: str,
                 episode_id: int) -> Optional[Dict]:
    """
    Build one episode: pre-window [-48h, 0] and post-window [0, +48h].
    """
    events_sorted = sorted(events, key=lambda e: e.time)

    # ── Demographics ──────────────────────────────────────────────────────────
    birth_year, gender = None, "Unknown"
    for e in events_sorted:
        if e.table == "person":
            if "MEDS_BIRTH" in e.code:
                birth_year = e.time.year
            if e.code.startswith("Gender/"):
                raw = e.code.split("/")[-1]
                gender = "Female" if raw.upper() in ("F", "FEMALE") else "Male"

    age = (intervention_time.year - birth_year) if birth_year else 50

    # ── Time windows ──────────────────────────────────────────────────────────
    pre_start = intervention_time - timedelta(hours=48)
    post_end = intervention_time + timedelta(hours=48)

    # ── Pre-window labs (context) ──────────────────────────────────────────────
    pre_labs: Dict[str, List] = defaultdict(list)
    for e in events_sorted:
        if e.table != "measurement":
            continue
        if e.code not in LOINC_TO_LABEL:
            continue
        if e.numeric_value is None:
            continue
        if not (pre_start <= e.time <= intervention_time):
            continue

        label = LOINC_TO_LABEL[e.code]
        pre_labs[label].append({
            "time": e.time,
            "value": e.numeric_value,
            "unit": e.unit or HUMAN_REF.get(label, (None, None, ""))[2] or "",
        })

    # Format pre-window context
    pre_context = []
    for label, measurements in pre_labs.items():
        measurements.sort(key=lambda x: x["time"])
        for m in measurements:
            pre_context.append({
                "datetime": m["time"].isoformat(),
                "label": label,
                "value": round(m["value"], 3),
                "unit": m["unit"],
                "flag": _flag(label, m["value"]),
                "ref_lower": str(HUMAN_REF.get(label, (None, None, ""))[0]) if HUMAN_REF.get(label, (None, None, ""))[0] else "",
                "ref_upper": str(HUMAN_REF.get(label, (None, None, ""))[1]) if HUMAN_REF.get(label, (None, None, ""))[1] else "",
            })

    # ── Post-window labs (trajectory) ─────────────────────────────────────────
    post_labs: Dict[str, List] = defaultdict(list)
    for e in events_sorted:
        if e.table != "measurement":
            continue
        if e.code not in LOINC_TO_LABEL:
            continue
        if e.numeric_value is None:
            continue
        if not (intervention_time < e.time <= post_end):
            continue

        label = LOINC_TO_LABEL[e.code]
        post_labs[label].append({
            "time": e.time,
            "value": e.numeric_value,
        })

    # If post-window is sparse, interpolate key labs
    post_trajectory = {}
    for label in LOINC_LAB_CODES.keys():
        if label in post_labs and len(post_labs[label]) >= 1:
            measurements = sorted(post_labs[label], key=lambda x: x["time"])
            times = [m["time"] for m in measurements]
            values = [m["value"] for m in measurements]

            resampled_vals, resampled_times = _resample_trajectory(times, values, target_length=96)
            post_trajectory[label] = {
                "resampled_values": [round(v, 3) for v in resampled_vals],
                "resampled_times": resampled_times,
                "n_original_measurements": len(measurements),
            }

    # Check: must have at least some post-window data
    if not post_trajectory:
        logger.warning(f"Episode {episode_id}: no post-window data for {subject_id}")
        return None

    # ── Clinical context (diagnoses, medications) ──────────────────────────────
    visit_events: Dict[str, List] = defaultdict(list)
    for e in events_sorted:
        if e.visit_id and e.time <= intervention_time:
            visit_events[e.visit_id].append(e)

    # Find visit containing intervention
    current_visit_id = None
    for e in events_sorted:
        if e.visit_id and abs((e.time - intervention_time).total_seconds()) < 86400:  # within 1 day
            current_visit_id = e.visit_id
            break

    diagnoses = []
    medications = []
    if current_visit_id:
        for e in visit_events.get(current_visit_id, []):
            if e.table == "condition":
                diagnoses.append(e.code)
            elif e.table == "drug_exposure":
                medications.append(e.code)

    # ── Build output ──────────────────────────────────────────────────────────
    pre_context.sort(key=lambda x: (x["datetime"], x["label"]))

    return {
        "episode_id": f"episode_{episode_id:04d}",
        "patient_id": str(subject_id),
        "intervention": {
            "type": intervention_type,
            "code": intervention_code,
            "datetime": intervention_time.isoformat(),
        },
        "demographics": {
            "age": age,
            "gender": gender,
        },
        "clinical_context": {
            "diagnoses": list(dict.fromkeys(diagnoses))[:10],
            "medications": list(dict.fromkeys(medications))[:15],
        },
        "pre_context": {
            "window_hours": 48,
            "labs": pre_context,
            "n_measurements": len(pre_context),
        },
        "post_trajectory": post_trajectory,
        "metadata": {
            "pre_window_start": (intervention_time - timedelta(hours=48)).isoformat(),
            "intervention_time": intervention_time.isoformat(),
            "post_window_end": (intervention_time + timedelta(hours=48)).isoformat(),
        },
    }


def main():
    logger.info(f"Loading EHRSHOT database from {EHRSHOT_PATH}...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))
    logger.info(f"Total subjects: {len(db)}")

    all_episodes = []
    episode_counter = 0
    processed = 0

    # Build reverse lookup: code -> intervention type
    code_to_intervention = {}
    for int_type, codes in INTERVENTION_CODES.items():
        for code in codes:
            code_to_intervention[code] = int_type

    logger.info(f"Intervention codes to search: {len(code_to_intervention)}")

    for subject_id in db:
        subject = db[subject_id]
        events = list(subject.events)
        processed += 1

        if processed % 1000 == 0:
            logger.info(f"  {processed}/{len(db)} scanned | episodes: {len(all_episodes)}")

        # Find all intervention events
        intervention_events = []
        for e in events:
            if e.code in code_to_intervention:
                intervention_events.append((e.time, e.code, code_to_intervention[e.code]))

        if not intervention_events:
            continue

        # Build episode for each intervention
        for intervention_time, intervention_code, intervention_type in intervention_events:
            episode_counter += 1
            episode = build_episode(
                subject_id=subject_id,
                events=events,
                intervention_type=intervention_type,
                intervention_time=intervention_time,
                intervention_code=intervention_code,
                episode_id=episode_counter,
            )

            if episode:
                all_episodes.append(episode)

                # Also save individual episode
                episode_file = EPISODES_DIR / f"{episode['episode_id']}.json"
                with open(episode_file, "w") as f:
                    json.dump(episode, f, indent=2)

                if len(all_episodes) % 50 == 0:
                    logger.info(f"  Built {len(all_episodes)} episodes...")

        # Stop if we have enough
        if len(all_episodes) >= 150:
            break

    logger.info(f"\nTotal episodes built: {len(all_episodes)}")

    # Intervention distribution
    int_dist = {}
    for ep in all_episodes:
        int_type = ep["intervention"]["type"]
        int_dist[int_type] = int_dist.get(int_type, 0) + 1
    logger.info(f"Intervention distribution: {int_dist}")

    # Build manifest
    manifest = {
        "name": "causal_intervention_episodes_v1",
        "description": (
            "Intervention-anchored episodes from EHRSHOT. "
            "Each episode has 48h pre-window context and 48h post-window trajectory to predict."
        ),
        "n_episodes": len(all_episodes),
        "n_interventions": len(set(e["intervention"]["type"] for e in all_episodes)),
        "intervention_distribution": int_dist,
        "episodes": all_episodes,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"Wrote {OUT_FILE} ({len(all_episodes)} episodes)")
    logger.info(f"Individual episodes saved to {EPISODES_DIR}")


if __name__ == "__main__":
    main()
