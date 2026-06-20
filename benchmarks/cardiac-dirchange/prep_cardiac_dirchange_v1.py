#!/usr/bin/env python3
"""
prep_cardiac_dirchange_v1.py

Builds a benchmark of DIRECTION-CHANGE cases:
  - The visible troponin trend (last 2+ readings) goes one direction
  - The actual troponin at T_target reverses that trend
  - Both trend-extrapolation AND last-value heuristics fail by definition
  - Model must use cross-lab signal (BNP, creatinine, vitals, meds) to detect the reversal

Examples of direction-change cases:
  - Troponin was FALLING (post-ACS clearance) → rises again (reinfarction, new injury)
  - Troponin was RISING (acute phase) → falls faster than expected (rapid clearance, intervention)
  - Troponin was STABLE → suddenly rising or falling

Output:
  benchmarks/cardiac-dirchange/output/case_NNN.json
  benchmarks/cardiac-dirchange/output/cardiac_dirchange_benchmark_v1.json
"""

import json
import random
from pathlib import Path
from collections import Counter

import meds_reader

# ── Paths ──────────────────────────────────────────────────────────────────────
EHRSHOT_PATH = Path("EHRSHOT Hackathon Project/meds_reader_omop_ehrshot")
OUTPUT_DIR   = Path("../output/cardiac-dirchange")
MANIFEST     = Path("../output/cardiac_dirchange_benchmark_v1.json")

# ── Constants ──────────────────────────────────────────────────────────────────
GAP_MIN_HOURS = 4
GAP_MAX_HOURS = 48
MAX_LAB_ROWS  = 500
TARGET_CASES  = 100
RANDOM_SEED   = 42

TROP_CODES = {
    'LOINC/10839-9': 'Troponin I',
    'LOINC/42757-5': 'Troponin I',
    'LOINC/49563-0': 'Troponin I',
    'LOINC/6598-7':  'Troponin I',
    'LOINC/89579-7': 'Troponin I',
    'LOINC/6597-9':  'Troponin T',
}

GAP_SIGNAL_CODES = {
    'LOINC/2160-0', 'LOINC/3094-0',   # Creatinine, BUN
    'LOINC/42637-9', 'LOINC/30934-4', 'LOINC/33762-6',  # BNP, NT-proBNP
    'LOINC/718-7', 'LOINC/4544-3',    # Hemoglobin, Hematocrit
    'LOINC/2519-9', 'LOINC/32693-4',  # Lactate
    'LOINC/2823-3', 'LOINC/6690-2',   # Potassium, WBC
    'LOINC/1988-5', 'LOINC/75241-0',  # CRP, Procalcitonin
    'LOINC/8867-4', 'LOINC/8480-6',   # Heart Rate, Systolic BP
}

CARDIAC_CODES = [
    'ICD10CM/I21', 'ICD10CM/I22', 'ICD10CM/I24', 'ICD10CM/I20',
    'ICD10CM/I25', 'ICD10CM/I50', 'ICD10CM/I42', 'ICD10CM/I47',
    'ICD9CM/410',  'ICD9CM/411',  'ICD9CM/413',
    'ICD9CM/414',  'ICD9CM/428',  'ICD9CM/402',
]

LOINC_LABELS = {
    'LOINC/2160-0':  'Creatinine',      'LOINC/3094-0':  'BUN',
    'LOINC/2823-3':  'Potassium',       'LOINC/2951-2':  'Sodium',
    'LOINC/1963-8':  'Bicarbonate',     'LOINC/718-7':   'Hemoglobin',
    'LOINC/4544-3':  'Hematocrit',      'LOINC/6690-2':  'WBC',
    'LOINC/777-3':   'Platelets',       'LOINC/6301-6':  'INR',
    'LOINC/5902-2':  'PT',              'LOINC/2345-7':  'Glucose',
    'LOINC/17861-6': 'Calcium',         'LOINC/2777-1':  'Phosphorus',
    'LOINC/1751-7':  'Albumin',         'LOINC/1742-6':  'ALT',
    'LOINC/1920-8':  'AST',             'LOINC/6768-6':  'Alk Phosphatase',
    'LOINC/1975-2':  'Total Bilirubin', 'LOINC/3040-3':  'Lipase',
    'LOINC/1988-5':  'CRP',             'LOINC/75241-0': 'Procalcitonin',
    'LOINC/42637-9': 'BNP',             'LOINC/30934-4': 'BNP',
    'LOINC/33762-6': 'NT-proBNP',       'LOINC/2519-9':  'Lactate',
    'LOINC/32693-4': 'Lactate',         'LOINC/10839-9': 'Troponin I',
    'LOINC/42757-5': 'Troponin I',      'LOINC/49563-0': 'Troponin I',
    'LOINC/6598-7':  'Troponin I',      'LOINC/89579-7': 'Troponin I',
    'LOINC/6597-9':  'Troponin T',      'LOINC/8310-5':  'Temperature',
    'LOINC/8867-4':  'Heart Rate',      'LOINC/9279-1':  'Resp Rate',
    'LOINC/2708-6':  'O2 Sat',          'LOINC/59408-5': 'SpO2',
    'LOINC/8480-6':  'Systolic BP',     'LOINC/8462-4':  'Diastolic BP',
    'LOINC/29463-7': 'Weight',          'LOINC/4548-4':  'HbA1c',
    'LOINC/2532-2':  'LDH',             'LOINC/2157-6':  'CK',
    'LOINC/2154-3':  'CK-MB',           'LOINC/13969-1': 'CK-MB',
    'LOINC/3016-3':  'TSH',             'LOINC/14979-9': 'PTT',
    'LOINC/3255-7':  'Fibrinogen',      'LOINC/48058-2': 'D-Dimer',
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

def visible_trend(trop_series, visible_idx):
    """Direction implied by the last 2 visible troponin readings."""
    if visible_idx < 1:
        return None  # need at least 2 readings for a trend
    v_prev = trop_series[visible_idx - 1][1]
    v_last = trop_series[visible_idx][1]
    return direction(v_prev, v_last)

def is_cardiac(events):
    for e in events:
        if any(e.code.startswith(c) for c in CARDIAC_CODES):
            return True
    return False

def get_trop_series(events):
    series = []
    for e in events:
        if e.code in TROP_CODES and e.numeric_value is not None and e.numeric_value >= 0:
            series.append((e.time, float(e.numeric_value), TROP_CODES[e.code]))
    return sorted(series, key=lambda x: x[0])

def find_dirchange_windows(trop_series):
    """
    Find windows where:
    - visible_idx >= 1 (at least 2 visible troponins → trend can be defined)
    - gap 4-48h
    - visible_trend != actual_direction (the key criterion)
    - actual direction is non-trivial (not stable if trend is also stable)
    """
    candidates = []
    for target_idx in range(2, len(trop_series)):
        for visible_idx in range(1, target_idx):
            t_visible = trop_series[visible_idx][0]
            t_target  = trop_series[target_idx][0]
            gap_h     = hours_between(t_visible, t_target)

            if not (GAP_MIN_HOURS <= gap_h <= GAP_MAX_HOURS):
                continue

            vis_trend  = visible_trend(trop_series, visible_idx)
            v_visible  = trop_series[visible_idx][1]
            v_target   = trop_series[target_idx][1]
            actual_dir = direction(v_visible, v_target)

            # DIRECTION CHANGE: visible trend disagrees with actual direction
            if vis_trend == actual_dir:
                continue
            # Skip stable→stable (no real change on either side)
            if vis_trend == 'stable' and actual_dir == 'stable':
                continue
            # Require the actual change to be meaningful (not just borderline stable)
            actual_delta = abs(v_target - v_visible) / v_visible if v_visible > 0 else 1.0
            if actual_delta < 0.10:  # at least 10% actual change
                continue

            candidates.append((visible_idx, target_idx, gap_h, vis_trend, actual_dir, actual_delta))
    return candidates

def extract_full_ehr(subject, t_target, t_visible, trop_series, visible_idx):
    events = list(subject.events)

    measurements = []
    for e in events:
        if e.table != 'measurement': continue
        if e.time > t_target: continue
        if e.code in TROP_CODES and e.time > t_visible: continue
        if e.numeric_value is None: continue
        label = LOINC_LABELS.get(e.code, e.code.split('/')[-1])
        measurements.append({
            'datetime': fmt_time(e.time),
            'label':    label,
            'value':    round(float(e.numeric_value), 4),
            'unit':     e.unit or '',
        })
    measurements.sort(key=lambda x: x['datetime'])
    if len(measurements) > MAX_LAB_ROWS:
        measurements = measurements[-MAX_LAB_ROWS:]

    def get_table(table_name):
        rows = []
        for e in events:
            if e.table != table_name: continue
            if e.time > t_target: continue
            rows.append(e)
        return sorted(rows, key=lambda e: e.time)

    diagnoses = [{'date': fmt_time(e.time), 'code': e.code, 'description': e.text_value or e.code}
                 for e in get_table('condition')]
    medications = [{'date': fmt_time(e.time), 'name': e.text_value or e.code, 'code': e.code}
                   for e in get_table('drug_exposure')]
    procedures = [{'date': fmt_time(e.time), 'code': e.code, 'description': e.text_value or e.code}
                  for e in get_table('procedure')]
    observations = [{'date': fmt_time(e.time), 'observation': e.text_value or e.code,
                     'value': str(e.numeric_value) if e.numeric_value is not None else None}
                    for e in get_table('observation')]
    visits = [{'date': fmt_time(e.time), 'type': e.text_value or e.code}
              for e in events if e.table in ('visit', 'visit_detail') and e.time <= t_target]
    visits.sort(key=lambda x: x['date'])

    trop_context = [
        {'datetime': fmt_time(t), 'value': round(v, 4), 'label': lbl}
        for t, v, lbl in trop_series[:visible_idx + 1]
    ]

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

def make_question_stem(patient_id, t_visible, t_target, trop_context, vis_trend, gap_h):
    last = trop_context[-1]
    prev = trop_context[-2] if len(trop_context) >= 2 else None
    trend_desc = {
        'rising':  'rising (most recent readings increasing)',
        'falling': 'falling (most recent readings decreasing)',
        'stable':  'stable (most recent readings within ±20%)',
    }.get(vis_trend, vis_trend)
    prev_line = f"Previous Troponin I: {prev['value']} ng/mL at {prev['datetime']}\n" if prev else ''
    return (
        f"Patient EHRSHOT subject_id: {patient_id}\n"
        f"{prev_line}"
        f"Last known Troponin I: {last['value']} ng/mL at {last['datetime']}\n"
        f"Visible troponin trend: {trend_desc}\n"
        f"Troponin measurements are NOT available after {fmt_time(t_visible)}.\n"
        f"All other labs are available up to {fmt_time(t_target)}.\n"
        f"Predict Troponin I at: {fmt_time(t_target)} ({gap_h:.1f}h after last known troponin)"
    )

def main():
    random.seed(RANDOM_SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading EHRSHOT ...")
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))

    # ── Phase 1: Scan for direction-change candidates ─────────────────────────
    print("Scanning for direction-change cases ...")
    candidates = []

    for i, subject_id in enumerate(db):
        if i % 500 == 0:
            print(f"  {i}/6731 scanned, {len(candidates)} direction-change candidates ...")

        subject = db[subject_id]
        events  = list(subject.events)

        if not is_cardiac(events):
            continue

        trop_series = get_trop_series(events)
        if len(trop_series) < 3:
            continue

        windows = find_dirchange_windows(trop_series)
        if not windows:
            continue

        # Score each window — prefer: larger actual change, more gap labs, moderate gap
        best = None
        for vis_idx, tgt_idx, gap_h, vis_trend_dir, actual_dir, actual_delta in windows:
            t_visible = trop_series[vis_idx][0]
            t_target  = trop_series[tgt_idx][0]

            n_gap_labs = sum(
                1 for e in events
                if t_visible < e.time <= t_target and e.code in GAP_SIGNAL_CODES
            )
            score = actual_delta * 3 + n_gap_labs * 0.01 + (1.0 if 6 <= gap_h <= 24 else 0.5)

            if best is None or score > best[0]:
                best = (score, vis_idx, tgt_idx, gap_h, vis_trend_dir, actual_dir, actual_delta, n_gap_labs)

        sc, vis_idx, tgt_idx, gap_h, vis_trend_dir, actual_dir, actual_delta, n_gap_labs = best
        t_visible  = trop_series[vis_idx][0]
        t_target   = trop_series[tgt_idx][0]
        v_visible  = trop_series[vis_idx][1]
        v_target   = trop_series[tgt_idx][1]
        v_prev     = trop_series[vis_idx - 1][1]

        candidates.append({
            'subject_id':    subject_id,
            'visible_idx':   vis_idx,
            'target_idx':    tgt_idx,
            'score':         sc,
            'gap_h':         gap_h,
            'n_gap_labs':    n_gap_labs,
            'vis_trend':     vis_trend_dir,
            'actual_dir':    actual_dir,
            'actual_delta':  actual_delta,
            'actual_value':  v_target,
            'last_visible':  v_visible,
            'prev_visible':  v_prev,
            't_visible':     t_visible,
            't_target':      t_target,
            'trop_series':   trop_series,
        })

    print(f"\nTotal direction-change candidates: {len(candidates)}")
    dc_types = Counter(f"{c['vis_trend']}→{c['actual_dir']}" for c in candidates)
    for k, v in sorted(dc_types.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    # ── Phase 2: Sample balanced across reversal types ────────────────────────
    # Main reversals: falling→rising (reinfarction) and rising→falling
    # Secondary: stable→rising, stable→falling
    reversal_groups = {}
    for c in candidates:
        key = f"{c['vis_trend']}→{c['actual_dir']}"
        reversal_groups.setdefault(key, []).append(c)

    # Sort each group by score descending
    for k in reversal_groups:
        reversal_groups[k].sort(key=lambda x: x['score'], reverse=True)

    # Target distribution — prioritize the most clinically interesting reversals
    target_dist = {
        'falling→rising': 35,   # reinfarction / new injury (hardest to predict)
        'rising→falling': 35,   # faster clearance than expected
        'stable→rising':  15,   # sudden new injury
        'stable→falling': 15,   # sudden clearance
    }

    selected = []
    for key, n_target in target_dist.items():
        pool = reversal_groups.get(key, [])
        take = min(n_target, len(pool))
        selected.extend(pool[:take])
        print(f"  {key}: took {take}/{len(pool)}")

    # If we're short, fill from any remaining candidates
    if len(selected) < TARGET_CASES:
        used_ids = {c['subject_id'] for c in selected}
        extras = [c for c in candidates if c['subject_id'] not in used_ids]
        extras.sort(key=lambda x: x['score'], reverse=True)
        needed = TARGET_CASES - len(selected)
        selected.extend(extras[:needed])
        print(f"  (filled {min(needed, len(extras))} extras to reach target)")

    random.shuffle(selected)
    selected = selected[:TARGET_CASES]

    print(f"\nFinal: {len(selected)} cases")
    final_types = Counter(f"{c['vis_trend']}→{c['actual_dir']}" for c in selected)
    for k, v in sorted(final_types.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    # ── Phase 3: Extract EHR and write case files ─────────────────────────────
    print("\nExtracting full EHR ...")
    manifest_cases = []

    for case_id, cand in enumerate(selected, start=1):
        sid         = cand['subject_id']
        vis_idx     = cand['visible_idx']
        tgt_idx     = cand['target_idx']
        trop_series = cand['trop_series']
        t_visible   = cand['t_visible']
        t_target    = cand['t_target']

        subject = db[sid]
        ehr     = extract_full_ehr(subject, t_target, t_visible, trop_series, vis_idx)

        v_target     = trop_series[tgt_idx][1]
        v_visible    = trop_series[vis_idx][1]
        n_ctx        = vis_idx + 1
        reversal_key = f"{cand['vis_trend']}→{cand['actual_dir']}"

        # Trend-extrapolation heuristic error: predict the trend continues
        # If visible trend is 'falling', heuristic predicts further fall; actual is 'rising' → wrong
        te_dir_correct = False  # trend extrapolation always wrong (by selection criterion)
        # LV heuristic error
        lv_err = abs(v_target - v_visible) / v_target * 100 if v_target > 0 else 100.0

        question_stem = make_question_stem(
            sid, t_visible, t_target, ehr['trop_context'], cand['vis_trend'], cand['gap_h']
        )

        case = {
            'case_id':      case_id,
            'patient_id':   str(sid),
            'reversal_type': reversal_key,
            'vis_trend':    cand['vis_trend'],
            'gap_hours':    round(cand['gap_h'], 1),
            'n_ctx_trops':  n_ctx,
            'n_gap_labs':   cand['n_gap_labs'],
            'lv_err_pct':   round(lv_err, 1),
            'trend_extrapolation_correct': False,
            'question': {
                'stem':            question_stem,
                'target_datetime': fmt_time(t_target),
                'last_trop_time':  fmt_time(t_visible),
                'hours_ahead':     round(cand['gap_h'], 1),
                'visible_trend':   cand['vis_trend'],
            },
            'ground_truth': {
                'value':          round(v_target, 4),
                'direction':      cand['actual_dir'],
                'last_visible':   round(v_visible, 4),
                'visible_trend':  cand['vis_trend'],
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
                'n_lab_rows':     len(ehr['lab_timeline']),
                'n_diagnoses':    len(ehr['diagnoses']),
                'n_medications':  len(ehr['medications']),
                'n_procedures':   len(ehr['procedures']),
                'n_observations': len(ehr['observations']),
                'n_visits':       len(ehr['visit_history']),
                'n_gap_labs':     len(ehr['gap_labs']),
            },
        }

        case_path = OUTPUT_DIR / f"case_{case_id:03d}.json"
        with open(case_path, 'w') as f:
            json.dump(case, f, indent=2)

        manifest_cases.append({
            'case_id':       case_id,
            'patient_id':    str(sid),
            'reversal_type': reversal_key,
            'vis_trend':     cand['vis_trend'],
            'actual_dir':    cand['actual_dir'],
            'gap_hours':     round(cand['gap_h'], 1),
            'n_gap_labs':    cand['n_gap_labs'],
            'lv_err_pct':    round(lv_err, 1),
            'actual_value':  round(v_target, 4),
            'file':          str(case_path),
        })

        if case_id % 10 == 0:
            print(f"  [{case_id:3d}/100] {reversal_key}  gap={cand['gap_h']:.1f}h  "
                  f"gap_labs={cand['n_gap_labs']}  lv_err={lv_err:.0f}%  "
                  f"dx={len(ehr['diagnoses'])} meds={len(ehr['medications'])} labs={len(ehr['lab_timeline'])}")

    # ── Phase 4: Write manifest ────────────────────────────────────────────────
    reversal_dist = dict(Counter(c['reversal_type'] for c in manifest_cases))
    manifest = {
        'name':        'cardiac_dirchange_v1',
        'description': 'Direction-change troponin cases — visible trend reverses at target time',
        'n_cases':     len(manifest_cases),
        'design': {
            'task':      'predict troponin when its visible trend reverses',
            'why_hard':  'both last-value AND trend-extrapolation heuristics fail by construction',
            'gap_hours': f'{GAP_MIN_HOURS}–{GAP_MAX_HOURS}',
            'max_lab_rows': MAX_LAB_ROWS,
        },
        'scoring': {
            'direction_weight': 0.40,
            'within_50pct':     0.35,
            'within_20pct':     0.25,
            'baselines': {
                'last_value_heuristic':       'always wrong on direction (predicts stable)',
                'trend_extrapolation':        'always wrong on direction (by construction)',
                'random_direction':           '~33% direction accuracy expected',
            },
        },
        'reversal_distribution': reversal_dist,
        'cases': manifest_cases,
    }

    with open(MANIFEST, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone!")
    print(f"  Cases:    {OUTPUT_DIR}/case_NNN.json")
    print(f"  Manifest: {MANIFEST}")
    print(f"\nReversal types: {reversal_dist}")
    lv_errs = [c['lv_err_pct'] for c in manifest_cases]
    print(f"LV error — mean={sum(lv_errs)/len(lv_errs):.0f}%  min={min(lv_errs):.0f}%  max={max(lv_errs):.0f}%")

if __name__ == '__main__':
    main()
