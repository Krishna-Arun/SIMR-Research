"""
Prepare patient args bundles for the evaluator-optimizer workflow.
Writes one JSON file per patient to benchmark/patient_data/.
"""
import gzip, csv, json, os
from collections import defaultdict

BASE = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/mimic-iv-clinical-database-demo-2.2'
OUT  = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/patient_data'
os.makedirs(OUT, exist_ok=True)

# ── load lookups ──────────────────────────────────────────────────────────────
diag_lookup, proc_lookup, lab_item_lookup = {}, {}, {}
with gzip.open(f'{BASE}/hosp/d_icd_diagnoses.csv.gz', 'rt') as f:
    for r in csv.DictReader(f): diag_lookup[(r['icd_code'], r['icd_version'])] = r['long_title']
with gzip.open(f'{BASE}/hosp/d_icd_procedures.csv.gz', 'rt') as f:
    for r in csv.DictReader(f): proc_lookup[(r['icd_code'], r['icd_version'])] = r['long_title']
with gzip.open(f'{BASE}/hosp/d_labitems.csv.gz', 'rt') as f:
    for r in csv.DictReader(f): lab_item_lookup[r['itemid']] = r['label']

patients = {}
with gzip.open(f'{BASE}/hosp/patients.csv.gz', 'rt') as f:
    for r in csv.DictReader(f): patients[r['subject_id']] = r

admissions = defaultdict(list)
with gzip.open(f'{BASE}/hosp/admissions.csv.gz', 'rt') as f:
    for r in csv.DictReader(f): admissions[r['subject_id']].append(r)

diags = defaultdict(list)
with gzip.open(f'{BASE}/hosp/diagnoses_icd.csv.gz', 'rt') as f:
    for r in csv.DictReader(f):
        title = diag_lookup.get((r['icd_code'], r['icd_version']), r['icd_code'])
        diags[r['subject_id']].append({'hadm_id': r['hadm_id'], 'seq_num': int(r['seq_num']), 'diagnosis': title})

procs = defaultdict(list)
with gzip.open(f'{BASE}/hosp/procedures_icd.csv.gz', 'rt') as f:
    for r in csv.DictReader(f):
        title = proc_lookup.get((r['icd_code'], r['icd_version']), r['icd_code'])
        procs[r['subject_id']].append({'hadm_id': r['hadm_id'], 'date': r['chartdate'], 'procedure': title})

meds = defaultdict(list)
with gzip.open(f'{BASE}/hosp/prescriptions.csv.gz', 'rt') as f:
    for r in csv.DictReader(f):
        if r['drug']:
            meds[r['subject_id']].append({
                'hadm_id': r['hadm_id'], 'start': r['starttime'][:10],
                'drug': r['drug'], 'dose': r['dose_val_rx'],
                'unit': r['dose_unit_rx'], 'route': r['route']
            })

KEY_LABS = {
    '51003':'Troponin T','51002':'Troponin I','50963':'NTproBNP',
    '50911':'CK-MB','50910':'CK','50912':'Creatinine',
    '51006':'BUN','50971':'Potassium','50983':'Sodium',
    '51222':'Hemoglobin','51265':'Platelet Count','51301':'WBC',
    '50882':'Bicarbonate','51237':'INR','51274':'Prothrombin Time',
    '50902':'Chloride','50931':'Glucose','50960':'Magnesium',
    '50893':'Calcium, Total','50970':'Phosphate','50813':'Lactate',
    '51221':'Hematocrit','50861':'ALT','50878':'AST',
    '50889':'C-Reactive Protein','50804':'BNP','50868':'Anion Gap',
    '50862':'Albumin','50867':'Amylase','50956':'Lipase',
    '51144':'Bands','51275':'PT','51491':'Urine Casts',
    '51094':'Urine Protein','51082':'Uric Acid','51254':'Lymphocytes',
    '51244':'Neutrophils','51200':'Eosinophils'
}
labs_raw = defaultdict(list)
with gzip.open(f'{BASE}/hosp/labevents.csv.gz', 'rt') as f:
    for r in csv.DictReader(f):
        if r['itemid'] in KEY_LABS and r['value']:
            labs_raw[r['subject_id']].append({
                'hadm_id': r['hadm_id'],
                'date': r['charttime'][:10],
                'label': KEY_LABS[r['itemid']],
                'value': r['value'],
                'flag': r['flag'] or None,
                'ref_lower': r['ref_range_lower'] or None,
                'ref_upper': r['ref_range_upper'] or None
            })

# ── builder ───────────────────────────────────────────────────────────────────
def build(sid, cut_hadm_id, ground_truth_procedure):
    p = patients[sid]
    sorted_adms = sorted(admissions[sid], key=lambda x: x['admittime'])
    cut_idx = next(i for i, a in enumerate(sorted_adms) if a['hadm_id'] == cut_hadm_id)
    prior_adms = sorted_adms[:cut_idx]
    cut_adm    = sorted_adms[cut_idx]

    history = []
    for adm in prior_adms:
        hid = adm['hadm_id']
        adm_diags  = sorted([d for d in diags[sid] if d['hadm_id']==hid], key=lambda x: x['seq_num'])
        adm_procs  = sorted([p2 for p2 in procs[sid] if p2['hadm_id']==hid], key=lambda x: x['date'])
        adm_meds   = sorted(set(m['drug'] for m in meds[sid] if m['hadm_id']==hid))
        history.append({
            'admit_date':        adm['admittime'][:10],
            'discharge_date':    adm['dischtime'][:10],
            'admission_type':    adm['admission_type'],
            'discharge_location':adm['discharge_location'],
            'diagnoses':         [d['diagnosis'] for d in adm_diags[:8]],
            'procedures_performed': [p2['procedure'] for p2 in adm_procs],
            'medications':       adm_meds[:12]
        })

    cut_diags = sorted([d for d in diags[sid] if d['hadm_id']==cut_hadm_id], key=lambda x: x['seq_num'])
    cut_meds  = sorted(set(m['drug'] for m in meds[sid] if m['hadm_id']==cut_hadm_id))

    current = {
        'admit_date':       cut_adm['admittime'][:10],
        'admission_type':   cut_adm['admission_type'],
        'admission_location':cut_adm['admission_location'],
        'diagnoses':        [d['diagnosis'] for d in cut_diags[:8]],
        'medications':      cut_meds[:15]
    }

    # Deduplicated labs for this admission
    cut_labs_raw = [l for l in labs_raw[sid] if l['hadm_id'] == cut_hadm_id]
    seen, cut_labs = set(), []
    for l in sorted(cut_labs_raw, key=lambda x: x['date']):
        key = (l['date'], l['label'])
        if key not in seen:
            seen.add(key)
            cut_labs.append(l)

    return {
        'patient_id': sid,
        'patient_context': {
            'demographics': {
                'age': int(p['anchor_age']),
                'gender': 'Male' if p['gender']=='M' else 'Female'
            },
            'admission_history': history,
            'current_admission': current
        },
        'lab_data': cut_labs,
        'ground_truth_procedure': ground_truth_procedure
    }

# ── target patients ───────────────────────────────────────────────────────────
# (subject_id, cut_hadm_id, ground_truth_procedure)
TARGETS = [
    # 46F: AKI → RRT/continuous dialysis (renal replacement therapy)
    ('10039708', '28258130', 'Performance of Urinary Filtration, Multiple (Continuous Renal Replacement Therapy)'),
    # 63M: long hematologic disease history → AKI → single urinary filtration (dialysis)
    ('10035631', '29276678', 'Performance of Urinary Filtration, Single'),
    # 53M: AKI unspecified → urinary filtration (dialysis) — hadm 24698912
    ('10015860', '24698912', 'Performance of Urinary Filtration, Intermittent, Less than 6 Hours Per Day'),
    # 72F: AKI with tubular necrosis → mechanical ventilation — hadm 23559586
    ('10003400', '23559586', 'Respiratory Ventilation, 24-96 Consecutive Hours'),
]

# Verify hadm_ids exist; skip those that don't
valid = []
for sid, hadm_id, gt in TARGETS:
    if any(a['hadm_id']==hadm_id for a in admissions[sid]):
        valid.append((sid, hadm_id, gt))
    else:
        print(f'WARNING: hadm_id {hadm_id} not found for patient {sid} — checking alternatives')
        for adm in sorted(admissions[sid], key=lambda x: x['admittime']):
            ap = [p2['procedure'] for p2 in procs[sid] if p2['hadm_id']==adm['hadm_id']]
            print(f'  hadm={adm["hadm_id"]} {adm["admittime"][:10]}: {ap[:3]}')

for sid, hadm_id, gt in valid:
    data = build(sid, hadm_id, gt)
    outpath = f'{OUT}/patient_{sid}.json'
    with open(outpath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'Wrote {outpath} ({len(data["lab_data"])} labs, {len(data["patient_context"]["admission_history"])} prior admissions)')
