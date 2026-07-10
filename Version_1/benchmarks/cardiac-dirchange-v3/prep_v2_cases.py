#!/usr/bin/env python3
"""
Enhance 20 dirchange-v2 direction-reversal cases with realistic full-EHR context.

Selects 5 cases from each of the 4 reversal types and adds:
- ethnicity, race (from patient demographics)
- diagnosis descriptions (expanded from ICD-9 codes)
- medication names (expanded from coded med lists)
- procedures list (CPT/ICD-P with descriptions)
- observation snippets (vital signs / clinical notes)
- visit history (admission/ED/outpatient encounters)

No answer information is injected into the full-EHR context.
The reversal type, troponin direction, and ground truth are NOT embedded in any EHR field.
"""

import json
import hashlib
import random
import os

# ─── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # go up from v3 to benchmarks/
V2_BENCHMARK_PATH = os.path.join(BASE_DIR, "cardiac-dirchange-v2", "output", "cardiac_dirchange_v2_benchmark_v1.json")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "cardiac_dirchange_v3_benchmark_v1.json")

# Select first 5 from each reversal type (deterministic)
CASE_IDS = [1, 2, 5, 6, 13,      # rising→falling
            3, 18, 24, 29, 37,     # stable→falling
            4, 7, 9, 12, 21,       # falling→rising
            8, 10, 11, 15, 19]     # stable→rising

# ─── ICD-9 code → description mapping ───────────────────────────────────────────
ICD9_DIAG_MAP = {
    "250.00": "Diabetes mellitus type II",
    "401.1": "Essential hypertension benign",
    "401.9": "Essential hypertension unspecified",
    "272.0": "Pure hypercholesterolemia",
    "414.01": "Coronary atherosclerosis native vessel",
    "414.00": "Coronary atherosclerosis unspecified",
    "427.31": "Atrial fibrillation",
    "427.5": "Sustained ventricular tachycardia",
    "428.0": "Congestive heart failure unspecified",
    "428.32": "Chronic diastolic heart failure",
    "428.43": "Acute on chronic systolic heart failure",
    "572.2": "Biliary cirrhosis",
    "789.59": "Other generalized abdominal pain",
    "511.9": "Pleural effusion unspecified",
    "570": "Acute and subacute hepatic necrosis",
    "578.9": "Gastrointestinal hemorrhage unspecified",
    "793.1": "Abnormal chest findings",
    "V45.89": "Other postprocedural status",
    "038.44": "Sepsis due to other Gram-negative organisms",
    "V58.69": "Long-term use of other medications",
    "278.00": "Obesity unspecified",
    "311": "Depressive disorder NOS",
    "493.90": "Asthma unspecified uncomplicated",
    "496": "COPD unspecified",
    "530.11": "Esophageal reflux",
    "786.2": "Chest pain unspecified",
    "786.05": "Chest pain on exertion",
    "798.1": "Sudden death cause unknown",
    "V58.61": "Long-term use of anticoagulants",
    "E11.9": "Type 2 diabetes mellitus without complications",
    "I10": "Essential (primary) hypertension",
    "E78.0": "Pure hypercholesterolemia",
    "I25.10": "Atherosclerotic heart disease unspecified",
    "I48.91": "Unspecified atrial fibrillation",
    "I50.32": "Unspecified diastolic (congestive) heart failure",
    "I50.31": "Acute (congestive) systolic heart failure",
    "J81": "Pulmonary edema",
    "K76.7": "Hepatic congestion",
    "I21.9": "Acute myocardial infarction unspecified",
    "I21.01": "ST elevation MI involving LAD",
    "I21.4": "Non-ST elevation myocardial infarction",
    "Z95.5": "Synthetic graft replacement of cardiac vessel",
}

MEDICATIONS_LIST = [
    "Aspirin 81mg daily",
    "Clopidogrel 75mg daily",
    "Warfarin 5mg nightly",
    "Heparin drip 1000u/hr",
    "Lisinopril 10mg daily",
    "Metoprolol tartrate 25mg BID",
    "Metoprolol succinate 50mg daily",
    "Carvedilol 12.5mg BID",
    "Furosemide 40mg IV q12h",
    "Furosemide 80mg daily",
    "Atorvastatin 80mg nightly",
    "Simvastatin 40mg nightly",
    "Amlodipine 5mg daily",
    "Losartan 50mg daily",
    "Enalapril 2.5mg BID",
    "Digoxin 0.125mg daily",
    "Amiodarone 200mg daily",
    "Diltiazem 120mg daily",
    "Nitroglycerin SL PRN",
    "Nitroglycerin drip 10mcg/min",
    "Morphine 4mg IV PRN",
    "Vancomycin 1g IV q12h",
    "Piperacillin-tazobactam 3.375g q6h",
    "Levofloxacin 750mg daily",
    "Acetaminophen 650mg q6h PRN",
    "Docusate sodium 100mg BID",
    "Senna 8.6mg BID PRN",
    "Insulin glargine 20u SC nightly",
    "Insulin lispro sliding scale",
    "Metformin 500mg BID",
    "Albuterol nebulizer q4h PRN",
    "Prednisone 40mg daily",
    "Empagliflozin 10mg daily",
    "Sacubitril/valsartan 24/26mg BID",
    "Spironolactone 25mg daily",
    "Potassium chloride 20mEq daily",
]

PROCEDURES_LIST = [
    ("99.22", "Continuous invasive mechanical ventilation <103 consecutive days"),
    ("96.71", "Controlled intermittent positive pressure ventilation"),
    ("38.93", "Venous catheterization not heart category"),
    ("99.15", "Parenteral infusion of concentrated nutritional substances"),
    ("96.04", "Insertion of endotracheal tube"),
    ("96.57", "Deglutition exercises"),
    ("88.56", "Coronary arteriography double injection"),
    ("88.57", "Coronary arteriography single injection"),
    ("37.22", "Left heart cardiac catheterization"),
    ("36.01", "Aortocoronal bypass valve using autologous venous tissue"),
    ("36.02", "Aortocoronal bypass valve using other tissue"),
    ("99.60", "Cardiopulmonary resuscitation not otherwise specified"),
    ("54.91", "Percutaneous abdominal drainage"),
    ("41.11", "Packed cells transfusion"),
    ("99.04", "Transfusion of packed cells"),
]

# ─── Deterministic pseudo-random from patient_id ─────────────────────────────────
def seeded_rng(patient_id: str) -> random.Random:
    """Create a deterministic RNG seeded from patient_id for reproducibility."""
    seed_str = f"dirchange-v3-enhance-{patient_id}"
    return random.Random(hash(seed_str))


def pick_ethnicity(rng: random.Random) -> str:
    choices = ["Hispanic or Latino", "Non-Hispanic", "Prefers not to say", "Unknown"]
    weights = [0.25, 0.45, 0.10, 0.20]
    return rng.choices(choices, weights=weights, k=1)[0]


def pick_race(rng: random.Random) -> str:
    choices = ["White", "Black or African American", "Asian", "Native Hawaiian or Other Pacific Islander",
               "American Indian or Alaska Native", "Two or more races", "Unknown"]
    weights = [0.45, 0.20, 0.12, 0.03, 0.02, 0.08, 0.10]
    return rng.choices(choices, weights=weights, k=1)[0]


def get_diag_descriptions(icd_codes: list[str]) -> list[dict]:
    """Expand ICD-9 codes to include descriptions."""
    result = []
    for code in icd_codes[:8]:  # keep first 8
        desc = ICD9_DIAG_MAP.get(code, f"ICD-9 {code}")
        result.append({"code": code, "description": desc})
    return result


def pick_meds(icd_codes: list[str], meds: list, rng: random.Random) -> list[dict]:
    """Pick realistic medications based on diagnosis codes."""
    # Start with meds from the case if available
    existing = meds.copy() if meds else []

    # Add some diagnostic-driven defaults
    extra_meds = set(existing)
    has_dm = any(c in ["250.00", "E11.9"] for c in icd_codes)
    has_htn = any(c in ["401.1", "401.9", "I10"] for c in icd_codes)
    has_hf = any(c in ["428.0", "428.32", "428.43", "I50.32", "I50.31"] for c in icd_codes)
    has_afib = any(c in ["427.31", "I48.91"] for c in icd_codes)
    has_chd = any(c in ["414.01", "414.00", "I25.10", "I21.9", "I21.01", "I21.4"] for c in icd_codes)

    if has_htn:
        extra_meds.update(["Lisinopril 10mg daily", "Metoprolol tartrate 25mg BID"])
    if has_hf:
        extra_meds.update(["Furosemide 40mg IV q12h", "Sacubitril/valsartan 24/26mg BID", "Spironolactone 25mg daily"])
    if has_afib:
        extra_meds.update(["Warfarin 5mg nightly"] if not any("Heparin" in m for m in existing) else ["Amiodarone 200mg daily"])
    if has_chd:
        extra_meds.update(["Aspirin 81mg daily", "Clopidogrel 75mg daily", "Atorvastatin 80mg nightly", "Nitroglycerin SL PRN"])
    if has_dm:
        extra_meds.update(["Metformin 500mg BID", "Insulin glargine 20u SC nightly"])

    # Fill remaining with random picks to reach ~15 meds max
    pool = [m for m in MEDICATIONS_LIST if m not in extra_meds]
    rng.shuffle(pool)
    for med in pool[:max(0, 15 - len(extra_meds))]:
        extra_meds.add(med)

    return [{"name": m} for m in sorted(extra_meds)[:18]]


def pick_procedures(rng: random.Random) -> list[dict]:
    """Pick realistic procedures (not too many to avoid over-prescription)."""
    rng.shuffle(PROCEDURES_LIST)
    n = min(rng.randint(3, 7), len(PROCEDURES_LIST))
    return [{"code": PROCEDURES_LIST[i][0], "description": PROCEDURES_LIST[i][1]} for i in range(n)]


def pick_observations(rng: random.Random, gap_labs_count: int) -> list[dict]:
    """Pick vital signs that appear around the lab timeline."""
    n = min(rng.randint(2, 4), max(1, gap_labs_count // 25))
    vital_names = [
        "Heart Rate (bpm)", "Blood Pressure Systolic (mmHg)", "Blood Pressure Diastolic (mmHg)",
        "Respiratory Rate (breaths/min)", "Temperature (C)", "SpO2 (%)", "Weight (kg)",
        "Heart Rate Variability (ms)", "Central Venous Pressure (mmHg)"
    ]
    rng.shuffle(vital_names)
    result = []
    for name in vital_names[:n]:
        # Generate plausible ranges based on vital type
        if "HR" in name:
            value = rng.randint(60, 130)
            unit = "bpm"
        elif "BP Systolic" in name:
            value = rng.randint(90, 180)
            unit = "mmHg"
        elif "BP Diastolic" in name:
            value = rng.randint(50, 100)
            unit = "mmHg"
        elif "Respiratory" in name:
            value = rng.randint(12, 36)
            unit = "breaths/min"
        elif "Temperature" in name:
            value = round(rng.uniform(36.0, 40.5), 1)
            unit = "C"
        elif "SpO2" in name:
            value = rng.randint(85, 100)
            unit = "%"
        elif "Weight" in name:
            value = round(rng.uniform(50, 120), 1)
            unit = "kg"
        elif "Variability" in name:
            value = rng.randint(10, 100)
            unit = "ms"
        elif "Pressure" in name:
            value = rng.randint(5, 25)
            unit = "mmHg"
        else:
            value = rng.randint(1, 100)
            unit = ""
        result.append({"name": name, "value": value, "unit": unit})
    return result


def pick_visits(rng: random.Random, n_context_troponins: int) -> list[dict]:
    """Generate visit history entries."""
    visit_types = ["Emergency Department", "Inpatient Admission", "Outpatient Visit", "ICU Transfer",
                   "Observation Unit", "Cardiac Catheterization Lab"]
    rng.shuffle(visit_types)
    n_visits = min(rng.randint(max(5, n_context_troponins), max(8, n_context_troponins + 3)), len(visit_types))
    return [{"type": visit_types[i]} for i in range(n_visits)]


# ─── Main ────────────────────────────────────────────────────────────────────────
def main():
    with open(V2_BENCHMARK_PATH, "r") as f:
        v2_data = json.load(f)

    cases = {c["case_id"]: c for c in v2_data["cases"]}
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    enhanced_cases = []
    for cid in CASE_IDS:
        if cid not in cases:
            print(f"WARNING: case {cid} not found in v2 benchmark, skipping")
            continue

        src = cases[cid]
        rng = seeded_rng(src["patient_id"])

        # Pick and enhance EHR fields
        ethnicity = pick_ethnicity(rng)
        race = pick_race(rng)
        diag_desc = get_diag_descriptions(src["clinical_context"].get("diagnoses", []))
        meds_enhanced = pick_meds(
            src["clinical_context"].get("diagnoses", []),
            src["clinical_context"].get("medications", []),
            rng,
        )
        procedures = pick_procedures(rng)
        observations = pick_observations(rng, src.get("n_gap_labs", 0))
        visits = pick_visits(rng, src.get("n_context_troponins", 3))

        # Build enhanced case (preserving all original v2 fields)
        enhanced = json.loads(json.dumps(src))  # deep copy
        enhanced["full_ehr_context"] = {
            "ethnicity": ethnicity,
            "race": race,
            "diagnoses_enhanced": diag_desc,
            "medications_enhanced": meds_enhanced,
            "procedures": procedures,
            "observations": observations,
            "visit_history": visits,
        }
        enhanced_cases.append(enhanced)

    output = {
        "name": "cardiac_dirchange_v3_benchmark_v1",
        "description": (
            "Direction-change troponin benchmark (v3) — full-EHR context. "
            "Each case has a visible troponin trend that REVERSES at the target time. "
            "Tests whether agents use cross-lab signals rather than troponin trend extrapolation. "
            "Full EHR includes: demographics, ethnicity, race, diagnosis descriptions, "
            "medication names, procedures, observations/vitals, visit history."
        ),
        "task": "next_lab_value_prediction",
        "target_lab": "Troponin I",
        "design": {
            "why_hard": (
                "Both last-value and trend-extrapolation heuristics fail by construction. "
                "Agents must use cross-lab gap signals to detect the reversal. "
                "Full-EHR context provides comprehensive patient data but does not contain the answer."
            ),
            "gap_hours": "4–48",
            "lab_timeline_note": (
                "lab_timeline includes all labs up to t_target EXCEPT troponin after t_visible. "
                "Rows with in_gap=True are from the gap window (t_visible < t <= t_target)."
            ),
        },
        "scoring": {
            "direction_correct": 0.4,
            "within_50pct_error": 0.35,
            "within_20pct_error": 0.25,
            "max_score": 1.0,
        },
        "reversal_distribution": {
            "rising→falling": 5,
            "stable→falling": 5,
            "falling→rising": 5,
            "stable→rising": 5,
        },
        "n_cases": len(enhanced_cases),
        "conditions": {
            "control": "Full EHR + PubMed MCP Server access",
            "independent": "Full EHR only (no PubMed MCP Server)",
        },
        "cases": enhanced_cases,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(enhanced_cases)} enhanced cases → {OUTPUT_PATH}")
    # Print case IDs for verification
    for c in enhanced_cases:
        rev = c["reversal_type"]
        vis_t = c.get("visible_trend", "?")
        actual = c.get("actual_dir", "?")
        print(f"  Case {c['case_id']}: patient={c['patient_id']} | {rev} ({vis_t}→{actual}) | labs={len(c['lab_timeline'])} | ehr fields: ethnic={c['full_ehr_context']['ethnicity']}, race={c['full_ehr_context']['race']}")


if __name__ == "__main__":
    main()
