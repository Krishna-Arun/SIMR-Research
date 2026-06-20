"""
prep_cardiac_nextlab.py

Extracts cardiac patients from EHRSHOT for the next-lab-value prediction benchmark.

Task: Given a patient's full lab timeline up to (and including) an initial elevated
Troponin I measurement, predict the value of the NEXT Troponin I measurement.

Selection criteria:
  1. Patient has at least one Troponin I > 0.04 ng/mL (above URL — abnormal)
  2. Patient has a second Troponin I measurement within 48 hours of the first
  3. The two measurements must differ (not an exact duplicate)

Output: benchmarks/cardiac-nextlab/output/cardiac_nextlab_benchmark_v1.json
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
OUT_DIR      = Path(__file__).parent / "output"
CASES_DIR    = OUT_DIR / "cardiac_nextlab_cases"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CASES_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE     = OUT_DIR / "cardiac_nextlab_benchmark_v1.json"

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
}
LOINC_TO_LABEL = {v: k for k, v in LAB_LOINC.items()}

TROPONIN_LOINC = "LOINC/10839-9"
TROPONIN_URL   = 0.04   # 99th percentile upper reference limit (ng/mL)

# ── Human reference ranges ────────────────────────────────────────────────────
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
    "BNP":         (0,    100,   "pg/mL"),
}

TARGET_N = 20   # aim for up to 20 benchmark cases
SERIAL_WINDOW_HOURS = 48  # consecutive troponin pair must be within 48h

# ── Load code descriptions ────────────────────────────────────────────────────
print("Loading code metadata...")
codes_df = pd.read_parquet(CODES_META)
code_to_desc = dict(zip(codes_df["code"], codes_df["description"]))

# ── ICD lookup (ICD-9 + ICD-10) ──────────────────────────────────────────────
_ICD_LOOKUP = {
    # ICD-9
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
    "428.0":  "Congestive heart failure, unspecified",
    "428.20": "Systolic heart failure, unspecified",
    "250.00": "Diabetes mellitus type 2, uncomplicated",
    "272.0":  "Pure hypercholesterolemia",
    "272.4":  "Other and unspecified hyperlipidemia",
    "496":    "COPD",
    "585.1":  "Chronic kidney disease, Stage I",
    "585.3":  "Chronic kidney disease, Stage III",
    "585.5":  "Chronic kidney disease, Stage V",
    "530.81": "Esophageal reflux (GERD)",
    "300.00": "Anxiety state, unspecified",
    "311":    "Depressive disorder",
    "V58.61": "Long-term use of anticoagulants",
    # ICD-10
    "I21.9":  "Acute myocardial infarction, unspecified",
    "I21.11": "STEMI involving right coronary artery",
    "I21.19": "STEMI, other site",
    "I25.10": "Coronary artery disease, native coronary artery",
    "I50.9":  "Heart failure, unspecified",
    "I48.0":  "Paroxysmal atrial fibrillation",
    "I10":    "Essential (primary) hypertension",
    "N17.9":  "Acute kidney failure, unspecified",
    "N18.3":  "Chronic kidney disease, stage 3",
    "E11.9":  "Type 2 diabetes mellitus without complications",
    "A41.9":  "Sepsis, unspecified organism",
}


def _icd_desc(code: str) -> str:
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


def _drug_name(code: str) -> str | None:
    desc = code_to_desc.get(code)
    if desc:
        return desc.strip()
    if code.startswith("STANFORD_SHC_DRUG/"):
        return code.split("/")[-1]
    return None


def build_case(subject_id: int, events: list,
               t1_time: datetime, t1_value: float,
               t2_time: datetime, t2_value: float,
               case_id: int,
               n_context_troponins: int) -> dict:
    """
    Build one benchmark case.
    t1: context cutoff — the troponin the model sees last (index i in the series)
    t2: prediction target — the next troponin (index i+1)
    n_context_troponins: how many troponins are visible in context (1 = only t1)
    difficulty: hard (1 trop seen), medium (2), easy (3+)
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

    age = (t1_time.year - birth_year) if birth_year else 50

    # ── Build lab timeline up to and including t1 (context) ─────────────────
    # Keep all Troponin I readings (always relevant) + last 90 days of other labs.
    # Cap at 80 total rows so the prompt stays within context limits.
    cutoff_90d = t1_time - timedelta(days=90)

    seen_labs: set = set()
    lab_timeline: list[dict] = []
    for e in events_sorted:
        if e.table != "measurement":
            continue
        if e.code not in LOINC_TO_LABEL:
            continue
        if e.numeric_value is None:
            continue
        if e.time > t1_time:
            continue   # only show data up to the cutoff

        label    = LOINC_TO_LABEL[e.code]
        is_trop  = (e.code == TROPONIN_LOINC)

        # Keep all troponin I values; for other labs, only last 90 days
        if not is_trop and e.time < cutoff_90d:
            continue

        date_str = e.time.date().isoformat()
        time_str = e.time.strftime("%Y-%m-%dT%H:%M")
        key      = (label, time_str)
        if key in seen_labs:
            continue
        seen_labs.add(key)

        ref = HUMAN_REF.get(label, (None, None, ""))
        lab_timeline.append({
            "datetime":  time_str,
            "date":      date_str,
            "label":     label,
            "value":     round(e.numeric_value, 3),
            "unit":      e.unit or ref[2] or "",
            "flag":      _flag(label, e.numeric_value),
            "ref_lower": str(ref[0]) if ref[0] is not None else "",
            "ref_upper": str(ref[1]) if ref[1] is not None else "",
        })

    lab_timeline.sort(key=lambda x: (x["datetime"], x["label"]))

    # Hard cap: keep at most 80 rows (always preserve all troponins).
    # If over limit, drop oldest non-troponin rows first.
    if len(lab_timeline) > 80:
        trops   = [x for x in lab_timeline if x["label"] == "Troponin I"]
        others  = [x for x in lab_timeline if x["label"] != "Troponin I"]
        others  = others[-(80 - len(trops)):]   # keep newest non-trop rows
        lab_timeline = sorted(trops + others, key=lambda x: (x["datetime"], x["label"]))

    # ── Clinical context (diagnoses, medications from most recent visit) ──────
    visit_events: dict[str, list] = defaultdict(list)
    for e in events_sorted:
        if e.visit_id and e.time <= t1_time:
            visit_events[e.visit_id].append(e)

    visit_order = sorted(visit_events.keys(),
                         key=lambda vid: min(e.time for e in visit_events[vid]))

    # Current visit = the one containing t1
    current_visit_id = None
    min_delta = timedelta(days=9999)
    for e in events_sorted:
        if e.table == "measurement" and e.code == TROPONIN_LOINC:
            if e.numeric_value is not None and abs(e.time - t1_time) < min_delta:
                min_delta = abs(e.time - t1_time)
                current_visit_id = e.visit_id

    def _diagnoses(vid: str) -> list[str]:
        codes = [e.code for e in visit_events.get(vid, []) if e.table == "condition"]
        names = [_icd_desc(c) for c in codes]
        return list(dict.fromkeys(names))[:8]

    def _meds(vid: str) -> list[str]:
        names = []
        for e in visit_events.get(vid, []):
            if e.table != "drug_exposure":
                continue
            n = _drug_name(e.code)
            if n and not n.startswith("Medication ("):
                names.append(n)
        return list(dict.fromkeys(names))[:12]

    diagnoses  = _diagnoses(current_visit_id) if current_visit_id else []
    medications = _meds(current_visit_id) if current_visit_id else []

    # Prior troponin values in the timeline (for trend context)
    prior_troponins = [
        {"datetime": x["datetime"], "value": x["value"], "unit": x["unit"], "flag": x["flag"]}
        for x in lab_timeline if x["label"] == "Troponin I"
    ]

    # Troponin direction label for human reference (not given to agent)
    pct_change = ((t2_value - t1_value) / t1_value) * 100 if t1_value > 0 else 0
    if t2_value > t1_value * 1.20:
        direction = "rising"
    elif t2_value < t1_value * 0.80:
        direction = "falling"
    else:
        direction = "stable"

    hours_between = (t2_time - t1_time).total_seconds() / 3600

    if n_context_troponins == 1:
        difficulty = "hard"
    elif n_context_troponins == 2:
        difficulty = "medium"
    else:
        difficulty = "easy"

    # ── Build question stem ───────────────────────────────────────────────────
    trop_series_desc = (
        f"{n_context_troponins} prior Troponin I value(s) visible in context"
        if n_context_troponins > 0 else "no prior Troponin I values"
    )
    question_stem = (
        f"Patient subject_id: {subject_id}\n\n"
        f"A {age}-year-old {gender} presents with chest symptoms. "
        f"Current diagnoses: {'; '.join(diagnoses) if diagnoses else 'not recorded'}. "
        f"Current medications: {', '.join(medications[:6]) if medications else 'not recorded'}.\n\n"
        f"The lab timeline below shows all available measurements up to "
        f"{t1_time.strftime('%Y-%m-%d %H:%M')} ({trop_series_desc}).\n\n"
        f"The next Troponin I measurement is scheduled for "
        f"{t2_time.strftime('%Y-%m-%d %H:%M')} "
        f"({hours_between:.1f} hours after the most recent measurement).\n\n"
        f"Based on this patient's lab history and clinical context, "
        f"predict the Troponin I value at {t2_time.strftime('%Y-%m-%d %H:%M')}."
    )

    return {
        "case_id":    case_id,
        "patient_id": str(subject_id),
        "difficulty":  difficulty,   # hard / medium / easy
        "n_context_troponins": n_context_troponins,
        "demographics": {"age": age, "gender": gender},
        "clinical_context": {
            "diagnoses":   diagnoses,
            "medications": medications,
        },
        "lab_timeline":    lab_timeline,
        "context_cutoff":  t1_time.strftime("%Y-%m-%dT%H:%M"),
        "troponin_series": prior_troponins,  # all troponins in context
        "question": {
            "stem": question_stem,
            "target_lab":      "Troponin I",
            "target_datetime": t2_time.strftime("%Y-%m-%dT%H:%M"),
            "hours_ahead":     round(hours_between, 1),
        },
        "ground_truth": {
            "lab_name":    "Troponin I",
            "datetime":    t2_time.strftime("%Y-%m-%dT%H:%M"),
            "value":       round(t2_value, 3),
            "unit":        "ng/mL",
            "flag":        _flag("Troponin I", t2_value),
            "direction":   direction,
            "pct_change":  round(pct_change, 1),
        },
        "scoring_guide": {
            "direction_correct":  0.40,  # rising / falling / stable within ±20%
            "within_50pct_error": 0.35,  # |predicted - actual| / actual ≤ 0.50
            "within_20pct_error": 0.25,  # |predicted - actual| / actual ≤ 0.20
            "max_score":          1.00,
            "note": (
                "Score = direction_correct (0.4 if direction matches, else 0) + "
                "within_50pct (0.35 if |error| ≤ 50%, else 0) + "
                "within_20pct (0.25 if |error| ≤ 20%, else 0). Max = 1.0."
            ),
        },
    }


def main():
    import random
    random.seed(42)   # reproducible

    print(f"Loading EHRSHOT database from {EHRSHOT_PATH}...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))
    print(f"Total subjects: {len(db)}")

    cases = []
    processed = 0

    for subject_id in db:
        subject = db[subject_id]
        events  = list(subject.events)
        processed += 1
        if processed % 1000 == 0:
            print(f"  {processed}/{len(db)} scanned | cases: {len(cases)}")

        # ── Collect all Troponin I measurements (sorted) ──────────────────────
        trop_events = sorted(
            [e for e in events
             if e.table == "measurement"
             and e.code == TROPONIN_LOINC
             and e.numeric_value is not None],
            key=lambda e: e.time
        )

        if len(trop_events) < 2:
            continue

        # Require at least one elevated troponin (this is a cardiac ACS patient)
        if not any(e.numeric_value > TROPONIN_URL for e in trop_events):
            continue

        # ── Find all valid consecutive pairs (gap 1h–48h, different values) ──
        valid_pairs = []
        for i in range(len(trop_events) - 1):
            e1, e2 = trop_events[i], trop_events[i + 1]
            gap_hours = (e2.time - e1.time).total_seconds() / 3600
            if gap_hours < 1 or gap_hours > SERIAL_WINDOW_HOURS:
                continue
            if e1.numeric_value == e2.numeric_value:
                continue
            # Record: (context_index i, t1, t1_val, t2, t2_val, n_context_trops)
            # n_context_troponins = i+1 (trops[0..i] all visible in context)
            valid_pairs.append((i, e1.time, e1.numeric_value,
                                    e2.time, e2.numeric_value, i + 1))

        if not valid_pairs:
            continue

        # ── Randomly sample one pair (deterministic per subject) ─────────────
        # Seed with subject_id so each patient always picks the same step
        rng = random.Random(int(subject_id))
        chosen = rng.choice(valid_pairs)
        _, t1_time, t1_val, t2_time, t2_val, n_ctx_trops = chosen

        case_id = len(cases) + 1
        case = build_case(subject_id, events,
                          t1_time, t1_val,
                          t2_time, t2_val,
                          case_id, n_ctx_trops)
        cases.append(case)

        print(f"  Case {case_id}: subject={subject_id}  "
              f"ctx_trops={n_ctx_trops}  difficulty={case['difficulty']}  "
              f"Trop@context={t1_val:.3f}  Target={t2_val:.3f}  "
              f"direction={case['ground_truth']['direction']}  "
              f"labs={len(case['lab_timeline'])}")

        if len(cases) >= TARGET_N:
            break

    print(f"\nTotal cases: {len(cases)}")

    direction_dist = {}
    for c in cases:
        d = c["ground_truth"]["direction"]
        direction_dist[d] = direction_dist.get(d, 0) + 1
    print(f"Direction distribution: {direction_dist}")

    benchmark = {
        "name":        "cardiac_nextlab_benchmark_v1",
        "description": (
            "Next-lab-value prediction benchmark for cardiac patients from EHRSHOT. "
            "Given a patient's complete lab timeline up to an initial elevated Troponin I, "
            "predict the value of the next serial Troponin I measurement."
        ),
        "task":        "next_lab_value_prediction",
        "target_lab":  "Troponin I",
        "scoring": {
            "direction_correct":  0.40,
            "within_50pct_error": 0.35,
            "within_20pct_error": 0.25,
            "max_score":          1.00,
        },
        "n_cases": len(cases),
        "cases":   cases,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(benchmark, f, indent=2)

    print(f"\nWrote {OUT_FILE}  ({len(cases)} cases)")


if __name__ == "__main__":
    main()
