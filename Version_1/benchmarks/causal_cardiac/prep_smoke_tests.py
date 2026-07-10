#!/usr/bin/env python3
"""
Smoke test case generator: Creates only 5 cases for Benchmark A for quick testing.
Filters the existing case discovery logic to select first 5 candidates.
"""

import json
import pandas as pd
from pathlib import Path
from prep_common import (
    load_labs, load_procedures, load_diagnoses, load_hpi,
    get_cardiac_labs_for_hadm, get_patient_demographics, format_lab_table
)

SCRIPT_DIR = Path(__file__).parent
QUESTIONS_DIR = SCRIPT_DIR / 'questions'
OUTPUTS_DIR = SCRIPT_DIR / 'outputs'

QUESTIONS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

def generate_smoke_test_a(n_cases=5):
    """Generate 5 Benchmark A smoke test cases (Intervention → Effect)."""
    print(f"Generating Benchmark A smoke test ({n_cases} cases)...")

    labs = load_labs()
    procedures = load_procedures()
    diagnoses = load_diagnoses()
    hpi = load_hpi()

    # Find candidate hadm_ids with procedures + serial cardiac labs
    hadm_ids_with_proc = procedures['hadm_id'].unique()
    labs_hadm = labs['hadm_id'].unique()
    candidates = [h for h in hadm_ids_with_proc if h in labs_hadm][:n_cases]

    cases = []
    for i, hadm_id in enumerate(candidates, 1):
        try:
            hadm_labs = get_cardiac_labs_for_hadm(hadm_id)
            if len(hadm_labs) < 5:
                continue

            # Get procedure info
            hadm_procedures = procedures[procedures['hadm_id'] == hadm_id].sort_values('procedure_date')
            if len(hadm_procedures) == 0:
                continue

            first_proc = hadm_procedures.iloc[0]
            proc_date = pd.Timestamp(first_proc['procedure_date'])

            # Split labs: pre vs post
            pre_labs = hadm_labs[hadm_labs['charttime'] < proc_date]
            post_labs = hadm_labs[hadm_labs['charttime'] >= proc_date]

            if len(pre_labs) < 3 or len(post_labs) < 2:
                continue

            # Build case
            visible_labs = pre_labs.sort_values('charttime')[['charttime', 'itemid', 'value_numeric', 'valueuom', 'label']].to_dict('records')
            ground_truth_labs = post_labs.sort_values('charttime')[['charttime', 'itemid', 'value_numeric', 'valueuom', 'label']].to_dict('records')

            case = {
                'benchmark': 'intervention_physiological_effect',
                'case_id': f'a_{str(i).zfill(3)}',
                'hadm_id': int(hadm_id),
                'procedure': {
                    'name': first_proc['procedure_name'],
                    'date': proc_date.isoformat(),
                },
                'question': {
                    'stem': f"Patient {hadm_id} underwent {first_proc['procedure_name']} on {proc_date.strftime('%Y-%m-%d')}. All pre-procedure cardiac labs are shown. Given this intervention, predict the expected post-procedure lab changes.",
                    'visible_labs': visible_labs,
                },
                'ground_truth': {
                    'post_intervention_labs': ground_truth_labs,
                },
            }

            # Save case
            case_file = QUESTIONS_DIR / f"a_{str(i).zfill(3)}.json"
            with open(case_file, 'w') as f:
                json.dump(case, f, indent=2)

            cases.append(case)
            print(f"  Case a_{str(i).zfill(3)}: {first_proc['procedure_name']}")

        except Exception as e:
            print(f"  Error processing hadm {hadm_id}: {e}")
            continue

    return cases


if __name__ == '__main__':
    print("\n=== Causal Cardiac Benchmark: Smoke Test Generation ===\n")

    cases_a = generate_smoke_test_a(5)

    print(f"\n✓ Generated {len(cases_a)} Benchmark A cases")
    print(f"✓ Total: {len(cases_a)} smoke test cases in {QUESTIONS_DIR}\n")
