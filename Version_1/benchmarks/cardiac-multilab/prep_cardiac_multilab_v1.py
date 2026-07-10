#!/usr/bin/env python3
"""
prep_cardiac_multilab_v1.py

Builds 100-case next-troponin benchmark with:
  - Full EHR context (all EHRSHOT tables) up to T_target
  - Troponin series visible only up to T_visible (4-48h before T_target)
  - Other labs (creatinine, Hgb, BNP, lactate...) visible in the gap
  - 50/50 mix: 50 cases with 1 visible troponin (hard), 50 with 2+ visible (medium/easy)

Output:
  benchmarks/cardiac-multilab/output/multilab_v1/case_NNN.json  (one file per case)
  benchmarks/cardiac-multilab/output/cardiac_multilab_benchmark_v1.json  (manifest)
"""

import json
import random
from pathlib import Path
from collections import defaultdict

import meds_reader

# ── Paths ──────────────────────────────────────────────────────────────────────
EHRSHOT_PATH = Path("EHRSHOT Hackathon Project/meds_reader_omop_ehrshot")
OUTPUT_DIR   = Path("../output/multilab_v1")
MANIFEST     = Path("../output/cardiac_multilab_benchmark_v1.json")

# ── Constants ──────────────────────────────────────────────────────────────────
GAP_MIN_HOURS = 4
GAP_MAX_HOURS = 48
MAX_LAB_ROWS  = 500   # cap on measurement rows per case
TARGET_CASES  = 100
RANDOM_SEED   = 42

# Troponin codes
TROP_CODES = {
    'LOINC/10839-9': 'Troponin I',
    'LOINC/42757-5': 'Troponin I',
    'LOINC/49563-0': 'Troponin I',
    'LOINC/6598-7':  'Troponin I',
    'LOINC/89579-7': 'Troponin I',
    'LOINC/6597-9':  'Troponin T',
}

# Labs that provide signal in the gap window
GAP_SIGNAL_CODES = {
    'LOINC/2160-0',   # Creatinine
    'LOINC/3094-0',   # BUN
    'LOINC/42637-9',  # BNP
    'LOINC/30934-4',  # BNP
    'LOINC/33762-6',  # NT-proBNP
    'LOINC/718-7',    # Hemoglobin
    'LOINC/4544-3',   # Hematocrit
    'LOINC/2519-9',   # Lactate
    'LOINC/32693-4',  # Lactate
    'LOINC/2823-3',   # Potassium
    'LOINC/6690-2',   # WBC
    'LOINC/1988-5',   # CRP
    'LOINC/75241-0',  # Procalcitonin
    'LOINC/8867-4',   # Heart Rate
    'LOINC/8480-6',   # Systolic BP
}

# Cardiac diagnosis codes
CARDIAC_CODES = [
    'ICD10CM/I21', 'ICD10CM/I22', 'ICD10CM/I24', 'ICD10CM/I20',
    'ICD10CM/I25', 'ICD10CM/I50', 'ICD10CM/I42', 'ICD10CM/I47',
    'ICD9CM/410',  'ICD9CM/411',  'ICD9CM/413',
    'ICD9CM/414',  'ICD9CM/428',  'ICD9CM/402',
]

# Full lab name mapping
LOINC_LABELS = {
    'LOINC/2160-0':  'Creatinine',        'LOINC/3094-0':  'BUN',
    'LOINC/2823-3':  'Potassium',         'LOINC/2951-2':  'Sodium',
    'LOINC/1963-8':  'Bicarbonate',       'LOINC/718-7':   'Hemoglobin',
    'LOINC/4544-3':  'Hematocrit',        'LOINC/6690-2':  'WBC',
    'LOINC/777-3':   'Platelets',         'LOINC/6301-6':  'INR',
    'LOINC/5902-2':  'PT',                'LOINC/2345-7':  'Glucose',
    'LOINC/17861-6': 'Calcium',           'LOINC/2777-1':  'Phosphorus',
    'LOINC/1751-7':  'Albumin',           'LOINC/1742-6':  'ALT',
    'LOINC/1920-8':  'AST',               'LOINC/6768-6':  'Alk Phosphatase',
    'LOINC/1975-2':  'Total Bilirubin',   'LOINC/3040-3':  'Lipase',
    'LOINC/1988-5':  'CRP',               'LOINC/75241-0': 'Procalcitonin',
    'LOINC/42637-9': 'BNP',              'LOINC/30934-4': 'BNP',
    'LOINC/33762-6': 'NT-proBNP',        'LOINC/2519-9':  'Lactate',
    'LOINC/32693-4': 'Lactate',          'LOINC/10839-9': 'Troponin I',
    'LOINC/42757-5': 'Troponin I',       'LOINC/49563-0': 'Troponin I',
    'LOINC/6598-7':  'Troponin I',       'LOINC/89579-7': 'Troponin I',
    'LOINC/6597-9':  'Troponin T',       'LOINC/8310-5':  'Temperature',
    'LOINC/8867-4':  'Heart Rate',       'LOINC/9279-1':  'Resp Rate',
    'LOINC/2708-6':  'O2 Sat',           'LOINC/59408-5': 'SpO2',
    'LOINC/8480-6':  'Systolic BP',      'LOINC/8462-4':  'Diastolic BP',
    'LOINC/29463-7': 'Weight',           'LOINC/8302-2':  'Height',
    'LOINC/4548-4':  'HbA1c',            'LOINC/2532-2':  'LDH',
    'LOINC/14631-6': 'LDH',              'LOINC/2157-6':  'CK',
    'LOINC/2154-3':  'CK-MB',            'LOINC/13969-1': 'CK-MB',
    'LOINC/3016-3':  'TSH',              'LOINC/3051-0':  'Free T4',
    'LOINC/2106-3':  'eGFR',             'LOINC/33914-3': 'eGFR',
    'LOINC/1558-6':  'Fasting Glucose',  'LOINC/6299-2':  'BUN/Creatinine',
    'LOINC/2498-6':  'Phosphate',        'LOINC/1989-3':  'Vitamin D',
    'LOINC/14979-9': 'PTT',              'LOINC/5895-7':  'PTT',
    'LOINC/3255-7':  'Fibrinogen',       'LOINC/48058-2': 'D-Dimer',
    'LOINC/48065-7': 'D-Dimer',          'LOINC/34714-6': 'INR',
}

def fmt_time(t):
    return t.strftime('%Y-%m-%d %H:%M') if t else ''

def hours_between(t1, t2):
    return (t2 - t1).total_seconds() / 3600

def direction(v_before, v_after):
    if v_before <= 0:
        return 'rising' if v_after > 0 else 'stable'
    delta = (v_after - v_before) / v_before
    if delta > 0.20:  return 'rising'
    if delta < -0.20: return 'falling'
    return 'stable'

def is_cardiac(events):
    for e in events:
        if any(e.code.startswith(c) for c in CARDIAC_CODES):
            return True
    return False

def get_trop_series(events):
    """Return sorted list of (time, value) for troponin measurements with numeric values."""
    series = []
    for e in events:
        if e.code in TROP_CODES and e.numeric_value is not None and e.numeric_value >= 0:
            series.append((e.time, float(e.numeric_value), TROP_CODES[e.code]))
    return sorted(series, key=lambda x: x[0])

def find_best_window(trop_series):
    """
    Find the best (T_visible_idx, T_target_idx) pair:
    - At least 1 troponin visible before T_visible (visible_idx >= 0)
    - Gap 4-48h
    Returns None if no valid window found.
    """
    candidates = []
    for target_idx in range(1, len(trop_series)):
        for visible_idx in range(0, target_idx):
            t_visible = trop_series[visible_idx][0]
            t_target  = trop_series[target_idx][0]
            gap_h     = hours_between(t_visible, t_target)
            if GAP_MIN_HOURS <= gap_h <= GAP_MAX_HOURS:
                candidates.append((visible_idx, target_idx, gap_h))
    return candidates

def score_window(visible_idx, target_idx, trop_series, gap_signal_events):
    """Score a candidate window — higher is better."""
    t_visible = trop_series[visible_idx][0]
    t_target  = trop_series[target_idx][0]
    v_visible = trop_series[visible_idx][1]
    v_target  = trop_series[target_idx][1]
    gap_h     = hours_between(t_visible, t_target)

    # How hard is the last-value heuristic? (higher = harder)
    lv_err = abs(v_target - v_visible) / v_target if v_target > 0 else (1.0 if v_target != v_visible else 0.0)

    # Number of gap signal labs
    n_gap_labs = sum(
        1 for e in gap_signal_events
        if t_visible < e.time <= t_target and e.code in GAP_SIGNAL_CODES
    )

    # Prefer: more gap labs, harder last-value error, moderate gap duration
    score = n_gap_labs * 3 + lv_err * 2 + (1.0 if 6 <= gap_h <= 24 else 0.5)
    return score, n_gap_labs, lv_err

def extract_all_ehr(subject, t_target, t_visible, trop_series, visible_idx):
    """
    Extract full EHR up to t_target.
    - Measurements: all labs up to t_target, BUT troponin masked after t_visible
    - Conditions, meds, procs, obs, visits: all up to t_target
    """
    events = list(subject.events)

    # ── Measurements ──────────────────────────────────────────────────────────
    measurements = []
    for e in events:
        if e.table != 'measurement': continue
        if e.time > t_target: continue
        is_trop = e.code in TROP_CODES
        # Mask troponin readings after t_visible
        if is_trop and e.time > t_visible: continue
        val = e.numeric_value
        if val is None: continue
        label = LOINC_LABELS.get(e.code, e.code.split('/')[-1])
        measurements.append({
            'datetime': fmt_time(e.time),
            'label':    label,
            'value':    round(float(val), 4),
            'unit':     e.unit or '',
            'flag':     None,
            'is_trop':  is_trop,
        })
    measurements.sort(key=lambda x: x['datetime'])
    # Cap at MAX_LAB_ROWS (keep most recent)
    if len(measurements) > MAX_LAB_ROWS:
        measurements = measurements[-MAX_LAB_ROWS:]

    # ── Conditions / Diagnoses ────────────────────────────────────────────────
    diagnoses = []
    for e in events:
        if e.table != 'condition': continue
        if e.time > t_target: continue
        diagnoses.append({
            'date': fmt_time(e.time),
            'code': e.code,
            'description': e.text_value or e.code,
        })
    diagnoses.sort(key=lambda x: x['date'])

    # ── Medications ───────────────────────────────────────────────────────────
    medications = []
    for e in events:
        if e.table != 'drug_exposure': continue
        if e.time > t_target: continue
        name = e.text_value or e.code
        medications.append({'date': fmt_time(e.time), 'name': name, 'code': e.code})
    medications.sort(key=lambda x: x['date'])

    # ── Procedures ────────────────────────────────────────────────────────────
    procedures = []
    for e in events:
        if e.table != 'procedure': continue
        if e.time > t_target: continue
        procedures.append({
            'date': fmt_time(e.time),
            'code': e.code,
            'description': e.text_value or e.code,
        })
    procedures.sort(key=lambda x: x['date'])

    # ── Observations ──────────────────────────────────────────────────────────
    observations = []
    for e in events:
        if e.table != 'observation': continue
        if e.time > t_target: continue
        observations.append({
            'date': fmt_time(e.time),
            'observation': e.text_value or e.code,
            'value': str(e.numeric_value) if e.numeric_value is not None else None,
        })
    observations.sort(key=lambda x: x['date'])

    # ── Visit history ─────────────────────────────────────────────────────────
    visits = []
    for e in events:
        if e.table not in ('visit', 'visit_detail'): continue
        if e.time > t_target: continue
        visits.append({
            'date': fmt_time(e.time),
            'type': e.text_value or e.code,
        })
    visits.sort(key=lambda x: x['date'])

    # ── Troponin context series (visible only) ─────────────────────────────────
    trop_context = [
        {'datetime': fmt_time(t), 'value': round(v, 4), 'label': lbl}
        for t, v, lbl in trop_series[:visible_idx + 1]
    ]

    # ── Gap labs (for metadata / scoring) ────────────────────────────────────
    gap_labs = []
    for e in events:
        if e.time <= t_visible or e.time > t_target: continue
        if e.code in GAP_SIGNAL_CODES and e.numeric_value is not None:
            gap_labs.append({
                'datetime': fmt_time(e.time),
                'label': LOINC_LABELS.get(e.code, e.code),
                'value': round(float(e.numeric_value), 4),
                'unit': e.unit or '',
            })
    gap_labs.sort(key=lambda x: x['datetime'])

    return {
        'lab_timeline':   measurements,
        'diagnoses':      diagnoses,
        'medications':    medications,
        'procedures':     procedures,
        'observations':   observations,
        'visit_history':  visits,
        'trop_context':   trop_context,
        'gap_labs':       gap_labs,
    }

def make_question_stem(patient_id, t_visible, t_target, trop_context, gap_h):
    last_trop = trop_context[-1]
    return (
        f"Patient EHRSHOT subject_id: {patient_id}\n"
        f"Last known Troponin I: {last_trop['value']} ng/mL at {last_trop['datetime']}\n"
        f"Troponin measurements are NOT available after {fmt_time(t_visible)}.\n"
        f"All other labs (creatinine, Hgb, BNP, etc.) are available up to {fmt_time(t_target)}.\n"
        f"Predict Troponin I at: {fmt_time(t_target)} ({gap_h:.1f}h after last known troponin)"
    )

def main():
    random.seed(RANDOM_SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading EHRSHOT from {EHRSHOT_PATH} ...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))

    # ── Phase 1: Scan all patients ─────────────────────────────────────────────
    print("Scanning patients for cardiac dx + troponin series ...")
    candidates = []  # (subject_id, visible_idx, target_idx, score, meta)

    for i, subject_id in enumerate(db):
        if i % 500 == 0:
            print(f"  {i}/6731 scanned, {len(candidates)} candidates so far ...")

        subject = db[subject_id]
        events  = list(subject.events)

        if not is_cardiac(events):
            continue

        trop_series = get_trop_series(events)
        if len(trop_series) < 2:
            continue

        windows = find_best_window(trop_series)
        if not windows:
            continue

        # Score each window and keep the best
        best = None
        for vis_idx, tgt_idx, gap_h in windows:
            sc, n_gap_labs, lv_err = score_window(vis_idx, tgt_idx, trop_series, events)
            if best is None or sc > best[0]:
                best = (sc, vis_idx, tgt_idx, gap_h, n_gap_labs, lv_err)

        sc, vis_idx, tgt_idx, gap_h, n_gap_labs, lv_err = best
        t_visible = trop_series[vis_idx][0]
        t_target  = trop_series[tgt_idx][0]
        v_visible = trop_series[vis_idx][1]
        v_target  = trop_series[tgt_idx][1]
        dir_label = direction(v_visible, v_target)

        candidates.append({
            'subject_id':  subject_id,
            'visible_idx': vis_idx,   # 0 = only 1 troponin visible (hard)
            'target_idx':  tgt_idx,
            'score':       sc,
            'gap_h':       gap_h,
            'n_gap_labs':  n_gap_labs,
            'lv_err':      lv_err,
            'direction':   dir_label,
            'actual_value': v_target,
            'last_visible': v_visible,
            't_visible':   t_visible,
            't_target':    t_target,
            'trop_series': trop_series,
        })

    print(f"\nTotal candidates: {len(candidates)}")

    # Breakdown
    from collections import Counter
    dir_counts = Counter(c['direction'] for c in candidates)
    n1_count = sum(1 for c in candidates if c['visible_idx'] == 0)
    print(f"  rising={dir_counts['rising']}  falling={dir_counts['falling']}  stable={dir_counts['stable']}")
    print(f"  single-visible (hard)={n1_count}  multi-visible (medium/easy)={len(candidates)-n1_count}")

    # ── Phase 2: Sample 100 balanced cases (50/50 single vs multi visible) ────
    # Split into two pools: single visible (visible_idx==0) and multi visible
    single_pool = [c for c in candidates if c['visible_idx'] == 0]
    multi_pool  = [c for c in candidates if c['visible_idx'] > 0]

    def sample_balanced(pool, n_total):
        """Sample n_total from pool, balanced ~33/33/34 across directions, top-scored."""
        by_dir = {'rising': [], 'falling': [], 'stable': []}
        for c in pool:
            by_dir[c['direction']].append(c)
        for d in by_dir:
            by_dir[d].sort(key=lambda x: x['score'], reverse=True)
        per_dir = {'rising': n_total // 3 + (1 if n_total % 3 > 0 else 0),
                   'falling': n_total // 3 + (1 if n_total % 3 > 1 else 0),
                   'stable':  n_total // 3}
        result = []
        for d, n in per_dir.items():
            take = min(n, len(by_dir[d]))
            result.extend(by_dir[d][:take])
            print(f"    {d}: took {take}/{len(by_dir[d])}")
        return result

    print(f"\nSampling 50 single-visible (hard) cases:")
    single_selected = sample_balanced(single_pool, 50)
    print(f"Sampling 50 multi-visible (medium/easy) cases:")
    multi_selected  = sample_balanced(multi_pool, 50)

    selected = single_selected + multi_selected
    random.shuffle(selected)
    # Reassign case_ids after shuffle (done in phase 3)

    print(f"\nFinal: {len(selected)} cases selected")
    dir_final = Counter(c['direction'] for c in selected)
    vis_final = Counter('single' if c['visible_idx'] == 0 else 'multi' for c in selected)
    print(f"  rising={dir_final['rising']}  falling={dir_final['falling']}  stable={dir_final['stable']}")
    print(f"  single-visible={vis_final['single']}  multi-visible={vis_final['multi']}")

    # ── Phase 3: Extract full EHR and write case files ────────────────────────
    print("\nExtracting full EHR for each case ...")
    manifest_cases = []

    for case_id, cand in enumerate(selected, start=1):
        sid        = cand['subject_id']
        vis_idx    = cand['visible_idx']
        tgt_idx    = cand['target_idx']
        trop_series = cand['trop_series']
        t_visible  = cand['t_visible']
        t_target   = cand['t_target']
        gap_h      = cand['gap_h']

        subject = db[sid]
        ehr     = extract_all_ehr(subject, t_target, t_visible, trop_series, vis_idx)

        v_target  = trop_series[tgt_idx][1]
        v_visible = trop_series[vis_idx][1]
        dir_label = direction(v_visible, v_target)
        n_ctx     = vis_idx + 1  # number of visible troponins

        # Difficulty: hard=1 visible troponin, medium=2, easy=3+
        if n_ctx == 1:   diff = 'hard'
        elif n_ctx == 2: diff = 'medium'
        else:            diff = 'easy'

        question_stem = make_question_stem(sid, t_visible, t_target, ehr['trop_context'], gap_h)

        case = {
            'case_id':    case_id,
            'patient_id': str(sid),
            'difficulty': diff,
            'n_ctx_trops': n_ctx,
            'gap_hours':  round(gap_h, 1),
            'n_gap_labs': cand['n_gap_labs'],
            'last_value_heuristic_error_pct': round(cand['lv_err'] * 100, 1),
            'question': {
                'stem':             question_stem,
                'target_datetime':  fmt_time(t_target),
                'last_trop_time':   fmt_time(t_visible),
                'hours_ahead':      round(gap_h, 1),
            },
            'ground_truth': {
                'value':     round(v_target, 4),
                'direction': dir_label,
                'last_visible_value': round(v_visible, 4),
            },
            'trop_context':   ehr['trop_context'],
            'gap_labs':       ehr['gap_labs'],
            'lab_timeline':   ehr['lab_timeline'],
            'diagnoses':      ehr['diagnoses'],
            'medications':    ehr['medications'],
            'procedures':     ehr['procedures'],
            'observations':   ehr['observations'],
            'visit_history':  ehr['visit_history'],
            'data_summary': {
                'n_lab_rows':    len(ehr['lab_timeline']),
                'n_diagnoses':   len(ehr['diagnoses']),
                'n_medications': len(ehr['medications']),
                'n_procedures':  len(ehr['procedures']),
                'n_observations':len(ehr['observations']),
                'n_visits':      len(ehr['visit_history']),
                'n_gap_labs':    len(ehr['gap_labs']),
            },
        }

        # Write individual case file
        case_path = OUTPUT_DIR / f"case_{case_id:03d}.json"
        with open(case_path, 'w') as f:
            json.dump(case, f, indent=2)

        manifest_cases.append({
            'case_id':    case_id,
            'patient_id': str(sid),
            'difficulty': diff,
            'n_ctx_trops': n_ctx,
            'gap_hours':  round(gap_h, 1),
            'n_gap_labs': cand['n_gap_labs'],
            'lv_err_pct': round(cand['lv_err'] * 100, 1),
            'actual_value': round(v_target, 4),
            'actual_dir':   dir_label,
            'file': str(case_path),
        })

        if case_id % 10 == 0:
            print(f"  [{case_id:3d}/100] patient={sid} dir={dir_label} gap={gap_h:.1f}h "
                  f"gap_labs={cand['n_gap_labs']} lv_err={cand['lv_err']*100:.0f}% "
                  f"dx={len(ehr['diagnoses'])} meds={len(ehr['medications'])} "
                  f"labs={len(ehr['lab_timeline'])}")

    # ── Phase 4: Write manifest ────────────────────────────────────────────────
    manifest = {
        'name':        'cardiac_multilab_v1',
        'description': 'Next Troponin I prediction with masked last value — forces multi-lab reasoning',
        'n_cases':     len(manifest_cases),
        'design': {
            'task':           'predict masked troponin value',
            'masking':        'last troponin hidden; all other labs visible up to target time',
            'gap_hours':      f'{GAP_MIN_HOURS}–{GAP_MAX_HOURS}',
            'gap_signal_labs': list(GAP_SIGNAL_CODES),
            'max_lab_rows':   MAX_LAB_ROWS,
        },
        'scoring': {
            'direction_weight': 0.40,
            'within_50pct':     0.35,
            'within_20pct':     0.25,
            'note': 'last-value heuristic (predict stable at last troponin) is NOT a valid baseline here',
        },
        'direction_distribution': dict(Counter(c['actual_dir'] for c in manifest_cases)),
        'difficulty_distribution': dict(Counter(c['difficulty'] for c in manifest_cases)),
        'cases': manifest_cases,
    }

    with open(MANIFEST, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone!")
    print(f"  Cases:    {OUTPUT_DIR}/case_NNN.json")
    print(f"  Manifest: {MANIFEST}")

    # Print summary stats
    lv_errs = [c['lv_err_pct'] for c in manifest_cases]
    gap_labs = [c['n_gap_labs'] for c in manifest_cases]
    print(f"\nCase stats:")
    print(f"  Last-value error — mean={sum(lv_errs)/len(lv_errs):.0f}%  "
          f"median={sorted(lv_errs)[len(lv_errs)//2]:.0f}%  "
          f"min={min(lv_errs):.0f}%  max={max(lv_errs):.0f}%")
    print(f"  Gap signal labs  — mean={sum(gap_labs)/len(gap_labs):.1f}  "
          f"median={sorted(gap_labs)[len(gap_labs)//2]}  "
          f"min={min(gap_labs)}  max={max(gap_labs)}")
    print(f"  Direction: {dict(Counter(c['actual_dir'] for c in manifest_cases))}")
    print(f"  Difficulty: {dict(Counter(c['difficulty'] for c in manifest_cases))}")

if __name__ == '__main__':
    main()
