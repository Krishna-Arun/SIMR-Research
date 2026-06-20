"""
prep_cardiac_nextlab_fullehr.py

Full-EHR version of the next-Troponin-I prediction benchmark.

Same 20 patients and same troponin prediction pairs as cardiac_nextlab_benchmark_v1.json,
but each case includes the patient's COMPLETE available EHR context up to the cutoff:
  - All lab measurements (not capped to specific LOINC codes)
  - Full medication history (RxNorm decoded)
  - Full procedure history (CPT4 decoded)
  - Full diagnosis history (ICD-9/10 decoded)
  - Observations (smoking, alcohol, social history)
  - Visit history (encounter types and dates)

Notes are excluded (PHI / prose format).

Output: benchmarks/cardiac-nextlab/output/cardiac_nextlab_fullehr_benchmark_v1.json
"""

import meds_reader
import json
import pandas as pd
from pathlib import Path
from datetime import timedelta, datetime
from collections import defaultdict
import random

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent
EHRSHOT_PATH = REPO_ROOT / "EHRSHOT Hackathon Project" / "meds_reader_omop_ehrshot"
CODES_META   = EHRSHOT_PATH / "metadata" / "codes.parquet"
OUT_DIR      = Path(__file__).parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE     = OUT_DIR / "cardiac_nextlab_fullehr_benchmark_v1.json"

# ── Same patients as cardiac_nextlab_benchmark_v1 ─────────────────────────────
TARGET_SUBJECTS = [
    115967110, 115967114, 115967119, 115967125, 115967128,
    115967129, 115967133, 115967134, 115967140, 115967142,
    115967149, 115967161, 115967163, 115967164, 115967167,
    115967180, 115967189, 115967190, 115967192, 115967227,
]

# ── Troponin ──────────────────────────────────────────────────────────────────
TROPONIN_LOINC      = "LOINC/10839-9"
TROPONIN_URL        = 0.04
SERIAL_WINDOW_HOURS = 48

# ── LOINC lab name mapping (for troponin + known labs) ────────────────────────
LOINC_TO_LABEL = {
    "LOINC/10839-9": "Troponin I",
    "LOINC/2160-0":  "Creatinine",
    "LOINC/3094-0":  "BUN",
    "LOINC/2823-3":  "Potassium",
    "LOINC/2951-2":  "Sodium",
    "LOINC/1963-8":  "Bicarbonate",
    "LOINC/718-7":   "Hemoglobin",
    "LOINC/2345-7":  "Glucose",
    "LOINC/6690-2":  "WBC",
    "LOINC/777-3":   "Platelets",
    "LOINC/6301-6":  "INR",
    "LOINC/17861-6": "Calcium",
    "LOINC/2777-1":  "Phosphorus",
    "LOINC/1751-7":  "Albumin",
    "LOINC/2601-3":  "Magnesium",
    "LOINC/1742-6":  "ALT",
    "LOINC/2519-7":  "Lactate",
    "LOINC/42637-9": "BNP",
    "LOINC/62238-1": "eGFR",
    "LOINC/20570-8": "Hematocrit",
    "LOINC/2075-0":  "Chloride",
    "LOINC/33037-3": "Anion Gap",
    # Vitals
    "LOINC/8867-4":  "Heart Rate",
    "LOINC/8480-6":  "Systolic BP",
    "LOINC/8462-4":  "Diastolic BP",
    "LOINC/2708-6":  "O2 Saturation",
    "LOINC/8310-5":  "Temperature",
    "LOINC/9279-1":  "Respiratory Rate",
    "LOINC/29463-7": "Weight",
    "LOINC/8302-2":  "Height",
}

HUMAN_REF = {
    "Creatinine":      (0.5,  1.2,   "mg/dL"),
    "BUN":             (7.0,  25.0,  "mg/dL"),
    "Potassium":       (3.5,  5.0,   "mEq/L"),
    "Sodium":          (136,  145,   "mEq/L"),
    "Bicarbonate":     (22,   29,    "mEq/L"),
    "Hemoglobin":      (12.0, 17.5,  "g/dL"),
    "Glucose":         (70,   99,    "mg/dL"),
    "WBC":             (4.5,  11.0,  "K/uL"),
    "Platelets":       (150,  400,   "K/uL"),
    "INR":             (0.9,  1.1,   "ratio"),
    "Calcium":         (8.5,  10.5,  "mg/dL"),
    "Phosphorus":      (2.5,  4.5,   "mg/dL"),
    "Albumin":         (3.5,  5.0,   "g/dL"),
    "Magnesium":       (1.7,  2.2,   "mg/dL"),
    "ALT":             (7,    56,    "U/L"),
    "Lactate":         (0.5,  2.0,   "mmol/L"),
    "Troponin I":      (0,    0.04,  "ng/mL"),
    "Hematocrit":      (36,   52,    "%"),
    "Chloride":        (98,   107,   "mEq/L"),
    "eGFR":            (60,   120,   "mL/min/1.73m2"),
    "Anion Gap":       (8,    16,    "mEq/L"),
    "BNP":             (0,    100,   "pg/mL"),
    "Heart Rate":      (60,   100,   "bpm"),
    "Systolic BP":     (90,   140,   "mmHg"),
    "Diastolic BP":    (60,   90,    "mmHg"),
    "O2 Saturation":   (95,   100,   "%"),
    "Temperature":     (36.1, 37.2,  "C"),
    "Respiratory Rate":(12,   20,    "breaths/min"),
}

# Token budget per patient (rough chars, ~4 chars/token)
# For the heavy outlier (115967190 with 1.8M tokens), we cap aggressively
MAX_MEASUREMENT_ROWS = 500   # more generous than the 80-row labs-only cap
MAX_MEASUREMENT_ROWS_HEAVY = 200  # for patients > 50k measurement events
HEAVY_THRESHOLD = 50_000

# ── Load code metadata ─────────────────────────────────────────────────────────
print("Loading code metadata...")
codes_df     = pd.read_parquet(CODES_META)
code_to_desc = dict(zip(codes_df["code"], codes_df["description"]))


def _desc(code: str) -> str:
    """Decode any code to a human-readable description."""
    d = code_to_desc.get(code)
    if d:
        return d.strip()
    # fallback: strip namespace prefix
    return code.split("/")[-1]


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


def _direction(t1_val: float, t2_val: float) -> str:
    if t1_val == 0:
        return "rising" if t2_val > 0 else "stable"
    pct = (t2_val - t1_val) / t1_val
    if pct > 0.20:
        return "rising"
    if pct < -0.20:
        return "falling"
    return "stable"


def build_full_ehr_case(subject_id: int, events: list,
                        t1_time: datetime, t1_value: float,
                        t2_time: datetime, t2_value: float,
                        case_id: int,
                        n_context_troponins: int) -> dict:
    """
    Build one full-EHR benchmark case.
    Everything available in EHRSHOT up to t1_time is included.
    """
    events_sorted = sorted(events, key=lambda e: e.time)
    cutoff        = t1_time  # hard cutoff: nothing after this

    # ── Demographics ──────────────────────────────────────────────────────────
    birth_year, gender = None, "Unknown"
    ethnicity, race = "Unknown", "Unknown"
    for e in events_sorted:
        if e.table == "person":
            if "MEDS_BIRTH" in e.code:
                birth_year = e.time.year
            if e.code.startswith("Gender/"):
                raw = e.code.split("/")[-1]
                gender = "Female" if raw.upper() in ("F", "FEMALE") else "Male"
            if e.code.startswith("Ethnicity/"):
                ethnicity = e.code.split("/", 1)[-1]
            if e.code.startswith("Race/"):
                race = e.code.split("/", 1)[-1]

    age = (t1_time.year - birth_year) if birth_year else 50

    # ── Diagnoses (all ICD codes up to cutoff) ────────────────────────────────
    diagnoses = []
    seen_diag = set()
    for e in events_sorted:
        if e.table != "condition" or e.time > cutoff:
            continue
        desc = _desc(e.code)
        key  = e.code
        if key not in seen_diag:
            seen_diag.add(key)
            diagnoses.append({
                "date": e.time.strftime("%Y-%m-%d"),
                "code": e.code.split("/")[-1],
                "description": desc,
            })

    # ── Medications (all drug_exposure up to cutoff, decoded) ─────────────────
    medications = []
    seen_meds = set()
    for e in events_sorted:
        if e.table != "drug_exposure" or e.time > cutoff:
            continue
        desc = _desc(e.code)
        key  = e.code
        if key not in seen_meds:
            seen_meds.add(key)
            medications.append({
                "date": e.time.strftime("%Y-%m-%d"),
                "code": e.code.split("/")[-1],
                "name": desc,
            })
        else:
            # Still record each date even if same drug
            medications.append({
                "date": e.time.strftime("%Y-%m-%d"),
                "code": e.code.split("/")[-1],
                "name": desc,
            })

    # De-duplicate by (name, date) and sort
    seen_med_pairs = set()
    meds_deduped = []
    for m in medications:
        k = (m["code"], m["date"])
        if k not in seen_med_pairs:
            seen_med_pairs.add(k)
            meds_deduped.append(m)
    medications = sorted(meds_deduped, key=lambda x: x["date"])

    # ── Procedures (CPT4 up to cutoff) ────────────────────────────────────────
    procedures = []
    for e in events_sorted:
        if e.table != "procedure" or e.time > cutoff:
            continue
        if not e.code.startswith("CPT4/") and not e.code.startswith("ICD10PCS/"):
            continue
        procedures.append({
            "date":        e.time.strftime("%Y-%m-%d"),
            "code":        e.code.split("/")[-1],
            "description": _desc(e.code),
        })
    # Deduplicate by (code, date)
    seen_proc = set()
    procs_deduped = []
    for p in procedures:
        k = (p["code"], p["date"])
        if k not in seen_proc:
            seen_proc.add(k)
            procs_deduped.append(p)
    procedures = sorted(procs_deduped, key=lambda x: x["date"])

    # ── Observations (smoking, alcohol, social history) ───────────────────────
    observations = []
    for e in events_sorted:
        if e.table != "observation" or e.time > cutoff:
            continue
        desc = _desc(e.code)
        val  = e.text_value or (str(e.numeric_value) if e.numeric_value is not None else None)
        observations.append({
            "date":  e.time.strftime("%Y-%m-%d"),
            "observation": desc,
            "value": val,
        })
    # Deduplicate
    seen_obs = set()
    obs_deduped = []
    for o in observations:
        k = (o["observation"], o["date"])
        if k not in seen_obs:
            seen_obs.add(k)
            obs_deduped.append(o)
    observations = sorted(obs_deduped, key=lambda x: x["date"])

    # ── Visit history (encounter types up to cutoff) ───────────────────────────
    visits = []
    for e in events_sorted:
        if e.table != "visit" or e.time > cutoff:
            continue
        visits.append({
            "date": e.time.strftime("%Y-%m-%d"),
            "type": _desc(e.code),
        })
    # Deduplicate by (type, date)
    seen_vis = set()
    vis_deduped = []
    for v in visits:
        k = (v["type"], v["date"])
        if k not in seen_vis:
            seen_vis.add(k)
            vis_deduped.append(v)
    visits = sorted(vis_deduped, key=lambda x: x["date"])

    # ── Measurements (labs + vitals) up to cutoff ─────────────────────────────
    # Count total measurement events to decide cap
    total_meas = sum(1 for e in events_sorted
                     if e.table == "measurement" and e.time <= cutoff)
    cap = MAX_MEASUREMENT_ROWS_HEAVY if total_meas > HEAVY_THRESHOLD else MAX_MEASUREMENT_ROWS

    # Separate troponins (always keep all) from other measurements
    troponin_events = [e for e in events_sorted
                       if e.table == "measurement"
                       and e.code == TROPONIN_LOINC
                       and e.time <= cutoff
                       and e.numeric_value is not None]

    other_meas = [e for e in events_sorted
                  if e.table == "measurement"
                  and e.code != TROPONIN_LOINC
                  and e.time <= cutoff
                  and e.numeric_value is not None]

    # For other measurements: all known LOINC codes get priority; unknown get sampled
    known_meas  = [e for e in other_meas if e.code in LOINC_TO_LABEL]
    unknown_meas = [e for e in other_meas if e.code not in LOINC_TO_LABEL]

    # Cap: fill up to `cap` rows with known labs first, then unknown
    remaining = cap - len(troponin_events)
    if len(known_meas) <= remaining:
        selected_other = known_meas + unknown_meas[:max(0, remaining - len(known_meas))]
    else:
        selected_other = known_meas[-remaining:]  # most recent

    all_meas = sorted(troponin_events + selected_other, key=lambda e: e.time)

    lab_timeline = []
    for e in all_meas:
        label = LOINC_TO_LABEL.get(e.code) or _desc(e.code)
        flag  = _flag(label, e.numeric_value)
        lab_timeline.append({
            "datetime": e.time.strftime("%Y-%m-%d %H:%M"),
            "label":    label,
            "code":     e.code,
            "value":    round(e.numeric_value, 4),
            "unit":     e.unit or "",
            "flag":     flag,
        })

    # ── Ground truth ──────────────────────────────────────────────────────────
    direction  = _direction(t1_value, t2_value)
    pct_change = round((t2_value - t1_value) / t1_value * 100, 1) if t1_value else None
    flag_t2    = _flag("Troponin I", t2_value)
    difficulty = "hard" if n_context_troponins == 1 else ("medium" if n_context_troponins == 2 else "easy")

    hours_ahead = round((t2_time - t1_time).total_seconds() / 3600, 1)

    n_trops_in_context = len(troponin_events)
    if n_trops_in_context > 1:
        trop_series_desc = f"{n_trops_in_context} prior Troponin I values visible"
    else:
        trop_series_desc = "1 prior Troponin I value visible"

    # ── Question stem ─────────────────────────────────────────────────────────
    dx_list = "; ".join(d["description"] for d in diagnoses[:10]) or "Not documented"
    stem = (
        f"Patient EHRSHOT subject_id: {subject_id}\n"
        f"Age: {age}  Sex: {gender}  Ethnicity: {ethnicity}\n"
        f"Active diagnoses: {dx_list}\n\n"
        f"The complete EHR data below shows all available information up to "
        f"{t1_time.strftime('%Y-%m-%d %H:%M')} ({trop_series_desc}).\n\n"
        f"Task: Predict the next Troponin I value at "
        f"{t2_time.strftime('%Y-%m-%d %H:%M')} "
        f"({hours_ahead} hours later)."
    )

    return {
        "case_id":    case_id,
        "patient_id": str(subject_id),
        "difficulty": difficulty,
        "n_context_troponins": n_context_troponins,
        "demographics": {
            "age":       age,
            "gender":    gender,
            "ethnicity": ethnicity,
            "race":      race,
        },
        "diagnoses":    diagnoses,
        "medications":  medications,
        "procedures":   procedures,
        "observations": observations,
        "visit_history": visits,
        "lab_timeline": lab_timeline,
        "question": {
            "stem":            stem,
            "target_datetime": t2_time.strftime("%Y-%m-%d %H:%M"),
            "hours_ahead":     hours_ahead,
        },
        "ground_truth": {
            "value":      t2_value,
            "unit":       "ng/mL",
            "flag":       flag_t2,
            "direction":  direction,
            "pct_change": pct_change,
        },
        "data_summary": {
            "n_diagnoses":    len(diagnoses),
            "n_medications":  len(medications),
            "n_procedures":   len(procedures),
            "n_observations": len(observations),
            "n_visits":       len(visits),
            "n_lab_rows":     len(lab_timeline),
            "total_meas_events": total_meas,
            "capped":         total_meas > cap,
        },
    }


def main():
    random.seed(42)

    print(f"Loading EHRSHOT database from {EHRSHOT_PATH}...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))

    cases = []

    for subject_id in TARGET_SUBJECTS:
        subject = db[subject_id]
        events  = list(subject.events)

        # Find the same troponin pair as the labs-only benchmark
        trop_events = sorted(
            [e for e in events
             if e.table == "measurement"
             and e.code == TROPONIN_LOINC
             and e.numeric_value is not None],
            key=lambda e: e.time
        )

        if len(trop_events) < 2:
            print(f"  SKIP {subject_id}: fewer than 2 troponins")
            continue

        if not any(e.numeric_value > TROPONIN_URL for e in trop_events):
            print(f"  SKIP {subject_id}: no elevated troponin")
            continue

        # Enumerate valid consecutive pairs
        valid_pairs = []
        for i in range(len(trop_events) - 1):
            e1, e2 = trop_events[i], trop_events[i + 1]
            gap_hours = (e2.time - e1.time).total_seconds() / 3600
            if gap_hours < 1 or gap_hours > SERIAL_WINDOW_HOURS:
                continue
            if e1.numeric_value == e2.numeric_value:
                continue
            valid_pairs.append((i, e1.time, e1.numeric_value,
                                    e2.time, e2.numeric_value, i + 1))

        if not valid_pairs:
            print(f"  SKIP {subject_id}: no valid consecutive troponin pair")
            continue

        # Same deterministic selection as labs-only benchmark
        rng    = random.Random(int(subject_id))
        chosen = rng.choice(valid_pairs)
        _, t1_time, t1_val, t2_time, t2_val, n_ctx_trops = chosen

        case_id = len(cases) + 1
        case    = build_full_ehr_case(
            subject_id, events,
            t1_time, t1_val,
            t2_time, t2_val,
            case_id, n_ctx_trops
        )
        cases.append(case)

        ds = case["data_summary"]
        print(
            f"  Case {case_id}: subject={subject_id}  difficulty={case['difficulty']}  "
            f"dx={ds['n_diagnoses']}  meds={ds['n_medications']}  "
            f"procs={ds['n_procedures']}  obs={ds['n_observations']}  "
            f"visits={ds['n_visits']}  labs={ds['n_lab_rows']}  "
            f"{'[CAPPED]' if ds['capped'] else ''}"
        )

    benchmark = {
        "name":        "cardiac_nextlab_fullehr_benchmark_v1",
        "description": "Next Troponin I prediction — full EHR context (labs, meds, diagnoses, procedures, observations, visits)",
        "n_cases":     len(cases),
        "cases":       cases,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(benchmark, f, indent=2)

    print(f"\nWrote {OUT_FILE}  ({len(cases)} cases)")

    # Print size summary
    size_mb = OUT_FILE.stat().st_size / 1e6
    print(f"File size: {size_mb:.1f} MB")

    print("\nData summary across cases:")
    print(f"  {'Case':<6} {'Diagnoses':>10} {'Meds':>8} {'Procs':>8} {'Obs':>6} {'Visits':>8} {'Labs':>8} {'Est.Tokens':>12}")
    for c in cases:
        ds  = c["data_summary"]
        est = (ds["n_diagnoses"] * 60 + ds["n_medications"] * 50 +
               ds["n_procedures"] * 60 + ds["n_observations"] * 40 +
               ds["n_visits"] * 30 + ds["n_lab_rows"] * 70) // 4
        print(f"  {c['case_id']:<6} {ds['n_diagnoses']:>10} {ds['n_medications']:>8} "
              f"{ds['n_procedures']:>8} {ds['n_observations']:>6} {ds['n_visits']:>8} "
              f"{ds['n_lab_rows']:>8} {est:>12,}")


if __name__ == "__main__":
    main()
