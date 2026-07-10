#!/usr/bin/env python3
"""
prep_cardiac_dirchange_v2.py

Builds a direction-change benchmark in nextlab format.

Design:
  - Scans EHRSHOT cardiac patients for troponin direction-change windows:
      visible trend (last 2 troponins) disagrees with actual next direction
  - Builds cases in the same JSON schema as cardiac_nextlab_benchmark_v1.json
      so nextlab_answer_agent.js works without modification
  - lab_timeline includes all labs up to t_target EXCEPT troponin after t_visible,
      giving the agent gap-window cross-lab signals (BNP, creatinine, etc.)
  - Adds reversal_type and visible_trend metadata fields

Reversal types (4):
  rising→falling   — acute clearance faster than expected
  falling→rising   — reinfarction / new injury
  stable→rising    — sudden new troponin elevation
  stable→falling   — sudden clearance from plateau

Output:
  benchmarks/cardiac-dirchange-v2/output/cardiac_dirchange_v2_benchmark_v1.json
"""

import json
import random
from pathlib import Path
from collections import Counter, defaultdict
from datetime import timedelta

import meds_reader
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent.parent
EHRSHOT_PATH = REPO_ROOT / "EHRSHOT Hackathon Project" / "meds_reader_omop_ehrshot"
CODES_META   = EHRSHOT_PATH / "metadata" / "codes.parquet"
OUT_DIR      = Path(__file__).parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE     = OUT_DIR / "cardiac_dirchange_v2_benchmark_v1.json"

# ── Constants ──────────────────────────────────────────────────────────────────
GAP_MIN_HOURS = 4
GAP_MAX_HOURS = 48
MAX_LAB_ROWS  = 120
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
    'LOINC/2601-3':  'Magnesium',       'LOINC/20570-8': 'Hematocrit',
    'LOINC/2075-0':  'Chloride',        'LOINC/33037-3': 'Anion Gap',
    'LOINC/62238-1': 'eGFR',
}

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


def fmt_time(t):
    return t.strftime('%Y-%m-%dT%H:%M')


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
    series = []
    for e in events:
        if e.code in TROP_CODES and e.numeric_value is not None and e.numeric_value >= 0:
            series.append((e.time, float(e.numeric_value), TROP_CODES[e.code]))
    return sorted(series, key=lambda x: x[0])


def find_dirchange_windows(trop_series):
    """
    Find (visible_idx, target_idx) pairs where:
      - visible_idx >= 1  →  at least 2 visible troponins (trend can be inferred)
      - gap 4-48h between visible and target
      - visible trend (prev→visible) disagrees with actual direction (visible→target)
      - actual delta ≥ 10%
    """
    candidates = []
    for target_idx in range(2, len(trop_series)):
        for visible_idx in range(1, target_idx):
            t_visible = trop_series[visible_idx][0]
            t_target  = trop_series[target_idx][0]
            gap_h     = hours_between(t_visible, t_target)

            if not (GAP_MIN_HOURS <= gap_h <= GAP_MAX_HOURS):
                continue

            v_prev    = trop_series[visible_idx - 1][1]
            v_visible = trop_series[visible_idx][1]
            v_target  = trop_series[target_idx][1]

            vis_trend  = direction(v_prev, v_visible)
            actual_dir = direction(v_visible, v_target)

            if vis_trend == actual_dir:
                continue
            if vis_trend == 'stable' and actual_dir == 'stable':
                continue

            actual_delta = abs(v_target - v_visible) / v_visible if v_visible > 0 else 1.0
            if actual_delta < 0.10:
                continue

            candidates.append((visible_idx, target_idx, gap_h, vis_trend, actual_dir, actual_delta))
    return candidates


def _flag(label, value):
    ref = HUMAN_REF.get(label)
    if ref is None or value is None:
        return None
    lo, hi, _ = ref
    if value < lo:   return 'low'
    if value > hi:   return 'abnormal'
    return None


def _drug_name(code, code_to_desc):
    desc = code_to_desc.get(code)
    if desc:
        return desc.strip()
    if code.startswith('STANFORD_SHC_DRUG/'):
        return code.split('/')[-1]
    return None


def build_case(subject_id, events, trop_series, visible_idx, target_idx,
               vis_trend, actual_dir, gap_h, case_id, code_to_desc):
    t_visible = trop_series[visible_idx][0]
    t_target  = trop_series[target_idx][0]
    v_visible = trop_series[visible_idx][1]
    v_target  = trop_series[target_idx][1]
    v_prev    = trop_series[visible_idx - 1][1]

    events_sorted = sorted(events, key=lambda e: e.time)

    # ── Demographics ──────────────────────────────────────────────────────────
    birth_year, gender = None, 'Unknown'
    for e in events_sorted:
        if e.table == 'person':
            if 'MEDS_BIRTH' in e.code:
                birth_year = e.time.year
            if e.code.startswith('Gender/'):
                raw = e.code.split('/')[-1]
                gender = 'Female' if raw.upper() in ('F', 'FEMALE') else 'Male'
    age = (t_visible.year - birth_year) if birth_year else 50

    # ── Lab timeline ──────────────────────────────────────────────────────────
    # Include:
    #   - All troponin readings up to t_visible (the last known troponin)
    #   - All other labs up to t_target (gap-window cross-lab signals for reversal detection)
    # Exclude:
    #   - Troponin readings after t_visible (these are hidden — the prediction target)
    seen_labs = set()
    lab_timeline = []
    for e in events_sorted:
        if e.table != 'measurement':
            continue
        if e.code not in LOINC_LABELS:
            continue
        if e.numeric_value is None:
            continue

        label   = LOINC_LABELS[e.code]
        is_trop = e.code in TROP_CODES

        if is_trop:
            if e.time > t_visible:
                continue     # troponin after cutoff is hidden
        else:
            if e.time > t_target:
                continue     # other labs shown up to prediction time

        key = (label, fmt_time(e.time))
        if key in seen_labs:
            continue
        seen_labs.add(key)

        ref = HUMAN_REF.get(label, (None, None, ''))
        lab_timeline.append({
            'datetime':  fmt_time(e.time),
            'label':     label,
            'value':     round(float(e.numeric_value), 4),
            'unit':      e.unit or ref[2] or '',
            'flag':      _flag(label, e.numeric_value),
            'ref_lower': str(ref[0]) if ref[0] is not None else '',
            'ref_upper': str(ref[1]) if ref[1] is not None else '',
            'in_gap':    (not is_trop and e.time > t_visible),  # flag for gap-window labs
        })

    lab_timeline.sort(key=lambda x: (x['datetime'], x['label']))

    # Cap rows: always keep all troponins, trim oldest non-trop rows
    if len(lab_timeline) > MAX_LAB_ROWS:
        trops  = [x for x in lab_timeline if x['label'] == 'Troponin I']
        others = [x for x in lab_timeline if x['label'] != 'Troponin I']
        others = others[-(MAX_LAB_ROWS - len(trops)):]
        lab_timeline = sorted(trops + others, key=lambda x: (x['datetime'], x['label']))

    # ── Clinical context (diagnoses, meds from visit containing t_visible) ────
    visit_events = defaultdict(list)
    for e in events_sorted:
        if e.visit_id and e.time <= t_visible:
            visit_events[e.visit_id].append(e)

    current_visit_id = None
    min_delta_sec = float('inf')
    for e in events_sorted:
        if e.table == 'measurement' and e.code in TROP_CODES:
            if e.numeric_value is not None:
                delta = abs((e.time - t_visible).total_seconds())
                if delta < min_delta_sec:
                    min_delta_sec = delta
                    current_visit_id = e.visit_id

    def _diagnoses(vid):
        if not vid:
            return []
        codes = [e.code for e in visit_events.get(vid, []) if e.table == 'condition']
        names = []
        for c in codes:
            desc = code_to_desc.get(c)
            names.append(desc.strip() if desc else c.split('/')[-1])
        return list(dict.fromkeys(names))[:8]

    def _meds(vid):
        if not vid:
            return []
        names = []
        for e in visit_events.get(vid, []):
            if e.table != 'drug_exposure':
                continue
            n = _drug_name(e.code, code_to_desc)
            if n and not n.startswith('Medication ('):
                names.append(n)
        return list(dict.fromkeys(names))[:12]

    diagnoses   = _diagnoses(current_visit_id)
    medications = _meds(current_visit_id)

    # ── Visible troponin series ───────────────────────────────────────────────
    prior_troponins = [
        {'datetime': x['datetime'], 'value': x['value'], 'unit': x['unit'], 'flag': x['flag']}
        for x in lab_timeline if x['label'] == 'Troponin I'
    ]
    n_ctx_trops = visible_idx + 1  # number of troponins visible in context

    # ── Difficulty ────────────────────────────────────────────────────────────
    if n_ctx_trops == 1:
        difficulty = 'hard'
    elif n_ctx_trops == 2:
        difficulty = 'medium'
    else:
        difficulty = 'easy'

    # ── Reversal metadata ─────────────────────────────────────────────────────
    reversal_type = f'{vis_trend}→{actual_dir}'
    pct_change = ((v_target - v_visible) / v_visible * 100) if v_visible > 0 else 0

    trend_desc = {
        'rising':  'rising (most recent readings increasing >20%)',
        'falling': 'falling (most recent readings decreasing >20%)',
        'stable':  'stable (most recent readings within ±20%)',
    }.get(vis_trend, vis_trend)

    n_gap_labs = sum(1 for x in lab_timeline if x.get('in_gap'))

    # ── Question stem ─────────────────────────────────────────────────────────
    question_stem = (
        f"Patient subject_id: {subject_id}\n\n"
        f"A {age}-year-old {gender} presents with chest symptoms. "
        f"Current diagnoses: {'; '.join(diagnoses) if diagnoses else 'not recorded'}. "
        f"Current medications: {', '.join(medications[:6]) if medications else 'not recorded'}.\n\n"
        f"Troponin I measurements are available up to {fmt_time(t_visible)} "
        f"({n_ctx_trops} troponin reading{'s' if n_ctx_trops > 1 else ''} visible). "
        f"Additional labs are available up to {fmt_time(t_target)}.\n\n"
        f"The next Troponin I measurement is scheduled for {fmt_time(t_target)} "
        f"({gap_h:.1f} hours after the last known troponin reading).\n\n"
        f"Based on this patient's full lab history, "
        f"predict the Troponin I value at {fmt_time(t_target)}."
    )

    return {
        'case_id':    case_id,
        'patient_id': str(subject_id),
        'difficulty': difficulty,
        'n_context_troponins': n_ctx_trops,
        'reversal_type': reversal_type,
        'visible_trend': vis_trend,
        'actual_dir':    actual_dir,
        'gap_hours':     round(gap_h, 1),
        'n_gap_labs':    n_gap_labs,
        'demographics': {'age': age, 'gender': gender},
        'clinical_context': {
            'diagnoses':   diagnoses,
            'medications': medications,
        },
        'lab_timeline':    lab_timeline,
        'context_cutoff':  fmt_time(t_visible),
        'troponin_series': prior_troponins,
        'question': {
            'stem':            question_stem,
            'target_lab':      'Troponin I',
            'target_datetime': fmt_time(t_target),
            'hours_ahead':     round(gap_h, 1),
            'visible_trend':   vis_trend,
        },
        'ground_truth': {
            'lab_name':    'Troponin I',
            'datetime':    fmt_time(t_target),
            'value':       round(v_target, 4),
            'unit':        'ng/mL',
            'flag':        _flag('Troponin I', v_target),
            'direction':   actual_dir,
            'pct_change':  round(pct_change, 1),
            'last_visible': round(v_visible, 4),
            'visible_trend': vis_trend,
            'reversal_type': reversal_type,
        },
        'scoring_guide': {
            'direction_correct':  0.40,
            'within_50pct_error': 0.35,
            'within_20pct_error': 0.25,
            'max_score':          1.00,
            'note': (
                'Score = direction_correct (0.4 if direction matches, else 0) + '
                'within_50pct (0.35 if |error| <= 50%, else 0) + '
                'within_20pct (0.25 if |error| <= 20%, else 0). Max = 1.0. '
                'Note: direction_correct uses the reversed direction (the actual direction at target), '
                'NOT the visible trend — both last-value and trend-extrapolation heuristics fail by design.'
            ),
        },
    }


def main():
    random.seed(RANDOM_SEED)

    print('Loading code metadata ...')
    codes_df = pd.read_parquet(CODES_META)
    code_to_desc = dict(zip(codes_df['code'], codes_df['description']))

    print(f'Loading EHRSHOT from {EHRSHOT_PATH} ...')
    db = meds_reader.SubjectDatabase(str(EHRSHOT_PATH))
    print(f'Total subjects: {len(db)}')

    # ── Phase 1: Scan for direction-change candidates ─────────────────────────
    print('Scanning for direction-change candidates ...')
    candidates = []

    for i, subject_id in enumerate(db):
        if i % 500 == 0:
            print(f'  {i}/{len(db)} scanned, {len(candidates)} candidates ...')

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

        # Score each window; prefer larger actual change, more gap labs, moderate gap
        best = None
        for vis_idx, tgt_idx, gap_h, vis_trend, actual_dir, actual_delta in windows:
            t_visible = trop_series[vis_idx][0]
            t_target  = trop_series[tgt_idx][0]
            n_gap = sum(
                1 for e in events
                if e.code in LOINC_LABELS and e.code not in TROP_CODES
                and t_visible < e.time <= t_target
                and e.numeric_value is not None
            )
            score = actual_delta * 3 + n_gap * 0.01 + (1.0 if 6 <= gap_h <= 24 else 0.5)
            if best is None or score > best[0]:
                best = (score, vis_idx, tgt_idx, gap_h, vis_trend, actual_dir, actual_delta, n_gap)

        sc, vis_idx, tgt_idx, gap_h, vis_trend, actual_dir, actual_delta, n_gap = best
        candidates.append({
            'subject_id':  subject_id,
            'events':      events,
            'trop_series': trop_series,
            'visible_idx': vis_idx,
            'target_idx':  tgt_idx,
            'score':       sc,
            'gap_h':       gap_h,
            'vis_trend':   vis_trend,
            'actual_dir':  actual_dir,
            'actual_delta': actual_delta,
            'n_gap_labs':  n_gap,
        })

    print(f'\nTotal direction-change candidates: {len(candidates)}')
    dc_types = Counter(f"{c['vis_trend']}→{c['actual_dir']}" for c in candidates)
    for k, v in sorted(dc_types.items(), key=lambda x: -x[1]):
        print(f'  {k}: {v}')

    # ── Phase 2: Balanced sampling across 4 reversal types ───────────────────
    reversal_groups = {}
    for c in candidates:
        key = f"{c['vis_trend']}→{c['actual_dir']}"
        reversal_groups.setdefault(key, []).append(c)

    for k in reversal_groups:
        reversal_groups[k].sort(key=lambda x: x['score'], reverse=True)

    target_dist = {
        'falling→rising': 35,
        'rising→falling': 35,
        'stable→rising':  15,
        'stable→falling': 15,
    }

    selected = []
    for key, n_target in target_dist.items():
        pool = reversal_groups.get(key, [])
        take = min(n_target, len(pool))
        selected.extend(pool[:take])
        print(f'  {key}: took {take}/{len(pool)}')

    if len(selected) < TARGET_CASES:
        used_ids = {c['subject_id'] for c in selected}
        extras = [c for c in candidates if c['subject_id'] not in used_ids]
        extras.sort(key=lambda x: x['score'], reverse=True)
        needed = TARGET_CASES - len(selected)
        selected.extend(extras[:needed])
        print(f'  (filled {min(needed, len(extras))} extras)')

    random.shuffle(selected)
    selected = selected[:TARGET_CASES]

    print(f'\nFinal: {len(selected)} cases')
    final_types = Counter(f"{c['vis_trend']}→{c['actual_dir']}" for c in selected)
    for k, v in sorted(final_types.items(), key=lambda x: -x[1]):
        print(f'  {k}: {v}')

    # ── Phase 3: Build case objects ───────────────────────────────────────────
    print('\nBuilding case objects ...')
    cases = []

    for case_id, cand in enumerate(selected, start=1):
        case = build_case(
            subject_id  = cand['subject_id'],
            events      = cand['events'],
            trop_series = cand['trop_series'],
            visible_idx = cand['visible_idx'],
            target_idx  = cand['target_idx'],
            vis_trend   = cand['vis_trend'],
            actual_dir  = cand['actual_dir'],
            gap_h       = cand['gap_h'],
            case_id     = case_id,
            code_to_desc = code_to_desc,
        )
        cases.append(case)

        if case_id % 10 == 0 or case_id <= 5:
            print(f'  [{case_id:3d}] {case["reversal_type"]:20s}  '
                  f'gap={case["gap_hours"]:.1f}h  gap_labs={case["n_gap_labs"]}  '
                  f'labs={len(case["lab_timeline"])}')

    # ── Phase 4: Write manifest ───────────────────────────────────────────────
    reversal_dist = dict(Counter(c['reversal_type'] for c in cases))

    benchmark = {
        'name':        'cardiac_dirchange_v2_benchmark_v1',
        'description': (
            'Direction-change troponin benchmark (v2) — nextlab format. '
            'Visible troponin trend reverses at target time; agent must use '
            'cross-lab gap signals to detect the reversal. '
            'Compatible with nextlab_answer_agent.js.'
        ),
        'task':       'next_lab_value_prediction',
        'target_lab': 'Troponin I',
        'design': {
            'why_hard': (
                'Both last-value and trend-extrapolation heuristics fail by construction. '
                'Non-troponin labs (BNP, creatinine, etc.) during the gap window '
                'provide the signal needed to detect the reversal.'
            ),
            'gap_hours': f'{GAP_MIN_HOURS}–{GAP_MAX_HOURS}',
            'lab_timeline_note': (
                'lab_timeline includes all labs up to t_target EXCEPT troponin after t_visible. '
                'Rows with in_gap=True are from the gap window (t_visible < t <= t_target).'
            ),
        },
        'scoring': {
            'direction_correct':  0.40,
            'within_50pct_error': 0.35,
            'within_20pct_error': 0.25,
            'max_score':          1.00,
        },
        'reversal_distribution': reversal_dist,
        'n_cases': len(cases),
        'cases':   cases,
    }

    with open(OUT_FILE, 'w') as f:
        json.dump(benchmark, f, indent=2)

    print(f'\nWrote {OUT_FILE}  ({len(cases)} cases)')
    print(f'Reversal types: {reversal_dist}')


if __name__ == '__main__':
    main()
