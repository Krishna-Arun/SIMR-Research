"""
Benchmark 1: Intervention → Physiological Effect (Forward Causal Prediction)

Given a patient's pre-intervention clinical state, predict what the post-intervention
lab trajectory will look like. Tests whether the model uses interventions as causal
inputs that modify patient-specific trajectories.

Case discovery:
1. Find hadm_ids with both procedures AND serial cardiac labs (pre + post)
2. Pre-intervention window: all labs before first procedure
3. Post-intervention window: all labs after first procedure (up to 7 days)
4. Require ≥3 pre-labs AND ≥2 post-labs with measurable direction change

Output: 100 cases in questions/ folder + manifest in outputs/

No eval-optimizer loop yet — just direct case extraction.
"""

import json
import random
from pathlib import Path
from datetime import timedelta
import pandas as pd
from prep_common import (
    load_labs, load_procedures, load_diagnoses, load_hpi,
    get_cardiac_labs_for_hadm, get_all_labs_for_hadm,
    get_procedures_for_hadm, get_patient_demographics, get_primary_diagnosis,
    format_lab_table, hours_between, direction, flag_lab_value
)

# ─── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
QUESTIONS_DIR = SCRIPT_DIR / "questions"
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Config ───────────────────────────────────────────────────────────────────

TARGET_CASES = 100
MAX_PRE_HOURS = 7 * 24  # 7 days before procedure
MAX_POST_HOURS = 7 * 24  # 7 days after procedure
MIN_PRE_LABS = 3
MIN_POST_LABS = 2
RANDOM_SEED = 42

# ─── Case discovery ──────────────────────────────────────────────────────────

def find_intervention_effect_cases():
    """Find all hadm_ids with procedures and both pre + post cardiac labs."""
    labs = load_labs()
    diags = load_diagnoses()

    candidates = []
    proc_df = load_procedures()

    for hadm_id in diags['hadm_id'].unique()[:5000]:  # scan first 5k admissions
        # Get cardiac labs
        cardiac_labs = get_cardiac_labs_for_hadm(hadm_id)
        if len(cardiac_labs) < MIN_PRE_LABS:
            continue

        # Get procedures
        procs_for_hadm = proc_df[proc_df['hadm_id'] == hadm_id]
        if len(procs_for_hadm) == 0:
            continue

        first_proc_date = procs_for_hadm.iloc[0]['chartdate']
        if pd.isna(first_proc_date):
            continue

        first_proc_date = pd.to_datetime(first_proc_date)

        # Split labs into pre and post
        pre_labs = cardiac_labs[cardiac_labs['charttime'] < first_proc_date]
        post_labs = cardiac_labs[cardiac_labs['charttime'] >= first_proc_date]

        if len(pre_labs) < MIN_PRE_LABS or len(post_labs) < MIN_POST_LABS:
            continue

        # Check for direction change in at least one marker
        pre_troponins = pre_labs[pre_labs['label'] == 'Troponin T']['valuenum'].dropna()
        post_troponins = post_labs[post_labs['label'] == 'Troponin T']['valuenum'].dropna()

        if len(pre_troponins) >= 2 and len(post_troponins) >= 1:
            pre_dir = direction(pre_troponins.iloc[-2], pre_troponins.iloc[-1])
            post_val = post_troponins.iloc[0]
            post_dir = direction(pre_troponins.iloc[-1], post_val)

            candidates.append({
                'hadm_id': hadm_id,
                'first_proc_date': first_proc_date,
                'proc_title': procs_for_hadm.iloc[0]['long_title'],
                'n_pre_labs': len(pre_labs),
                'n_post_labs': len(post_labs),
                'pre_troponin_dir': pre_dir,
                'post_troponin_dir': post_dir,
                'dir_changed': pre_dir != post_dir,
            })

    print(f"Found {len(candidates)} candidate hadm_ids with procedures + labs")
    return candidates

# ─── Build single case ───────────────────────────────────────────────────────

def build_case(hadm_id: int, first_proc_date, proc_title: str, case_id: int):
    """Build one intervention→effect case."""
    hadm_id = int(hadm_id)  # Ensure int, not int64

    cardiac_labs = get_cardiac_labs_for_hadm(hadm_id)
    all_labs = get_all_labs_for_hadm(hadm_id)

    pre_labs_cardiac = cardiac_labs[cardiac_labs['charttime'] < first_proc_date]
    post_labs_cardiac = cardiac_labs[cardiac_labs['charttime'] >= first_proc_date]

    if len(pre_labs_cardiac) < MIN_PRE_LABS or len(post_labs_cardiac) < MIN_POST_LABS:
        return None

    # Limit post-labs to 7 days
    max_post_time = first_proc_date + timedelta(hours=MAX_POST_HOURS)
    post_labs_cardiac = post_labs_cardiac[post_labs_cardiac['charttime'] <= max_post_time]

    # Build question stem (pre-intervention labs only, no ground truth)
    pre_all_labs = all_labs[all_labs['charttime'] < first_proc_date]
    pre_all_labs = pre_all_labs.tail(100)  # cap at 100 rows

    lab_table = format_lab_table(pre_all_labs, markdown=True)

    demographics = get_patient_demographics(hadm_id)
    primary_dx = get_primary_diagnosis(hadm_id)

    question_stem = f"""Patient hadm_id: {hadm_id}

Demographics: {demographics.get('age', '?')}-year-old {demographics.get('gender', '?')}
Primary Diagnosis: {primary_dx}

Pre-Procedure Lab Timeline (all available labs before {first_proc_date.strftime('%Y-%m-%d %H:%M')}):

{lab_table}

Procedure Performed: {proc_title} on {first_proc_date.strftime('%Y-%m-%d %H:%M')}

Analyze the pre-intervention lab trajectory and clinical context. Given the patient's state and the intervention performed, describe what physiological changes you would expect to see in the post-intervention period. Specifically discuss expected direction and magnitude of change for key cardiac biomarkers (Troponin, CK, CK-MB)."""

    # Ground truth (post-intervention labs)
    post_lab_table = format_lab_table(post_labs_cardiac, markdown=True)

    # Compute expected changes in troponin
    pre_trop = pre_labs_cardiac[pre_labs_cardiac['label'] == 'Troponin T']['valuenum'].dropna()
    post_trop = post_labs_cardiac[post_labs_cardiac['label'] == 'Troponin T']['valuenum'].dropna()

    expected_troponin_dir = None
    expected_troponin_magnitude = None
    if len(pre_trop) > 0 and len(post_trop) > 0:
        expected_troponin_dir = direction(pre_trop.iloc[-1], post_trop.iloc[0])
        pct_change = ((post_trop.iloc[0] - pre_trop.iloc[-1]) / pre_trop.iloc[-1] * 100) if pre_trop.iloc[-1] > 0 else 0
        expected_troponin_magnitude = pct_change

    case = {
        'case_id': f'a_{case_id:03d}',
        'benchmark': 'intervention_physiological_effect',
        'hadm_id': int(hadm_id),
        'procedure': {
            'title': proc_title,
            'date': first_proc_date.strftime('%Y-%m-%d %H:%M'),
        },
        'question': {
            'stem': question_stem,
            'type': 'intervention_forward_prediction',
        },
        'visible_context': {
            'pre_intervention_labs': len(pre_all_labs),
            'demographics': demographics,
            'primary_diagnosis': primary_dx,
        },
        'ground_truth': {
            'post_intervention_labs': post_lab_table,
            'n_post_labs': len(post_labs_cardiac),
            'expected_troponin_direction': expected_troponin_dir,
            'expected_troponin_magnitude_pct': expected_troponin_magnitude,
        },
    }

    return case

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    random.seed(RANDOM_SEED)

    print("Discovering intervention → effect cases...")
    candidates = find_intervention_effect_cases()

    # Shuffle and select top TARGET_CASES
    random.shuffle(candidates)
    selected = candidates[:TARGET_CASES]

    print(f"Building {len(selected)} cases...")
    cases = []

    for idx, cand in enumerate(selected, start=1):
        case = build_case(
            cand['hadm_id'],
            cand['first_proc_date'],
            cand['proc_title'],
            idx
        )
        if case:
            cases.append(case)

            # Write individual case file
            case_file = QUESTIONS_DIR / f"{case['case_id']}.json"
            with open(case_file, 'w') as f:
                json.dump(case, f, indent=2)

            if idx % 10 == 0:
                print(f"  Built {idx}/{len(selected)} cases")

    print(f"\nTotal cases built: {len(cases)}")

    # Write manifest
    manifest = {
        'name': 'intervention_physiological_effect_benchmark_v1',
        'description': 'Forward causal prediction: given pre-intervention state and procedure, predict post-intervention lab trajectory',
        'task': 'intervention_physiological_effect',
        'n_cases': len(cases),
        'cases': [
            {
                'case_id': c['case_id'],
                'hadm_id': c['hadm_id'],
                'procedure': c['procedure'],
                'file': str(QUESTIONS_DIR / f"{c['case_id']}.json"),
            }
            for c in cases
        ],
    }

    manifest_file = OUTPUTS_DIR / 'intervention_physiological_effect_manifest_v1.json'
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote manifest to {manifest_file}")
    print(f"Wrote {len(cases)} case files to {QUESTIONS_DIR}")

if __name__ == '__main__':
    main()
