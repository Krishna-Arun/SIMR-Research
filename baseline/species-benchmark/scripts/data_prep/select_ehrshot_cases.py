"""
select_ehrshot_cases.py

Scans EHRSHOT for CVD patients with clinically significant lab panels —
labs that cross published clinical thresholds and thus have an objective
clinical action associated with them.

These become the raw material for the cross-species translation benchmark.
The "next event" is derived from the clinical threshold crossed (objective),
not from the EHR record (which would require complex medication resolution).

Output: species-benchmark/data/candidate_cases.json
"""

import meds_reader
import itertools
import json
from datetime import timedelta
from pathlib import Path

EHRSHOT_PATH = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/EHRSHOT Hackathon Project/meds_reader_omop_ehrshot")
OUTPUT_PATH  = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/data")
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

# ── LOINC codes for CVD-relevant labs ──────────────────────────────────────────
LAB_LOINC = {
    "creatinine":      "LOINC/2160-0",
    "bun":             "LOINC/3094-0",
    "potassium":       "LOINC/2823-3",
    "sodium":          "LOINC/2951-2",
    "bicarbonate":     "LOINC/1963-8",
    "hemoglobin":      "LOINC/718-7",
    "glucose":         "LOINC/2345-7",
    "cholesterol":     "LOINC/2093-3",
    "ldl":             "LOINC/2089-1",
    "hdl":             "LOINC/2085-9",
    "hba1c":           "LOINC/4548-4",
    "bnp":             "LOINC/42637-9",
    "troponin_i":      "LOINC/10839-9",
    "alt":             "LOINC/1742-6",
    "albumin":         "LOINC/1751-7",
    "calcium":         "LOINC/17861-6",
    "wbc":             "LOINC/6690-2",
    "inr":             "LOINC/6301-6",
    "lactate":         "LOINC/2519-7",
    "phosphorus":      "LOINC/2777-1",
    "magnesium":       "LOINC/2601-3",
    "platelets":       "LOINC/777-3",
    "egfr":            "LOINC/62238-1",
}
LOINC_TO_NAME = {v: k for k, v in LAB_LOINC.items()}

# ── CVD ICD prefixes ────────────────────────────────────────────────────────────
CVD_ICD_PREFIXES = [
    "ICD10CM/I10", "ICD10CM/I11", "ICD10CM/I13", "ICD10CM/I50",
    "ICD10CM/I48", "ICD10CM/I25", "ICD10CM/I21", "ICD10CM/I22",
    "ICD10CM/E11", "ICD10CM/N18",
    "ICD9CM/401",  "ICD9CM/428",  "ICD9CM/427",
]

# ── Clinical thresholds with associated actions ─────────────────────────────────
# Each entry: (lab_name, direction, threshold, action_label, action_detail)
CLINICAL_THRESHOLDS = [
    # Renal / Electrolyte
    ("potassium",    "above", 6.5,  "emergent_rrt",
     "Emergent renal replacement therapy or potassium-binding treatment for life-threatening hyperkalemia"),
    ("potassium",    "below", 3.0,  "potassium_repletion",
     "IV or oral potassium repletion; hold/dose-reduce loop diuretics; evaluate for hypomagnesemia"),
    ("creatinine",   "above", 4.0,  "nephrology_consult",
     "Urgent nephrology consultation; evaluate for RRT initiation"),
    ("bicarbonate",  "below", 15.0, "metabolic_acidosis_workup",
     "Evaluate for cause of metabolic acidosis; consider bicarbonate supplementation or RRT"),
    ("egfr",         "below", 30.0, "ckd_stage4_management",
     "CKD stage 4 protocol: hold/adjust nephrotoxins, ACE/ARB dose reduction, phosphate management"),

    # Cardiac
    ("troponin_i",   "above", 0.5,  "acs_pathway",
     "Acute coronary syndrome pathway: cardiology consult, antiplatelet therapy, consider urgent catheterization"),
    ("bnp",          "above", 400,  "hf_decompensation",
     "Decompensated heart failure: IV diuresis, fluid restriction, consider uptitration of GDMT"),

    # Hematologic
    ("hemoglobin",   "below", 7.0,  "prbc_transfusion",
     "Packed red blood cell transfusion; evaluate for bleeding source"),
    ("inr",          "above", 3.5,  "anticoagulation_reversal",
     "Supratherapeutic anticoagulation: hold anticoagulant, consider reversal agent (Vitamin K or PCC)"),
    ("platelets",    "below", 50.0, "thrombocytopenia_management",
     "Severe thrombocytopenia: hold anticoagulants and antiplatelets, evaluate for cause, consider transfusion if bleeding"),

    # Metabolic
    ("glucose",      "above", 400,  "dka_hhs_protocol",
     "Severe hyperglycemia: insulin infusion protocol, aggressive IV fluids, electrolyte monitoring"),
    ("sodium",       "below", 120,  "severe_hyponatremia",
     "Severe hyponatremia: 3% hypertonic saline at controlled rate; endocrine consult"),
    ("sodium",       "above", 155,  "hypernatremia_correction",
     "Hypernatremia: free water replacement at controlled rate to avoid cerebral edema"),
    ("hba1c",        "above", 9.0,  "diabetes_intensification",
     "Poorly controlled diabetes: intensify antidiabetic regimen, add/increase insulin or GLP-1 agonist"),

    # Lipid / Cardiovascular risk
    ("ldl",          "above", 100,  "statin_intensification",
     "LDL above target in high-risk CVD patient: intensify or initiate statin therapy"),
    ("cholesterol",  "above", 280,  "lipid_treatment",
     "Severely elevated total cholesterol: initiate or intensify lipid-lowering therapy"),
]

def has_cvd_diagnosis(events):
    for e in events:
        if e.table == "condition":
            for prefix in CVD_ICD_PREFIXES:
                if e.code.startswith(prefix):
                    return True
    return False


def extract_cases_for_subject(subject_id, events):
    events = sorted(events, key=lambda e: e.time)

    lab_events  = [e for e in events if e.table == "measurement"
                   and e.numeric_value is not None and e.code in LOINC_TO_NAME]
    cond_events = [e for e in events if e.table == "condition"]
    visit_events= [e for e in events if e.table == "visit"]

    if not lab_events:
        return []

    # Extract demographics from person events
    demographics = {}
    for e in events:
        if e.table == "person":
            if "MEDS_BIRTH" in e.code:
                demographics["birth_year"] = e.time.year
            if e.code.startswith("Gender/"):
                demographics["gender"] = e.code.split("/")[-1]

    # Group labs into visit windows (labs within 3 days of each other)
    visit_windows = []
    if lab_events:
        window = [lab_events[0]]
        for lab_e in lab_events[1:]:
            if (lab_e.time - window[-1].time).days <= 3:
                window.append(lab_e)
            else:
                visit_windows.append(window)
                window = [lab_e]
        visit_windows.append(window)

    diagnoses = list({e.code for e in cond_events})

    cases = []
    for window in visit_windows:
        # Build lab panel for this window
        lab_panel = {}
        for lab_e in window:
            lab_name = LOINC_TO_NAME[lab_e.code]
            if lab_name not in lab_panel:
                lab_panel[lab_name] = {
                    "value": lab_e.numeric_value,
                    "unit":  lab_e.unit,
                    "time":  lab_e.time.isoformat(),
                    "loinc": lab_e.code,
                }

        if len(lab_panel) < 3:
            continue

        # Check which clinical thresholds are crossed
        threshold_hits = []
        for (lab_name, direction, threshold, action_label, action_detail) in CLINICAL_THRESHOLDS:
            if lab_name not in lab_panel:
                continue
            val = lab_panel[lab_name]["value"]
            if direction == "above" and val > threshold:
                threshold_hits.append({
                    "lab":            lab_name,
                    "value":          val,
                    "threshold":      threshold,
                    "direction":      direction,
                    "action_label":   action_label,
                    "action_detail":  action_detail,
                    "z_excess":       round(abs(val - threshold), 2),
                })
            elif direction == "below" and val < threshold:
                threshold_hits.append({
                    "lab":            lab_name,
                    "value":          val,
                    "threshold":      threshold,
                    "direction":      direction,
                    "action_label":   action_label,
                    "action_detail":  action_detail,
                    "z_excess":       round(abs(val - threshold), 2),
                })

        if not threshold_hits:
            continue

        # Pick the most clinically urgent threshold hit as the primary action
        priority_order = [
            "emergent_rrt", "acs_pathway", "severe_hyponatremia",
            "dka_hhs_protocol", "prbc_transfusion", "hf_decompensation",
            "metabolic_acidosis_workup", "anticoagulation_reversal",
            "nephrology_consult", "potassium_repletion",
            "thrombocytopenia_management", "ckd_stage4_management",
            "hypernatremia_correction", "diabetes_intensification",
            "statin_intensification", "lipid_treatment"
        ]
        threshold_hits.sort(key=lambda h: priority_order.index(h["action_label"])
                             if h["action_label"] in priority_order else 99)
        primary_action = threshold_hits[0]

        window_date = window[0].time.isoformat()[:10]
        cases.append({
            "subject_id":       str(subject_id),
            "demographics":     demographics,
            "window_date":      window_date,
            "n_labs":           len(lab_panel),
            "lab_panel":        lab_panel,
            "diagnoses":        diagnoses[:12],
            "primary_action":   primary_action,
            "all_threshold_hits": threshold_hits,
            "n_threshold_hits": len(threshold_hits),
        })

    return cases


def main():
    print("Loading EHRSHOT database...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))
    print(f"Total subjects: {len(db)}")

    all_cases    = []
    processed    = 0
    cvd_subjects = 0

    for subject_id in db:
        subject = db[subject_id]
        events  = list(subject.events)
        processed += 1

        if processed % 1000 == 0:
            print(f"  {processed}/{len(db)} processed | CVD: {cvd_subjects} | cases: {len(all_cases)}")

        if not has_cvd_diagnosis(events):
            continue

        cvd_subjects += 1
        cases = extract_cases_for_subject(subject_id, events)
        all_cases.extend(cases)

    print(f"\nTotal CVD subjects: {cvd_subjects}")
    print(f"Total candidate cases: {len(all_cases)}")

    # Prefer richer panels and cases with more threshold hits
    all_cases.sort(key=lambda c: (c["n_threshold_hits"], c["n_labs"]), reverse=True)

    # Action distribution
    from collections import Counter
    action_counts = Counter(c["primary_action"]["action_label"] for c in all_cases)
    print("\nPrimary action distribution:")
    for action, count in action_counts.most_common():
        print(f"  {action:35s}: {count}")

    output = {
        "n_cvd_subjects":  cvd_subjects,
        "n_cases":         len(all_cases),
        "action_counts":   dict(action_counts),
        "cases":           all_cases,
    }

    outfile = OUTPUT_PATH / "candidate_cases.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(all_cases)} cases to {outfile}")


if __name__ == "__main__":
    main()
