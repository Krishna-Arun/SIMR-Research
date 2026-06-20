"""
prep_patients_ehrshot.py

Extracts clinically diverse patients from EHRSHOT for the next-event prediction benchmark.
Covers renal, cardiac, hematologic, metabolic, and critical-care scenarios.

Selection criteria:
  1. Patient has a qualifying lab event crossing a clinical severity threshold
  2. Patient has a relevant procedure in the EHR
  3. At least one qualifying lab event precedes the procedure by 1–60 days

Output: benchmarks/patient_data_ehrshot/patient_<subject_id>.json  (full)
        benchmarks/patient_data_ehrshot/patient_<subject_id>_trimmed.json  (masked)
"""

import meds_reader
import json
import pandas as pd
from pathlib import Path
from datetime import timedelta, datetime
from collections import defaultdict

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent
EHRSHOT_PATH = REPO_ROOT / "EHRSHOT Hackathon Project" / "meds_reader_omop_ehrshot"
CODES_META   = EHRSHOT_PATH / "metadata" / "codes.parquet"
OUT_DIR      = Path(__file__).parent / "patient_data_ehrshot"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── LOINC lab code mapping ────────────────────────────────────────────────────
LAB_LOINC = {
    "Creatinine":  "LOINC/2160-0",
    "BUN":         "LOINC/3094-0",
    "Potassium":   "LOINC/2823-3",
    "Sodium":      "LOINC/2951-2",
    "Bicarbonate": "LOINC/1963-8",
    "Hemoglobin":  "LOINC/718-7",
    "Glucose":     "LOINC/2345-7",
    "WBC":         "LOINC/6690-2",
    "Platelets":   "LOINC/777-3",
    "INR":         "LOINC/6301-6",
    "Calcium":     "LOINC/17861-6",
    "Phosphorus":  "LOINC/2777-1",
    "Albumin":     "LOINC/1751-7",
    "Magnesium":   "LOINC/2601-3",
    "ALT":         "LOINC/1742-6",
    "Lactate":     "LOINC/2519-7",
    "Troponin I":  "LOINC/10839-9",
    "BNP":         "LOINC/42637-9",
    "eGFR":        "LOINC/62238-1",
    "Hematocrit":  "LOINC/20570-8",
    "Chloride":    "LOINC/2075-0",
    "Anion Gap":   "LOINC/33037-3",
    "HDL":         "LOINC/2085-9",
    "LDL":         "LOINC/2089-1",
    "Cholesterol": "LOINC/2093-3",
    "HbA1c":       "LOINC/4548-4",
}
LOINC_TO_LABEL = {v: k for k, v in LAB_LOINC.items()}

# ── Human reference ranges (for flag computation) ─────────────────────────────
HUMAN_REF = {
    "Creatinine":  (0.5,  1.2,   "mg/dL"),
    "BUN":         (7.0,  25.0,  "mg/dL"),
    "Potassium":   (3.5,  5.0,   "mEq/L"),
    "Sodium":      (136,  145,   "mEq/L"),
    "Bicarbonate": (22,   29,    "mEq/L"),
    "Hemoglobin":  (12.0, 17.5,  "g/dL"),
    "Glucose":     (70,   99,    "mg/dL"),
    "WBC":         (4.5,  11.0,  "K/uL"),
    "Platelets":   (150,  400,   "K/uL"),
    "INR":         (0.9,  1.1,   "ratio"),
    "Calcium":     (8.5,  10.5,  "mg/dL"),
    "Phosphorus":  (2.5,  4.5,   "mg/dL"),
    "Albumin":     (3.5,  5.0,   "g/dL"),
    "Magnesium":   (1.7,  2.2,   "mg/dL"),
    "ALT":         (7,    56,    "U/L"),
    "Lactate":     (0.5,  2.0,   "mmol/L"),
    "Troponin I":  (0,    0.04,  "ng/mL"),
    "Hematocrit":  (36,   52,    "%"),
    "Chloride":    (98,   107,   "mEq/L"),
    "eGFR":        (60,   120,   "mL/min/1.73m2"),
    "Anion Gap":   (8,    16,    "mEq/L"),
    "HDL":         (40,   60,    "mg/dL"),
    "LDL":         (0,    100,   "mg/dL"),
    "Cholesterol": (0,    200,   "mg/dL"),
    "HbA1c":       (4.0,  5.6,   "%"),
    "BNP":         (0,    100,   "pg/mL"),
}

# ── Cardiac clinical triggers ─────────────────────────────────────────────────
# Each entry: (loinc_code, direction, threshold, action_label, action_readable)
ALL_TRIGGERS = [
    # Troponin I elevation → ACS → cardiac catheterization / PCI
    ("LOINC/10839-9", "above", 0.5,  "acs_high_risk",   "Emergent Cardiac Catheterization / PCI (High-Risk ACS)"),
    ("LOINC/10839-9", "above", 0.04, "acs_workup",      "Urgent Cardiac Catheterization for ACS"),
    # BNP elevation → decompensated heart failure → cardiac evaluation / right heart cath
    ("LOINC/42637-9", "above", 900,  "hf_severe",       "Right Heart Catheterization for Severe Heart Failure"),
    ("LOINC/42637-9", "above", 400,  "hf_decompensated","Cardiac Evaluation for Decompensated Heart Failure"),
]

# Set of all LOINC codes that are triggers — used for fast membership testing
TRIGGER_LOINC_SET = {t[0] for t in ALL_TRIGGERS}

# ── Qualifying cardiac procedure codes ───────────────────────────────────────
# Each entry: CPT4 code → (readable_name, category_label)
PROCEDURE_CODES = {
    # Left / right heart catheterization
    "CPT4/93454": ("Left Heart Catheterization",                            "acs_pathway"),
    "CPT4/93455": ("Left Heart Catheterization with Coronary Angiography",  "acs_pathway"),
    "CPT4/93456": ("Right and Left Heart Catheterization",                  "acs_pathway"),
    "CPT4/93457": ("Right and Left Heart Catheterization with Angiography", "acs_pathway"),
    "CPT4/93458": ("Left Heart Catheterization with Left Ventriculography", "acs_pathway"),
    "CPT4/93459": ("Left Heart Catheterization with Coronary Angiography and Left Ventriculography", "acs_pathway"),
    # PCI / PTCA / stent
    "CPT4/92920": ("Percutaneous Transluminal Coronary Angioplasty",        "acs_pathway"),
    "CPT4/92928": ("Percutaneous Coronary Intervention with Stent",         "acs_pathway"),
    "CPT4/92980": ("Coronary Stent Placement",                              "acs_pathway"),
    # Right heart catheterization for HF hemodynamics
    "CPT4/93501": ("Right Heart Catheterization",                           "hf_pathway"),
    "CPT4/93503": ("Right Heart Catheterization with Balloon Flotation",    "hf_pathway"),
}

# All unique procedure CPT4 codes
PROC_CODE_SET = set(PROCEDURE_CODES.keys())

# Labs to mask in the trimmed file — agent must retrieve these via MCP tools
# Focused on cardiac decision-critical values
MASK_LABS = {
    "Troponin I",  # primary ACS decision driver
    "BNP",         # primary HF decision driver
    "Hemoglobin",  # anemia in ACS affects management
    "Creatinine",  # cardiorenal syndrome / contrast risk
    "Potassium",   # electrolyte critical pre-cath
    "INR",         # anticoagulation status pre-procedure
    "Glucose",     # metabolic control pre-procedure
    "Lactate",     # cardiogenic shock indicator
}

# Constrain which procedures count as valid evidence for each cardiac action.
ACTION_PREFERRED_PROCS: dict[str, set[str]] = {
    "acs_high_risk": {"CPT4/93454", "CPT4/93455", "CPT4/93456", "CPT4/93457",
                      "CPT4/93458", "CPT4/93459",
                      "CPT4/92920", "CPT4/92928", "CPT4/92980"},
    "acs_workup":    {"CPT4/93454", "CPT4/93455", "CPT4/93456", "CPT4/93457",
                      "CPT4/93458", "CPT4/93459",
                      "CPT4/92920", "CPT4/92928", "CPT4/92980"},
    "hf_severe":      {"CPT4/93501", "CPT4/93503",
                       "CPT4/93454", "CPT4/93455", "CPT4/93456"},
    "hf_decompensated":{"CPT4/93501", "CPT4/93503",
                        "CPT4/93454", "CPT4/93455", "CPT4/93456"},
}

TARGET_N         = 20   # aim for up to 20 cardiac cases
MAX_PER_ACTION   = 20   # no effective cap — maximize cases found
PROC_WINDOW_DAYS = 60   # look for procedure up to 60 days after trigger lab

# ── Load code descriptions (for drug names, visit types) ─────────────────────
print("Loading code metadata...")
codes_df = pd.read_parquet(CODES_META)
code_to_desc = dict(zip(codes_df["code"], codes_df["description"]))


# ── ICD-10 descriptions ───────────────────────────────────────────────────────
_ICD_LOOKUP = {
    # ── ICD-9 codes (pre-2015 Stanford patients) ──────────────────────────────
    # Cardiovascular
    "401.9":  "Essential hypertension, unspecified",
    "410.01": "Anterior wall AMI, initial episode",
    "410.11": "Inferior wall AMI, initial episode",
    "410.90": "AMI, unspecified site, initial episode",
    "411.1":  "Intermediate coronary syndrome (unstable angina)",
    "413.9":  "Angina pectoris, unspecified",
    "414.00": "Coronary atherosclerosis, unspecified vessel",
    "414.01": "Coronary atherosclerosis of native coronary artery",
    "414.9":  "Chronic ischemic heart disease, unspecified",
    "424.0":  "Mitral valve disorders",
    "424.1":  "Aortic valve disorders",
    "424.90": "Endocarditis, unspecified",
    "427.31": "Atrial fibrillation",
    "427.32": "Atrial flutter",
    "427.89": "Other specified cardiac dysrhythmia",
    "428.0":  "Congestive heart failure, unspecified",
    "428.20": "Systolic heart failure, unspecified",
    "428.30": "Diastolic heart failure, unspecified",
    # Renal
    "584.9":  "Acute kidney failure, unspecified",
    "585.1":  "Chronic kidney disease, Stage I",
    "585.2":  "Chronic kidney disease, Stage II",
    "585.3":  "Chronic kidney disease, Stage III",
    "585.4":  "Chronic kidney disease, Stage IV",
    "585.5":  "Chronic kidney disease, Stage V",
    "585.6":  "End-stage renal disease",
    # Hematologic
    "280.9":  "Iron deficiency anemia, unspecified",
    "281.0":  "Pernicious anemia",
    "285.9":  "Anemia, unspecified",
    "286.6":  "Defibrination syndrome (DIC)",
    "287.5":  "Thrombocytopenia, unspecified",
    # Metabolic / endocrine
    "250.00": "Diabetes mellitus type 2, uncomplicated",
    "250.01": "Diabetes mellitus type 1, uncomplicated",
    "250.10": "Diabetic ketoacidosis, type 2",
    "250.11": "Diabetic ketoacidosis, type 1",
    "276.0":  "Hyperosmolality",
    "276.1":  "Hyponatremia",
    "276.7":  "Hyperpotassemia (hyperkalemia)",
    "276.8":  "Hypopotassemia (hypokalemia)",
    "272.0":  "Pure hypercholesterolemia",
    "272.4":  "Other and unspecified hyperlipidemia",
    # Respiratory
    "486":    "Pneumonia, unspecified organism",
    "491.21": "Obstructive chronic bronchitis with acute exacerbation",
    "496":    "Chronic airway obstruction (COPD), not elsewhere classified",
    "518.81": "Acute respiratory failure",
    "518.82": "Acute and chronic respiratory failure",
    # Sepsis / infectious
    "995.91": "Sepsis",
    "995.92": "Severe sepsis",
    "785.52": "Septic shock",
    "038.9":  "Unspecified septicemia",
    # Coagulation / anticoagulation
    "286.5":  "Hemorrhagic disorder due to intrinsic circulating anticoagulants",
    "790.92": "Abnormal coagulation profile",
    # GI
    "530.81": "Esophageal reflux (GERD)",
    "564.00": "Constipation, unspecified",
    "578.9":  "Hemorrhage of gastrointestinal tract, unspecified",
    # Other
    "300.00": "Anxiety state, unspecified",
    "311":    "Depressive disorder",
    "365.9":  "Glaucoma, unspecified",
    "V58.61": "Long-term (current) use of anticoagulants",
    # ── ICD-10 codes ──────────────────────────────────────────────────────────
    # Renal
    "N17.9":  "Acute kidney failure, unspecified",
    "N17.0":  "Acute kidney failure with tubular necrosis",
    "N17.1":  "Acute kidney failure with acute cortical necrosis",
    "N18.1":  "Chronic kidney disease, stage 1",
    "N18.2":  "Chronic kidney disease, stage 2",
    "N18.3":  "Chronic kidney disease, stage 3",
    "N18.4":  "Chronic kidney disease, stage 4",
    "N18.5":  "Chronic kidney disease, stage 5",
    "N18.6":  "End-stage renal disease",
    # Electrolyte / metabolic
    "E87.2":  "Acidosis",
    "E87.20": "Acidosis, unspecified",
    "E87.21": "Acute metabolic acidosis",
    "E87.5":  "Hyperkalemia",
    "E87.6":  "Hypokalemia",
    "E87.0":  "Hyperosmolality and hypernatremia",
    "E87.1":  "Hypo-osmolality and hyponatremia",
    "E86.0":  "Dehydration",
    # Cardiac
    "I10":    "Essential (primary) hypertension",
    "I21.9":  "Acute myocardial infarction, unspecified",
    "I21.11": "ST elevation (STEMI) myocardial infarction involving RCA",
    "I21.19": "ST elevation (STEMI) myocardial infarction, other",
    "I25.10": "Coronary artery disease, native coronary artery",
    "I50.9":  "Heart failure, unspecified",
    "I50.22": "Chronic systolic heart failure",
    "I50.32": "Chronic diastolic heart failure",
    "I47.2":  "Ventricular tachycardia",
    "I48.0":  "Paroxysmal atrial fibrillation",
    "I48.11": "Longstanding persistent atrial fibrillation",
    # Hematologic
    "D62":    "Acute posthemorrhagic anemia",
    "D64.9":  "Anemia, unspecified",
    "D69.6":  "Thrombocytopenia, unspecified",
    "D65":    "Disseminated intravascular coagulation",
    "D61.818":"Other pancytopenia",
    # Metabolic / endocrine
    "E11.9":  "Type 2 diabetes mellitus without complications",
    "E11.65": "Type 2 diabetes mellitus with hyperglycemia",
    "E13.10": "Other specified diabetes with ketoacidosis without coma",
    "E11.10": "Type 2 diabetes mellitus with ketoacidosis without coma",
    "E83.51": "Hypocalcemia",
    # Sepsis / infectious
    "A41.9":  "Sepsis, unspecified organism",
    "A41.51": "Sepsis due to Escherichia coli",
    "J18.9":  "Pneumonia, unspecified organism",
    "J96.01": "Acute respiratory failure with hypoxia",
    # Other
    "I10":    "Essential (primary) hypertension",
    "K57.30": "Diverticulosis of large intestine without perforation or abscess",
    "K52.9":  "Noninfective gastroenteritis and colitis, unspecified",
    "R50.81": "Fever presenting with conditions classified elsewhere",
    "R80.8":  "Other proteinuria",
    "F25.9":  "Schizoaffective disorder, unspecified",
}


def _icd_desc(code: str) -> str:
    # Try parquet description first (covers ICD-9 and ICD-10 both)
    parquet_desc = code_to_desc.get(code)
    if parquet_desc:
        return parquet_desc.strip()
    raw = code.split("/")[-1]
    return _ICD_LOOKUP.get(raw, raw)


def _flag(label: str, value: float) -> str | None:
    ref = HUMAN_REF.get(label)
    if ref is None or value is None:
        return None
    lo, hi, _ = ref
    if value < lo:
        return "low"
    if value > hi:
        return "abnormal"
    return None


def _ref_bounds(label: str):
    ref = HUMAN_REF.get(label)
    if ref is None:
        return None, None
    return str(ref[0]), str(ref[1])


def _unit(label: str, event_unit: str | None) -> str:
    ref = HUMAN_REF.get(label)
    return (event_unit or (ref[2] if ref else "")) or ""


def _drug_name(code: str) -> str | None:
    desc = code_to_desc.get(code)
    if desc:
        return desc.strip()
    if code.startswith("STANFORD_SHC_DRUG/"):
        return code.split("/")[-1]
    if code.startswith("RxNorm/"):
        return f"Medication ({code.split('/')[-1]})"
    return None


def _severity_score(val: float, direction: str, threshold: float) -> float:
    """Normalized deviation from threshold — allows ranking across different lab types."""
    if direction == "above":
        return (val - threshold) / threshold
    else:
        return (threshold - val) / threshold


def build_patient(subject_id: int, events: list, trigger_time: datetime,
                  trigger_action: str, trigger_readable: str,
                  proc_code: str, proc_time: datetime) -> dict:
    """Build the patient_data JSON from EHRSHOT events."""

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

    trigger_year = trigger_time.year
    age = (trigger_year - birth_year) if birth_year else 50

    # ── Visits grouped by visit_id ────────────────────────────────────────────
    visit_events: dict[str, list] = defaultdict(list)
    for e in events_sorted:
        if e.visit_id:
            visit_events[e.visit_id].append(e)

    visit_order = sorted(visit_events.keys(),
                         key=lambda vid: min(e.time for e in visit_events[vid]))

    # Find the visit that contains the trigger lab event
    trigger_visit_id = None
    min_delta = timedelta(days=9999)
    for e in events_sorted:
        if e.table == "measurement" and e.code in TRIGGER_LOINC_SET:
            if e.numeric_value is not None:
                delta = abs(e.time - trigger_time)
                if delta < min_delta:
                    min_delta = delta
                    trigger_visit_id = e.visit_id

    # Fallback: visit whose window straddles trigger_time
    if trigger_visit_id is None:
        for vid in visit_order:
            evts = visit_events[vid]
            t_min = min(e.time for e in evts)
            t_max = max(e.time for e in evts)
            if t_min <= trigger_time <= t_max + timedelta(days=1):
                trigger_visit_id = vid
                break

    prior_visits = [vid for vid in visit_order if vid != trigger_visit_id]

    def _diagnoses_for_visit(vid: str) -> list[str]:
        codes = [e.code for e in visit_events.get(vid, []) if e.table == "condition"]
        names = [_icd_desc(c) for c in codes]
        return list(dict.fromkeys(names))[:8]

    def _meds_for_visit(vid: str) -> list[str]:
        drug_codes = [e.code for e in visit_events.get(vid, []) if e.table == "drug_exposure"]
        names = []
        for c in drug_codes:
            n = _drug_name(c)
            if n and not n.startswith("Medication ("):
                names.append(n)
        return list(dict.fromkeys(names))[:15]

    def _visit_type(vid: str) -> str:
        for e in visit_events.get(vid, []):
            if e.table == "visit":
                desc = code_to_desc.get(e.code, e.code)
                if "inpatient" in desc.lower():
                    return "Inpatient"
                if "emergency" in desc.lower() or "emergent" in desc.lower():
                    return "Emergency"
                if "outpatient" in desc.lower():
                    return "Outpatient"
        return "Inpatient"

    # ── Prior admission history ───────────────────────────────────────────────
    history = []
    for vid in prior_visits[-5:]:
        evts = visit_events[vid]
        t_min = min(e.time for e in evts).date().isoformat()
        t_max = max(e.time for e in evts).date().isoformat()
        history.append({
            "admit_date":           t_min,
            "discharge_date":       t_max,
            "admission_type":       _visit_type(vid),
            "diagnoses":            _diagnoses_for_visit(vid),
            "procedures_performed": [],
            "medications":          _meds_for_visit(vid),
        })

    # ── Current admission ─────────────────────────────────────────────────────
    if trigger_visit_id and trigger_visit_id in visit_events:
        cur_evts  = visit_events[trigger_visit_id]
        cur_admit = min(e.time for e in cur_evts).date().isoformat()
    else:
        cur_admit = trigger_time.date().isoformat()

    current_admission = {
        "admit_date":        cur_admit,
        "admission_type":    "Inpatient",
        "admission_location":"Emergency Department",
        "diagnoses":         _diagnoses_for_visit(trigger_visit_id) if trigger_visit_id else [],
        "medications":       _meds_for_visit(trigger_visit_id) if trigger_visit_id else [],
    }

    # ── Lab data around the trigger event (±3 days) ───────────────────────────
    window_start = trigger_time - timedelta(days=3)
    window_end   = trigger_time + timedelta(days=1)

    seen_labs: set = set()
    lab_data: list[dict] = []
    for e in events_sorted:
        if e.table != "measurement":
            continue
        if e.code not in LOINC_TO_LABEL:
            continue
        if not (window_start <= e.time <= window_end):
            continue
        if e.numeric_value is None:
            continue
        label   = LOINC_TO_LABEL[e.code]
        date_str = e.time.date().isoformat()
        key      = (label, date_str)
        if key in seen_labs:
            continue
        seen_labs.add(key)
        ref_lo, ref_hi = _ref_bounds(label)
        lab_data.append({
            "date":      date_str,
            "label":     label,
            "value":     str(round(e.numeric_value, 2)),
            "flag":      _flag(label, e.numeric_value),
            "ref_lower": ref_lo,
            "ref_upper": ref_hi,
        })

    lab_data.sort(key=lambda x: (x["date"], x["label"]))

    proc_name = PROCEDURE_CODES[proc_code][0]

    return {
        "patient_id": str(subject_id),
        "action_label": trigger_action,
        "patient_context": {
            "demographics": {
                "age":    age,
                "gender": gender,
            },
            "admission_history": history,
            "current_admission": current_admission,
        },
        "lab_data":               lab_data,
        "ground_truth_procedure": proc_name,
        "ground_truth_action":    trigger_readable,
    }


def build_trimmed(full: dict) -> dict:
    """Mask decision-critical labs as '___'; add clinical guidelines context."""
    import copy
    trimmed = copy.deepcopy(full)
    for lab in trimmed["lab_data"]:
        if lab["label"] in MASK_LABS:
            lab["value"] = "___"
    trimmed["guidelines_context"] = (
        "ACC/AHA Clinical Guidelines — Cardiac Next-Event Prediction Context: "
        "ACS (Acute Coronary Syndrome): troponin elevation above the 99th percentile URL (0.04 ng/mL) "
        "with ischemic symptoms constitutes NSTEMI. High-risk features (troponin > 0.5 ng/mL, dynamic "
        "ECG changes, hemodynamic instability, GRACE score > 140) warrant urgent invasive strategy "
        "(cardiac catheterization ± PCI) within 24h (ACC/AHA 2014 NSTEMI guidelines). STEMI with "
        "persistent ST elevation or new LBBB → primary PCI within 90 min of first medical contact. "
        "Heart Failure: BNP > 400 pg/mL strongly supports heart failure diagnosis. Decompensated HF "
        "with refractory symptoms or cardiogenic shock → hemodynamic assessment via right heart "
        "catheterization (Swan-Ganz). Cardiogenic shock (MAP < 65, CI < 1.8, PCWP > 18) may indicate "
        "need for mechanical circulatory support. "
        "Use all available lab data to identify the most urgent cardiac procedure."
    )
    return trimmed


def main():
    print(f"Loading EHRSHOT database from {EHRSHOT_PATH}...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))
    print(f"Total subjects: {len(db)}")

    # candidates: (subject_id, trigger_time, action_label, action_readable,
    #              proc_code, proc_time, severity_score, events)
    candidates = []

    processed = 0
    for subject_id in db:
        subject = db[subject_id]
        events  = list(subject.events)
        processed += 1
        if processed % 1000 == 0:
            print(f"  {processed}/{len(db)} scanned | candidates: {len(candidates)}")

        # ── 1. Collect all qualifying lab events (per trigger definition) ──────
        trigger_hits: list[tuple[datetime, float, str, str, str]] = []
        for e in events:
            if e.table != "measurement" or e.numeric_value is None:
                continue
            if e.code not in TRIGGER_LOINC_SET:
                continue
            for loinc, direction, threshold, action_label, action_readable in ALL_TRIGGERS:
                if e.code != loinc:
                    continue
                val = e.numeric_value
                triggered = (
                    (direction == "above" and val > threshold) or
                    (direction == "below" and val < threshold)
                )
                if triggered:
                    sev = _severity_score(val, direction, threshold)
                    trigger_hits.append((e.time, sev, action_label, action_readable, loinc))

        if not trigger_hits:
            continue

        # ── 2. Collect procedure events ───────────────────────────────────────
        proc_events = [e for e in events
                       if e.table == "procedure" and e.code in PROC_CODE_SET]
        if not proc_events:
            continue

        # ── 3. Find best (trigger_time, proc_time) pair with 1–60 day gap ─────
        # Require the procedure to be appropriate for the trigger's action_label.
        # Sort trigger hits by severity descending; pick highest-severity aligned pair.
        best_candidate = None
        best_sev = -1.0
        for t_time, sev, action_label, action_readable, loinc in sorted(
                trigger_hits, key=lambda x: -x[1]):
            allowed_procs = ACTION_PREFERRED_PROCS.get(action_label, PROC_CODE_SET)
            for pe in proc_events:
                if pe.code not in allowed_procs:
                    continue
                gap = (pe.time - t_time).days
                if 1 <= gap <= PROC_WINDOW_DAYS:
                    if sev > best_sev:
                        best_sev = sev
                        best_candidate = (t_time, action_label, action_readable,
                                          pe.code, pe.time)

        if best_candidate is None:
            continue

        trigger_t, action_label, action_readable, proc_code, proc_t = best_candidate
        candidates.append((subject_id, trigger_t, action_label, action_readable,
                           proc_code, proc_t, best_sev, events))

    print(f"\nFound {len(candidates)} qualifying patients")

    # ── 4. Select diverse, high-severity cases ────────────────────────────────
    # Sort by severity score descending; cap per action_label for diversity
    candidates.sort(key=lambda x: -x[6])
    per_action: dict[str, int] = defaultdict(int)
    selected = []
    for cand in candidates:
        _, _, action_label, _, _, _, _, _ = cand
        if per_action[action_label] >= MAX_PER_ACTION:
            continue
        per_action[action_label] += 1
        selected.append(cand)
        if len(selected) >= TARGET_N:
            break

    print(f"\nSelected {len(selected)} cases:")
    for sid, trig_t, action_label, action_readable, pc, pt, sev, _ in selected:
        proc_name = PROCEDURE_CODES[pc][0]
        print(f"  subject={sid}  severity={sev:.2f}  action={action_label}"
              f"  procedure={proc_name}  lab_date={trig_t.date()}  proc_date={pt.date()}")

    print(f"\nAction distribution:")
    for action, count in sorted(per_action.items(), key=lambda x: -x[1]):
        print(f"  {action}: {count}")

    # ── 5. Build and write patient JSONs ──────────────────────────────────────
    for sid, trigger_t, action_label, action_readable, pc, pt, _, events in selected:
        full    = build_patient(sid, events, trigger_t, action_label, action_readable, pc, pt)
        trimmed = build_trimmed(full)

        full_path    = OUT_DIR / f"patient_{sid}.json"
        trimmed_path = OUT_DIR / f"patient_{sid}_trimmed.json"

        with open(full_path, "w") as f:
            json.dump(full, f, indent=2)
        with open(trimmed_path, "w") as f:
            json.dump(trimmed, f, indent=2)

        print(f"Wrote {full_path.name} ({len(full['lab_data'])} labs, "
              f"{len(full['patient_context']['admission_history'])} prior visits, "
              f"action={action_label})")


if __name__ == "__main__":
    main()
