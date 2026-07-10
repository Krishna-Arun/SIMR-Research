"""
Common utilities for causal cardiac benchmarks.
Shared data loading, linking, and case discovery.
"""

import pandas as pd
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# ─── Paths ───────────────────────────────────────────────────────────────────

MIMIC_DATA_ROOT = Path(__file__).parent.parent.parent / "mimic-iv-ext-cardiac-disease-1.0.0"
LAB_EVENTS_FILE = MIMIC_DATA_ROOT / "heart_labevents_examination_group.csv"
PROCEDURES_FILE = MIMIC_DATA_ROOT / "heart_procedures.csv"
DIAGNOSES_FILE = MIMIC_DATA_ROOT / "heart_diagnoses_all_true.csv"
HPI_FILE = MIMIC_DATA_ROOT / "RAG_data" / "HPI.json"

# ─── Reference Ranges ────────────────────────────────────────────────────────

HUMAN_REF = {
    "Troponin T":       (0.0,    0.01,   "ng/mL"),
    "Creatine Kinase (CK)": (29.0,  201.0,  "IU/L"),
    "Creatine Kinase, MB Isoenzyme": (0.0, 6.0, "ng/mL"),
    "Creatinine":       (0.4,    1.1,    "mg/dL"),
    "BUN":              (6.0,    25.0,   "mg/dL"),
    "Hemoglobin":       (12.0,   17.5,   "g/dL"),
    "Hematocrit":       (36.0,   52.0,   "%"),
    "Potassium":        (3.3,    5.1,    "mEq/L"),
    "Sodium":           (133.0,  145.0,  "mEq/L"),
    "Bicarbonate":      (22.0,   32.0,   "mEq/L"),
    "Anion Gap":        (8.0,    20.0,   "mEq/L"),
    "Phosphate":        (2.7,    4.5,    "mg/dL"),
    "Magnesium":        (1.6,    2.6,    "mg/dL"),
    "Glucose":          (70.0,   99.0,   "mg/dL"),
    "INR(PT)":          (0.9,    1.1,    "ratio"),
    "PT":               (9.4,    12.5,   "sec"),
    "PTT":              (25.0,   36.5,   "sec"),
    "Platelet Count":   (150.0,  440.0,  "K/uL"),
    "White Blood Cells":(4.0,    11.0,   "K/uL"),
    "Red Blood Cells":  (4.2,    5.4,    "m/uL"),
}

# ─── Load and Cache Data ──────────────────────────────────────────────────────

_labs_cache = None
_procs_cache = None
_diags_cache = None
_hpi_cache = None

def load_labs():
    global _labs_cache
    if _labs_cache is None:
        print(f"Loading labs from {LAB_EVENTS_FILE}...")
        _labs_cache = pd.read_csv(LAB_EVENTS_FILE, low_memory=False)
        _labs_cache['charttime'] = pd.to_datetime(_labs_cache['charttime'])
        _labs_cache = _labs_cache.sort_values(['hadm_id', 'charttime'])
    return _labs_cache

def load_procedures():
    global _procs_cache
    if _procs_cache is None:
        print(f"Loading procedures from {PROCEDURES_FILE}...")
        _procs_cache = pd.read_csv(PROCEDURES_FILE)
        _procs_cache['chartdate'] = pd.to_datetime(_procs_cache['chartdate'])
    return _procs_cache

def load_diagnoses():
    global _diags_cache
    if _diags_cache is None:
        print(f"Loading diagnoses from {DIAGNOSES_FILE}...")
        _diags_cache = pd.read_csv(DIAGNOSES_FILE)
    return _diags_cache

def load_hpi():
    global _hpi_cache
    if _hpi_cache is None:
        print(f"Loading HPI from {HPI_FILE}...")
        with open(HPI_FILE) as f:
            hpi_list = json.load(f)
        # Convert list of {hadm_id: text} dicts into a single dict
        _hpi_cache = {}
        for entry in hpi_list:
            for hadm_id_str, text in entry.items():
                _hpi_cache[int(hadm_id_str)] = text
    return _hpi_cache

# ─── Demographics extraction from HPI ─────────────────────────────────────────

def extract_age_gender_from_hpi(hpi_text: str) -> Tuple[Optional[int], Optional[str]]:
    """Extract age and gender from HPI text."""
    if not hpi_text:
        return None, None

    # Try to find age pattern like "___ year old" or "XX-year-old"
    age_match = re.search(r'(\d{2,3})\s*(?:year|yo|y\.?o\.?)', hpi_text, re.IGNORECASE)
    age = int(age_match.group(1)) if age_match else None

    # Find gender
    gender = None
    if re.search(r'\bwoman\b|\bfemale\b|\bher\b', hpi_text, re.IGNORECASE):
        gender = "Female"
    elif re.search(r'\bman\b|\bmale\b|\bhis\b', hpi_text, re.IGNORECASE):
        gender = "Male"

    return age, gender

def get_patient_demographics(hadm_id: int) -> Dict:
    """Get age and gender for a patient from HPI."""
    hpi = load_hpi()
    hpi_text = hpi.get(hadm_id, "")
    age, gender = extract_age_gender_from_hpi(hpi_text)
    return {"age": age, "gender": gender or "Unknown"}

def get_primary_diagnosis(hadm_id: int) -> str:
    """Get primary diagnosis (seq_num=1) for a patient."""
    diags = load_diagnoses()
    primary = diags[(diags['hadm_id'] == hadm_id) & (diags['seq_num'] == 1)]
    if len(primary) > 0:
        return primary.iloc[0]['long_title']
    return "Unknown"

# ─── Lab utilities ───────────────────────────────────────────────────────────

def get_cardiac_labs_for_hadm(hadm_id: int, up_to_time: datetime = None) -> pd.DataFrame:
    """Get cardiac marker labs for a hadm_id, optionally up to a specific time."""
    labs = load_labs()
    cardiac = labs[
        (labs['hadm_id'] == hadm_id) &
        (labs['examination_group'] == 'Cardiac Markers')
    ].copy()

    if up_to_time:
        cardiac = cardiac[cardiac['charttime'] <= up_to_time]

    return cardiac.sort_values('charttime')

def get_all_labs_for_hadm(hadm_id: int, up_to_time: datetime = None) -> pd.DataFrame:
    """Get all labs for a hadm_id, optionally up to a specific time."""
    labs = load_labs()
    patient_labs = labs[labs['hadm_id'] == hadm_id].copy()

    if up_to_time:
        patient_labs = patient_labs[patient_labs['charttime'] <= up_to_time]

    return patient_labs.sort_values('charttime')

def flag_lab_value(label: str, value: float) -> Optional[str]:
    """Flag a lab value as normal, low, or abnormal."""
    if pd.isna(value):
        return None
    ref = HUMAN_REF.get(label)
    if ref is None:
        return None
    lo, hi, _ = ref
    if value < lo:
        return "low"
    if value > hi:
        return "abnormal"
    return None

# ─── Procedure utilities ──────────────────────────────────────────────────────

def get_procedures_for_hadm(hadm_id: int) -> pd.DataFrame:
    """Get all procedures for a hadm_id."""
    procs = load_procedures()
    return procs[procs['hadm_id'] == hadm_id].sort_values('chartdate')

def get_first_procedure(hadm_id: int) -> Optional[Dict]:
    """Get the first (earliest) procedure for a hadm_id."""
    procs = get_procedures_for_hadm(hadm_id)
    if len(procs) > 0:
        p = procs.iloc[0]
        return {
            'date': p['chartdate'],
            'code': p['icd_code'],
            'title': p['long_title'],
        }
    return None

# ─── Case building utilities ──────────────────────────────────────────────────

def format_lab_table(labs_df: pd.DataFrame, markdown: bool = True) -> str:
    """Format labs as markdown or text table."""
    if len(labs_df) == 0:
        return "(no labs)"

    if markdown:
        lines = [
            "| Datetime | Lab | Value | Unit | Flag |",
            "|---|---|---|---|---|",
        ]
        for _, row in labs_df.iterrows():
            flag_str = row.get('flag', '') or ''
            lines.append(
                f"| {row['charttime'].strftime('%Y-%m-%d %H:%M')} | "
                f"{row['label']} | {row['valuenum']} | {row['valueuom']} | {flag_str} |"
            )
        return "\n".join(lines)
    else:
        lines = []
        for _, row in labs_df.iterrows():
            lines.append(
                f"{row['charttime'].strftime('%Y-%m-%d %H:%M')}: "
                f"{row['label']} = {row['valuenum']} {row['valueuom']}"
            )
        return "\n".join(lines)

def hours_between(t1: datetime, t2: datetime) -> float:
    """Hours between two datetimes."""
    return (t2 - t1).total_seconds() / 3600.0

def direction(v_before: float, v_after: float, threshold: float = 0.20) -> str:
    """Classify direction of change: rising, falling, or stable."""
    if v_before <= 0:
        return "rising" if v_after > 0 else "stable"
    delta = (v_after - v_before) / v_before
    if delta > threshold:
        return "rising"
    if delta < -threshold:
        return "falling"
    return "stable"
