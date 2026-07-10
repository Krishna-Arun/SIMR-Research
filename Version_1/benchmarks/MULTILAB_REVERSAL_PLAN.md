# Multi-Lab Post-Intervention Reversal Benchmark (MIMIC-IV) — Refined Plan

## Overview

Adapt cardiac-dirchange-v2 logic for MIMIC-IV with:
- **Multi-lab tracking** (Troponin, CK, Creatinine, BNP)
- **Flexible reversal timing** (immediate post-intervention AND arbitrary gaps)
- **All available labs** up to prediction point (not just pre-procedure)
- **Patient-specific causal justification** (not generic)

---

## Phase 1: Core Design

### Task Definition

**Given:**
- Complete lab timeline: all labs from admission up to `t_visible` (last observed value)
- Procedure performed and timing
- Patient demographics, comorbidities, baseline kidney function

**Visible state at `t_visible`:**
- Last value for each lab
- Trend from previous values (rising/falling/stable)

**Prediction task:**
- Predict direction of each lab at `t_target` (next measurement or 24-48h post-intervention)
- Explain WHY each lab will reverse or not, given THIS PATIENT's state

**Example case structure:**
```
Patient: 65M, CKD Stage 2, HTN, prior MI
Procedure: PTCA on LAD, 2163-01-16 10:00
Contrast volume: 180 mL

All available labs from admission to 2163-01-16 18:00 (8h post-intervention):
├── Troponin:    0.15 → 0.28 → 0.45 → 0.52 (rising trend, visible)
├── CK:          250 → 450 → 490 (rising trend, visible)
├── Creatinine:  1.1 → 1.1 → 1.15 (stable/slowly rising, visible)
├── BNP:         450 → 460 (stable, visible)
├── WBC:         7.2 → 8.1 (rising)
├── Glucose:     145 → 180 (rising from stress)
└── ... (all other labs available)

Prediction target: 2163-01-17 10:00 (24h post-procedure)

Model must predict:
- Troponin: falling OR rising? (visible says rising, but intervention restores perfusion→washout)
- CK: falling OR rising? (post-op elevation continues, then falls as myocardial stress resolves)
- Creatinine: rising OR stable? (contrast exposure, but patient has CKD—higher risk)
- BNP: falling OR rising? (depends on intervention success, hemodynamic improvement)

AND explain mechanisms tied to THIS patient:
- "Troponin will fall because PTCA restores LAD perfusion, but patient has CKD so
   creatinine might rise from contrast toxicity. Previous MI means slower troponin
   clearance, so expect fall but not to baseline for days."
```

---

## Phase 2: Reversal Timing (Flexible, Anywhere in Timeline)

### Multiple Reversal Windows

Reversals can happen **anywhere** in the patient's hospital stay, not just post-intervention:

```
ADMISSION                                        DISCHARGE
│                                                    │
├─ PRE-PROCEDURE PHASE (Days 1-2)
│  ├─ Troponin rising (MI developing)
│  ├─ CK rising (enzyme release from infarction)
│  ├─ Can labs REVERSE here? YES
│  │  └─ Example: Troponin rises then falls (small infarction self-limiting)
│  │  └─ Example: CK peaks then starts declining (myocardial necrosis complete)
│  └─ Patient just hasn't reached peak yet
│
├─ INTERVENTION WINDOW (Minutes to Hours)
│  ├─ Procedure occurs (PTCA, CABG, stent, etc.)
│  ├─ Can labs REVERSE during procedure? YES
│  │  └─ Immediate response to successful reperfusion
│  │  └─ Real-time troponin response if monitoring
│  └─ Rarely captured (labs not measured minute-by-minute)
│
├─ IMMEDIATE POST (0-6h)
│  ├─ Post-operative stress, initial recovery phase
│  ├─ Can labs REVERSE? YES
│  │  └─ Example: Troponin starts falling immediately (good reperfusion)
│  │  └─ Example: CK continues rising (expected post-op enzyme release)
│  └─ Most dramatic immediate changes
│
├─ SHORT-TERM POST (6-24h)
│  ├─ Peak post-operative stress, peak enzyme elevation
│  ├─ Can labs REVERSE? YES (MOST COMMON WINDOW)
│  │  └─ Example: CK peaks at 18h then starts falling
│  │  └─ Example: Troponin falls as washout completes
│  └─ Intervention effects now visible
│
├─ MEDIUM-TERM POST (24-72h)
│  ├─ Complications emerge, resolution begins
│  ├─ Can labs REVERSE? YES
│  │  └─ Example: Creatinine rises (CIN peak) despite good cardiac output
│  │  └─ Example: BNP continues falling (heart recovers)
│  └─ Delayed responses visible
│
└─ LATE RECOVERY (72h+)
   ├─ Discharge planning phase
   ├─ Can labs REVERSE? YES
   │  └─ Example: Troponin stabilizes (washout complete)
   │  └─ Example: Creatinine stabilizes (acute injury peak passed)
   └─ Chronic baselines reestablish
```

### Case Types (Anywhere in Timeline)

```
1. PRE-PROCEDURE REVERSAL (Days 1-2 before intervention)
   - Natural disease progression independent of intervention
   - Example: Troponin rises then falls (small non-interventional MI)
   - Example: CK peaks naturally as myocardial necrosis completes
   - Tests: Can model predict reversals from physiology alone, pre-procedure?

2. PERI-PROCEDURE REVERSAL (During or immediately after procedure)
   - Immediate response to intervention success/failure
   - Example: Troponin response to reperfusion (0-3h post-PTCA)
   - Example: CK starts falling if post-op inflammation controlled
   - Tests: Can model predict immediate procedure effects?

3. IMMEDIATE POST REVERSAL (0-6h post-procedure)
   - Early post-operative response
   - Example: Troponin still rising despite successful PTCA (washout lag)
   - Example: CK rapid elevation from surgical trauma

4. SHORT-TERM POST REVERSAL (6-24h post-procedure)
   - Peak post-operative phase
   - Example: CK peaks at 18-24h then starts falling
   - Example: Troponin falls as reperfusion enables washout
   - MOST COMMON reversal window

5. MEDIUM-TERM POST REVERSAL (24-72h post-procedure)
   - Delayed responses and complications
   - Example: Creatinine rises despite good cardiac recovery (CIN)
   - Example: BNP continues falling (ventricular remodeling)

6. LATE REVERSAL (72h+)
   - Long-term resolution
   - Example: Troponin stabilizes as washout completes
   - Example: Creatinine stabilizes (CIN peak passed, recovery begins)

7. NON-REVERSAL (Any timing)
   - Trend continues as expected
   - Example: Troponin keeps rising (intervention failed)
   - Example: CK keeps rising (severe post-op inflammation)
   - Example: Creatinine stays stable (no kidney injury)

8. MULTI-LAB MIXED (Any timing)
   - Some labs reverse, some don't
   - Example: Troponin falls, CK rises, Creatinine rises
   - Example: Some labs pre-procedure, some post-procedure
```

### Selection Logic

```python
def find_reversals_all_timeline(lab_series, procedure_time, admission_time):
    """
    Find all (visible_idx, target_idx) pairs ANYWHERE in the timeline where:
    - visible_idx: any measurement (can be pre, peri, or post-procedure)
    - target_idx: any later measurement
    - visible_trend ≠ actual_direction (REVERSAL)
    - actual_delta ≥ 10%
    - Any time gap from 1h to 72h
    """
    reversals = []
    
    # PRE-PROCEDURE REVERSALS (before procedure_time)
    # Example: Troponin rising on day 1, then falling on day 2 (before intervention)
    for visible_idx in range(len(lab_series)):
        t_visible = lab_series[visible_idx].time
        
        # Only consider if well before procedure (≥12h before)
        if t_visible >= procedure_time - timedelta(hours=12):
            continue
        
        for target_idx in range(visible_idx + 1, len(lab_series)):
            t_target = lab_series[target_idx].time
            
            # Only target measurements still before procedure
            if t_target >= procedure_time:
                continue
            
            gap_hours = (t_target - t_visible).total_seconds() / 3600
            if not (1 <= gap_hours <= 48):  # Flexible gap
                continue
            
            vis_trend = direction(lab_series[visible_idx-1], lab_series[visible_idx])
            actual_dir = direction(lab_series[visible_idx], lab_series[target_idx])
            
            if vis_trend != actual_dir and vis_trend != 'stable':
                reversals.append({
                    'window': 'pre_procedure',
                    'visible_time': t_visible,
                    'target_time': t_target,
                    'trend': vis_trend,
                    'direction': actual_dir
                })
    
    # POST-PROCEDURE REVERSALS (after procedure_time)
    # Break into windows, or scan all
    for visible_idx in range(len(lab_series)):
        t_visible = lab_series[visible_idx].time
        
        # Only consider if after procedure
        if t_visible < procedure_time:
            continue
        
        for target_idx in range(visible_idx + 1, len(lab_series)):
            t_target = lab_series[target_idx].time
            
            gap_hours = (t_target - t_visible).total_seconds() / 3600
            if not (1 <= gap_hours <= 72):  # Flexible gap post-procedure
                continue
            
            # OPTIONAL: Classify into windows for analysis
            hours_post_proc = (t_visible - procedure_time).total_seconds() / 3600
            if hours_post_proc < 6:
                window = 'immediate'
            elif hours_post_proc < 24:
                window = 'shortterm'
            elif hours_post_proc < 72:
                window = 'mediumterm'
            else:
                window = 'late'
            
            vis_trend = direction(lab_series[visible_idx-1], lab_series[visible_idx])
            actual_dir = direction(lab_series[visible_idx], lab_series[target_idx])
            
            if vis_trend != actual_dir and vis_trend != 'stable':
                reversals.append({
                    'window': f'post_procedure_{window}',
                    'visible_time': t_visible,
                    'target_time': t_target,
                    'trend': vis_trend,
                    'direction': actual_dir,
                    'hours_post_proc': hours_post_proc
                })
    
    return reversals
```

### Key Changes
- **Not constrained to post-procedure** — scans entire timeline
- **Pre-procedure reversals included** — natural disease progression
- **Any gap 1-72h** — flexible windows, not fixed
- **Classified by phase** — but no restrictions

---

## Phase 3: All Available Labs (Not Just Pre-Procedure)

### Lab Timeline Expansion

**Currently:** Only pre-procedure labs shown
**New:** ALL labs from admission up to `t_visible`, with flags for:
- Which labs are abnormal vs normal
- Patient baseline for each lab
- Trend direction

### Lab Table Structure

```
Timestamp        | Troponin | CK   | Creatinine | BNP | WBC | Glucose | Note
2163-01-14 08:00 | 0.02     | 95   | 1.1        | 85  | 6.8 | 110     | Admission
2163-01-14 16:00 | 0.04     | 110  | 1.1        | 92  | 7.2 | 140     | Chest pain
2163-01-15 08:00 | 0.15     | 250  | 1.1        | 120 | 7.5 | 155     | Rising troponin
2163-01-15 18:00 | 0.28     | 390  | 1.12       | 250 | 7.8 | 180     | MI suspected
2163-01-16 08:00 | 0.45     | 450  | 1.15       | 380 | 8.1 | 190     | On IV fluids
2163-01-16 10:00 | 0.52     | 490  | 1.15       | 420 | —   | —       | [PROCEDURE: PTCA+stent]
2163-01-16 18:00 | 0.48     | 520  | 1.18       | 440 | 8.3 | 200     | Post-op stress peak
2163-01-17 10:00 | 0.42     | 480  | 1.22       | 380 | 7.9 | 160     | [PREDICTION TARGET: reversal]
```

### Patient Context

```json
{
  "demographics": {
    "age": 65,
    "gender": "M",
    "bmi": 28.5
  },
  "comorbidities": [
    "CKD Stage 2 (eGFR 60)",
    "Hypertension",
    "Prior MI (2 years ago)",
    "Diabetes Type 2"
  ],
  "baseline_labs": {
    "Creatinine": "1.0-1.1 mg/dL (outpatient)",
    "Troponin": "<0.04 ng/mL",
    "BNP": "50-100 pg/mL"
  },
  "procedure": {
    "name": "PTCA + DES on LAD",
    "time": "2163-01-16 10:00",
    "contrast_volume": 180,
    "pre_hydration": "1L NS bolus"
  },
  "critical_context": "CKD + high contrast volume = elevated CIN risk"
}
```

---

## Phase 4: Patient-Specific Causal Justification

### Problem with Generic Reasoning

❌ BAD: "Troponin will fall because PTCA restores perfusion"
- True for healthy patients
- Doesn't account for THIS patient

### Solution: Patient-Specific Mechanisms

✅ GOOD: "Troponin will fall because:
  - PTCA restores LAD perfusion (reperfusion washout)
  - Patient is 65, so clearance slower than younger patient
  - BUT prior MI means some stunned myocardium won't clear as fast
  - Expect 15-20% decline by 24h, then plateau"

### Justification Requirements

Model must address (for EACH lab):

1. **Procedure mechanism** — What does the intervention do?
   - PTCA: restores perfusion
   - CABG: bypasses occlusion (but surgery causes trauma)
   - Stent: maintains patency (but thrombosis risk)

2. **Patient baseline** — What's THIS patient's starting point?
   - Kidney function? (affects creatinine + troponin clearance)
   - Prior MI? (affects troponin elevation/kinetics)
   - Comorbidities? (affects response)

3. **Procedure-specific risks** — What complications for THIS patient?
   - High contrast volume + CKD = CIN risk → creatinine rises
   - Post-op trauma + diabetes = prolonged CK elevation
   - Stent insertion = thrombosis risk (troponin could re-rise)

4. **Timeline** — When do effects manifest?
   - Immediate (0-6h): troponin continues rising (washout lag)
   - Short-term (6-24h): peak then decline, enzyme rises from trauma
   - Medium-term (24-72h): CIN emerges if present, troponin clears

5. **Reversal prediction** — Why will the trend reverse (or not)?
   - "Troponin rising now, but will fall at 24h because: reperfusion enables
     clearance, and this patient's kidney function is intact so no washout delay"
   - "CK will continue rising through 24h despite procedure because: post-op
     inflammation peaks at 24-36h, this patient has diabetes (delayed resolution)"

### Scoring Rubric for Justification

| Score | Criteria |
|---|---|
| **1.0** | Explains mechanism + baseline + complications + timeline + patient-specific modifiers for EACH lab |
| **0.75** | Mechanism + baseline clear; timeline/complications mentioned; some patient specificity |
| **0.5** | Generic mechanism without patient context; explains 2/4 labs specifically |
| **0.25** | Vague; barely addresses mechanism or patient |
| **0.0** | No justification or nonsensical |

---

## Phase 5: Data Extraction

### Required MIMIC-IV Tables

```
labevents.csv.gz
├── hadm_id, subject_id
├── itemid (LOINC code)
├── valuenum (lab value)
├── valueuom (units)
├── charttime (when drawn)
└── flag (if abnormal)

d_labitems.csv.gz
├── itemid
├── label (e.g., "Troponin T")
└── loinc_code

procedures_icd.csv
├── hadm_id
├── seq_num
├── icd9_code / icd10_code
└── long_title (procedure name)

admissions.csv
├── hadm_id, subject_id
├── admission_type
├── admission_location
├── admission_time
└── discharge_time

patients.csv
├── subject_id
├── gender
├── dob (for age calculation)
```

### Lab Code Mappings

```python
TROPONIN_CODES = {
    'LOINC/6597-9': 'Troponin T',      # Troponin T cardiac
    'LOINC/10839-9': 'Troponin I',      # Troponin I cardiac
    'LOINC/42757-5': 'Troponin I',      # Troponin I high sensitivity
}

CK_CODES = {
    'LOINC/2157-6': 'CK total',         # Creatine kinase
    'LOINC/2154-3': 'CK-MB',            # CK-MB cardiac
}

CREATININE_CODES = {
    'LOINC/2160-0': 'Creatinine',       # Serum creatinine
}

BNP_CODES = {
    'LOINC/42637-9': 'BNP',             # B-type natriuretic peptide
    'LOINC/33762-6': 'NT-proBNP',       # N-terminal pro-BNP
    'LOINC/30934-4': 'BNP alt',
}

COMORBIDITY_INDICATORS = {
    'ICD10CM/N18': 'CKD',
    'ICD10CM/I10': 'Hypertension',
    'ICD10CM/I21': 'MI (acute)',
    'ICD10CM/I25': 'Prior MI',
    'ICD10CM/E11': 'Diabetes Type 2',
}
```

### Procedure Codes to Include

```python
CARDIAC_PROCEDURES = {
    'ICD9/36.01': 'PTCA',
    'ICD9/36.05': 'PTCA with stent',
    'ICD10/021040': 'PTCA with stent',
    'ICD9/88.53': 'Coronary angiography',
    'ICD10/021341': 'Coronary angiography',
    'ICD9/36.03': 'CABG',
    'ICD10/021109': 'CABG',
}
```

---

## Phase 6: Case Generation Algorithm

### Step 1: Find Candidates

```python
def find_candidates():
    """
    Find hadm_ids with:
    - Cardiac diagnosis (MI, ACS, CAD)
    - Cardiac procedure (PTCA, CABG, angiography)
    - ≥2 troponin, ≥2 CK, ≥1 creatinine, ≥0 BNP in 48h window
    """
    candidates = []
    for hadm_id in cardiac_admits:
        proc = get_first_cardiac_procedure(hadm_id)
        if not proc:
            continue
        
        labs = get_all_labs(hadm_id, 
                            start=proc_time - 48h,
                            end=proc_time + 72h)
        
        if len(labs['Troponin']) >= 2 and len(labs['CK']) >= 2:
            candidates.append({
                'hadm_id': hadm_id,
                'procedure': proc,
                'labs': labs,
            })
    
    return candidates
```

### Step 2: Detect Reversals Across Windows

```python
def find_reversals(labs, procedure_time):
    """
    For each lab, find (visible_time, target_time) pairs where:
    - visible: last value before target
    - trend: visible_value vs prior value
    - actual: target value
    - Check: trend ≠ actual direction
    """
    reversals_by_window = {
        'immediate': [],    # 0-6h post-procedure
        'shortterm': [],    # 6-24h post-procedure
        'mediumterm': [],   # 24-72h post-procedure
        'arbitrary': [],    # Any 4-72h gap
    }
    
    for window_name, visible_offset, target_offsets in [
        ('immediate', timedelta(hours=2), 
         [timedelta(hours=4), timedelta(hours=6)]),
        ('shortterm', timedelta(hours=6),
         [timedelta(hours=12), timedelta(hours=18), timedelta(hours=24)]),
        ('mediumterm', timedelta(hours=24),
         [timedelta(hours=48), timedelta(hours=72)]),
    ]:
        for lab_name in ['Troponin', 'CK', 'Creatinine', 'BNP']:
            lab_series = labs[lab_name]
            t_visible = procedure_time + visible_offset
            
            for t_target in target_offsets:
                visible_val = find_closest_lab(lab_series, t_visible)
                target_val = find_closest_lab(lab_series, t_target)
                
                if visible_val and target_val:
                    vis_trend = direction(lab_series[-2], visible_val)
                    actual_dir = direction(visible_val, target_val)
                    
                    if vis_trend != actual_dir:
                        reversals_by_window[window_name].append({
                            'lab': lab_name,
                            'visible_time': t_visible,
                            'target_time': t_target,
                            'visible_trend': vis_trend,
                            'actual_direction': actual_dir,
                        })
    
    return reversals_by_window
```

### Step 3: Build Case

For each selected reversal/non-reversal, create JSON with:
- Demographics + comorbidities
- All labs from admission to `t_visible`
- Procedure details
- Visible trends
- Ground truth directions
- Reversal indicators

---

## Phase 7: Benchmark Structure

### 100 Target Cases Distribution (Anywhere in Timeline)

```
PRE-PROCEDURE REVERSALS (10 cases):
├─ Natural disease progression before intervention
├─ Example: Troponin rises day 1, falls day 2 (before PTCA)
├─ Example: CK peaks naturally (myocardial necrosis complete)
├─ Tests: Can model reason about physiology independent of procedure?
└─ Distribution: Various labs, various reversals

PERI-PROCEDURE REVERSALS (5 cases):
├─ Immediate response (within hours of procedure)
├─ Example: Troponin response to reperfusion (0-3h post-PTCA)
├─ Example: CK elevation from surgical trauma
└─ Tests: Can model predict real-time intervention effects?

IMMEDIATE POST-PROCEDURE REVERSALS (10 cases):
├─ 0-6h post-procedure phase
├─ Example: Troponin still rising (washout lag)
├─ Example: CK elevation peak
└─ Multiple labs: Troponin, CK, Creatinine early indicators

SHORT-TERM POST-PROCEDURE REVERSALS (35 cases):
├─ 6-24h post-procedure phase [MOST COMMON REVERSAL WINDOW]
├─ Example: CK peaks at 18h then falls
├─ Example: Troponin falls as reperfusion washout completes
├─ Example: BNP falls as heart recovers
└─ Distribution: All 4 labs, various reversal combinations

MEDIUM/LATE POST-PROCEDURE REVERSALS (10 cases):
├─ 24-72h+ post-procedure phase
├─ Example: Creatinine rises at 48h (CIN peak)
├─ Example: Troponin/BNP stabilize
└─ Tests: Can model predict delayed complications?

NON-REVERSAL CASES (20):
├─ Trends continue as expected (no reversal)
├─ Example: Troponin keeps rising (intervention failed)
├─ Example: CK keeps rising (severe post-op inflammation)
├─ Example: Creatinine stays stable (no kidney injury)
└─ Distribution: Pre-procedure, immediate, short-term, medium-term

MIXED COMPLEXITY CASES (10):
├─ Some labs reverse, some don't
├─ Some reversals pre-procedure, some post
├─ Example: Troponin reverses (falls), CK doesn't (keeps rising)
├─ Example: Troponin reverses immediate, Creatinine reverses at 48h
└─ Tests: Can model handle multi-phase, multi-lab complexity?
```

**Key insight:** Cases span the ENTIRE timeline, testing whether the model can reason about:
- Pre-intervention physiology (natural disease course)
- Procedure effects (real-time intervention response)
- Post-intervention recovery (immediate + delayed)
- Complications (CIN, re-infarction, persistent elevation)

---

## Phase 8: Evaluation

### Agent Task

```
Given:
- Patient demographics + comorbidities
- All labs from admission to t_visible
- Procedure name + time + details

Predict:
- For each lab (Troponin, CK, Creatinine, BNP):
  - Direction at t_target (rising/falling/stable)
  - Patient-specific justification (mechanism + baseline + complications)
  - Confidence level

Format: JSON with structured output + free-text justification
```

### Scoring

```
PER-LAB:
- Direction accuracy: 1.0 if correct, 0.0 if wrong
- Reversal detection: 1.0 if reversal correctly identified
- Justification quality: 0.0-1.0 based on patient specificity

OVERALL:
= (0.50 × mean_direction_accuracy) 
+ (0.30 × mean_reversal_detection)
+ (0.20 × mean_justification_quality)

Range: 0.0-1.0
```

---

## Advantages Over Original Plan

✅ **Flexible timing** — Capture reversals at realistic intervals (not just arbitrary gaps)  
✅ **Immediate reversals** — Real post-intervention complications detected early  
✅ **All available labs** — Richer context for causal reasoning  
✅ **Patient-specific** — Not generic mechanisms; requires understanding THIS patient  
✅ **Multi-lab** — Troponin + CK + Creatinine + BNP tracked simultaneously  
✅ **Clinically realistic** — Mirrors actual ICU monitoring workflow  

---

## Next Steps

1. **Validate data availability** in MIMIC-IV
2. **Implement extraction** (Phase 5)
3. **Generate candidates** (Phase 6 Step 1-2)
4. **Build balanced cases** (Phase 6 Step 3)
5. **Create evaluation scripts** (Phase 7-8)
