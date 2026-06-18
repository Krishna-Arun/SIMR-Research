export const meta = {
  name: 'aki-benchmark-10003400',
  description: 'AKI next-event benchmark — patient 10003400 (72F) ground truth: Respiratory Ventilation, 24-96 Consecutive Hours',
  phases: [
    { title: 'Generate', detail: 'Draft question stem (no lab values) + classify L_core / L_optional / L_irrelevant' },
    { title: 'Evaluate', detail: 'Strict 4-criterion check (A/B/C/D); reject and loop up to 5x if any fails' },
    { title: 'Rubric',   detail: 'Build personalized answer rubric + full lab-set scoring rubric' },
  ],
}

// ─── patient data (embedded — no args dependency) ─────────────────────────────
const PATIENT = {
  "patient_id": "10003400",
  "age": 72,
  "gender": "Female",
  "ground_truth": "Respiratory Ventilation, 24-96 Consecutive Hours",
  "diagnoses": [
    "Disruption of external operation (surgical) wound, not elsewhere classified, initial encounter",
    "Severe sepsis with septic shock",
    "Acute respiratory failure with hypoxia",
    "Acute kidney failure, unspecified",
    "Sepsis, unspecified organism",
    "Encephalopathy, unspecified",
    "Multiple myeloma not having achieved remission",
    "Malignant pleural effusion"
  ],
  "admission_history": [
    {
      "admit_date": "2134-06-06",
      "discharge_date": "2134-06-07",
      "admission_type": "EW EMER.",
      "discharge_location": "HOME HEALTH CARE",
      "diagnoses": [
        "Microscopic hematuria",
        "Multiple myeloma, without mention of having achieved remission",
        "Anticoagulants causing adverse effects in therapeutic use",
        "Atrial fibrillation",
        "Unspecified essential hypertension",
        "Obesity, unspecified",
        "Long-term (current) use of anticoagulants",
        "Other nonspecific findings on examination of urine"
      ],
      "procedures_performed": [],
      "medications": [
        "Acetaminophen",
        "Amlodipine",
        "Clarithromycin",
        "Furosemide",
        "Lenalidomide (Revlimide)15mg ",
        "Lisinopril",
        "Metoprolol Tartrate",
        "Phytonadione",
        "Pneumococcal Vac Polyvalent",
        "Sodium Chloride 0.9%  Flush",
        "Vitamin D"
      ]
    },
    {
      "admit_date": "2136-11-04",
      "discharge_date": "2136-11-12",
      "admission_type": "EW EMER.",
      "discharge_location": "SKILLED NURSING FACILITY",
      "diagnoses": [
        "Malignant neoplasm of other sites of rectum, rectosigmoid junction, and anus",
        "Other drug-induced pancytopenia",
        "Multiple myeloma, without mention of having achieved remission",
        "Hypotension, unspecified",
        "Atrial fibrillation",
        "Chronic kidney disease, Stage III (moderate)",
        "Acute posthemorrhagic anemia",
        "Long-term (current) use of anticoagulants"
      ],
      "procedures_performed": [
        "Biopsy of anus",
        "Colonoscopy"
      ],
      "medications": [
        "Acetaminophen",
        "Bag",
        "Calcium Carbonate",
        "Clarithromycin",
        "Diltiazem Extended-Release",
        "Docusate Sodium",
        "Furosemide",
        "HYDROmorphone (Dilaudid)",
        "Hemorrhoidal Suppository",
        "Influenza Vaccine Quadrivalent",
        "Lidocaine Jelly 2%",
        "Magnesium Citrate"
      ]
    },
    {
      "admit_date": "2136-12-09",
      "discharge_date": "2136-12-15",
      "admission_type": "EW EMER.",
      "discharge_location": "SKILLED NURSING FACILITY",
      "diagnoses": [
        "Atrial fibrillation",
        "Other drug-induced pancytopenia",
        "Acute kidney failure, unspecified",
        "Intestinal infection due to Clostridium difficile",
        "Multiple myeloma, without mention of having achieved remission",
        "Hypotension, unspecified",
        "Acidosis",
        "Other adrenal hypofunction"
      ],
      "procedures_performed": [],
      "medications": [
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "Acetaminophen",
        "Bag",
        "CeftriaXONE",
        "Diltiazem",
        "Diltiazem Extended-Release",
        "Docusate Sodium",
        "Fluconazole",
        "Furosemide",
        "Heparin Flush (10 units/ml)",
        "Heparin Flush (100 units/ml)",
        "Magnesium Sulfate"
      ]
    },
    {
      "admit_date": "2136-12-31",
      "discharge_date": "2137-01-03",
      "admission_type": "EW EMER.",
      "discharge_location": "SKILLED NURSING FACILITY",
      "diagnoses": [
        "Other encephalopathy",
        "Multiple myeloma, without mention of having achieved remission",
        "Malignant neoplasm of anus, unspecified site",
        "Atrial fibrillation",
        "Obesity, unspecified",
        "Body Mass Index 31.0-31.9, adult",
        "Osteoarthrosis, localized, not specified whether primary or secondary, lower leg",
        "Hypertensive chronic kidney disease, unspecified, with chronic kidney disease stage I through stage IV, or unspecified"
      ],
      "procedures_performed": [],
      "medications": [
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "Bag",
        "CeftriaXONE",
        "Diltiazem Extended-Release",
        "Docusate Sodium",
        "Furosemide",
        "Heparin",
        "Heparin Flush (10 units/ml)",
        "Heparin Flush (100 units/ml)",
        "Magnesium Oxide",
        "Magnesium Sulfate",
        "Metoprolol Tartrate"
      ]
    },
    {
      "admit_date": "2137-02-07",
      "discharge_date": "2137-02-18",
      "admission_type": "EW EMER.",
      "discharge_location": "SKILLED NURSING FACILITY",
      "diagnoses": [
        "Malignant neoplasm of rectum",
        "Hemorrhage of rectum and anus",
        "Multiple myeloma, without mention of having achieved remission",
        "Disorders of phosphorus metabolism",
        "Atrial fibrillation",
        "Calculus of ureter",
        "Anticoagulants causing adverse effects in therapeutic use",
        "Neoplasm related pain (acute) (chronic)"
      ],
      "procedures_performed": [
        "Other radiotherapeutic procedure"
      ],
      "medications": [
        "0.9% Sodium Chloride",
        "5% Dextrose",
        "Acetaminophen",
        "Aluminum-Magnesium Hydrox.-Simethicone",
        "Aquaphor Ointment",
        "Bisacodyl",
        "Calcium Carbonate",
        "Calcium Gluconate",
        "Citalopram",
        "Dexamethasone",
        "Diltiazem",
        "Diltiazem Extended-Release"
      ]
    },
    {
      "admit_date": "2137-02-24",
      "discharge_date": "2137-03-19",
      "admission_type": "URGENT",
      "discharge_location": "CHRONIC/LONG TERM ACUTE CARE",
      "diagnoses": [
        "Malignant neoplasm of anus, unspecified site",
        "Defibrination syndrome",
        "Acute respiratory failure",
        "Acute kidney failure with lesion of tubular necrosis",
        "Systemic inflammatory response syndrome due to noninfectious process with acute organ dysfunction",
        "Multiple myeloma, without mention of having achieved remission",
        "Unspecified protein-calorie malnutrition",
        "Postoperative shock, other"
      ],
      "procedures_performed": [
        "Attachment of pedicle or flap graft to other sites",
        "Other lysis of peritoneal adhesions",
        "Continuous invasive mechanical ventilation for less than 96 consecutive hours",
        "Application or administration of an adhesion barrier substance",
        "Other partial resection of small intestine",
        "Open abdominoperineal resection of the rectum",
        "Other and open repair of other hernia of anterior abdominal wall with graft or prosthesis",
        "Central venous catheter placement with guidance",
        "Enteral infusion of concentrated nutritional substances",
        "Nonexcisional debridement of wound, infection or burn"
      ],
      "medications": [
        "0.9% Sodium Chloride",
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "5% Dextrose",
        "5% Dextrose (EXCEL BAG)",
        "Acetaminophen",
        "Acetaminophen (Liquid)",
        "Acetaminophen IV",
        "Albumin 25% (12.5g / 50mL)",
        "Albumin 5% (25g / 500mL)",
        "Amiodarone",
        "Aquaphor Ointment",
        "Artificial Tears"
      ]
    }
  ],
  "lab_data": [
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Creatinine",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0.4",
      "ref_upper": "1.1"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "BUN",
      "value": "35",
      "flag": "abnormal",
      "ref_lower": "6",
      "ref_upper": "20"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-21",
      "label": "Potassium",
      "value": "3.1",
      "flag": "abnormal",
      "ref_lower": "3.3",
      "ref_upper": "5.1"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-07",
      "label": "Sodium",
      "value": "132",
      "flag": "abnormal",
      "ref_lower": "133",
      "ref_upper": "145"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-10",
      "label": "Bicarbonate",
      "value": "21",
      "flag": "abnormal",
      "ref_lower": "22",
      "ref_upper": "32"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-10",
      "label": "Anion Gap",
      "value": "21",
      "flag": "abnormal",
      "ref_lower": "8",
      "ref_upper": "20"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-26",
      "label": "Phosphate",
      "value": "2.6",
      "flag": "abnormal",
      "ref_lower": "2.7",
      "ref_upper": "4.5"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Albumin",
      "value": "2.4",
      "flag": "abnormal",
      "ref_lower": "3.5",
      "ref_upper": "5.2"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-18",
      "label": "WBC",
      "value": "10.2",
      "flag": "abnormal",
      "ref_lower": "4",
      "ref_upper": "10"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Hemoglobin",
      "value": "8.3",
      "flag": "abnormal",
      "ref_lower": "11.2",
      "ref_upper": "15.7"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Hematocrit",
      "value": "25.3",
      "flag": "abnormal",
      "ref_lower": "34",
      "ref_upper": "45"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Platelet Count",
      "value": "107",
      "flag": "abnormal",
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "NTproBNP",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0",
      "ref_upper": "624"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "INR",
      "value": "1.4",
      "flag": "abnormal",
      "ref_lower": "0.9",
      "ref_upper": "1.1"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-08",
      "label": "PT",
      "value": "54.4",
      "flag": "abnormal",
      "ref_lower": "25",
      "ref_upper": "36.5"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "100"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Calcium, Total",
      "value": "8.1",
      "flag": "abnormal",
      "ref_lower": "8.4",
      "ref_upper": "10.3"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-07",
      "label": "Chloride",
      "value": "95",
      "flag": "abnormal",
      "ref_lower": "96",
      "ref_upper": "108"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Prothrombin Time",
      "value": "15.2",
      "flag": "abnormal",
      "ref_lower": "9.4",
      "ref_upper": "12.5"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Neutrophils",
      "value": "14",
      "flag": "abnormal",
      "ref_lower": "19",
      "ref_upper": "53"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Lymphocytes",
      "value": "25",
      "flag": "abnormal",
      "ref_lower": "5",
      "ref_upper": "13"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "C-Reactive Protein",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0",
      "ref_upper": "5"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Magnesium",
      "value": "2.1",
      "flag": null,
      "ref_lower": "1.6",
      "ref_upper": "2.6"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Urine Casts",
      "value": "5.5",
      "flag": null,
      "ref_lower": "5",
      "ref_upper": "8"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-10",
      "label": "Lactate",
      "value": "0.8",
      "flag": null,
      "ref_lower": "0.5",
      "ref_upper": "2"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-10",
      "label": "BNP",
      "value": "22",
      "flag": null,
      "ref_lower": "21",
      "ref_upper": "30"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "ALT",
      "value": "6",
      "flag": null,
      "ref_lower": "0",
      "ref_upper": "40"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "AST",
      "value": "18",
      "flag": null,
      "ref_lower": "0",
      "ref_upper": "40"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Bands",
      "value": "0",
      "flag": null,
      "ref_lower": "0",
      "ref_upper": "5"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-05",
      "label": "Eosinophils",
      "value": "3",
      "flag": null,
      "ref_lower": "1",
      "ref_upper": "7"
    },
    {
      "hadm_id": "23559586",
      "date": "2137-08-06",
      "label": "Uric Acid",
      "value": "82",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    }
  ]
}

// ─── scoring constants ────────────────────────────────────────────────────────
const WEIGHTS       = { w1: 0.35, w2: 0.20, w3: 0.10, w4: 0.20, w5: 0.15 }
const PENALTY_PARAMS = { beta: 2.0, alpha: 0.5, epsilon: 1e-6 }

// ─── schemas ──────────────────────────────────────────────────────────────────

const LAB_ITEM_SCHEMA = {
  type: 'object',
  required: ['lab_name', 'clinical_rationale'],
  properties: {
    lab_name:           { type: 'string' },
    clinical_rationale: { type: 'string' },
  },
}

const QUESTION_SCHEMA = {
  type: 'object',
  required: ['question_stem', 'reasoning_gap', 'lab_sets'],
  properties: {
    question_stem: { type: 'string', description: 'Full question. ZERO numeric lab values.' },
    reasoning_gap: { type: 'string', description: 'One sentence: what labs are the missing piece.' },
    lab_sets: {
      type: 'object',
      required: ['L_core', 'L_optional', 'L_irrelevant'],
      properties: {
        L_core:      { type: 'array', items: LAB_ITEM_SCHEMA },
        L_optional:  { type: 'array', items: LAB_ITEM_SCHEMA },
        L_irrelevant: {
          type: 'array',
          items: {
            type: 'object',
            required: ['lab_name', 'why_irrelevant'],
            properties: {
              lab_name:       { type: 'string' },
              why_irrelevant: { type: 'string' },
            },
          },
        },
      },
    },
  },
}

const EVAL_SCHEMA = {
  type: 'object',
  required: [
    'pass',
    'criterion_a_pass', 'criterion_a_verdict', 'criterion_a_feedback',
    'criterion_b_pass', 'criterion_b_verdict', 'criterion_b_feedback',
    'criterion_c_pass', 'criterion_c_verdict', 'criterion_c_feedback',
    'criterion_d_pass', 'criterion_d_verdict', 'criterion_d_feedback',
  ],
  properties: {
    pass:                 { type: 'boolean' },
    criterion_a_pass:     { type: 'boolean' },
    criterion_a_verdict:  { type: 'string', enum: ['PASS', 'FAIL'] },
    criterion_a_feedback: { type: 'string' },
    criterion_b_pass:     { type: 'boolean' },
    criterion_b_verdict:  { type: 'string', enum: ['PASS', 'FAIL'] },
    criterion_b_feedback: { type: 'string' },
    criterion_c_pass:     { type: 'boolean' },
    criterion_c_verdict:  { type: 'string', enum: ['PASS', 'FAIL'] },
    criterion_c_feedback: { type: 'string' },
    criterion_d_pass:     { type: 'boolean' },
    criterion_d_verdict:  { type: 'string', enum: ['PASS', 'FAIL'] },
    criterion_d_feedback: { type: 'string' },
  },
}

const RUBRIC_SCHEMA = {
  type: 'object',
  required: ['answer_rubric', 'lab_scoring_rubric', 'final_reward_formula'],
  properties: {
    answer_rubric: {
      type: 'object',
      required: [
        'c1_exact_answer', 'c1_accepted_synonyms', 'c1_scoring_guidance', 'c1_wrong_answers',
        'c2_required_labs_summary', 'c2_scoring_guidance', 'c2_insufficient_examples',
        'c3_causal_chain', 'c3_required_steps', 'c3_scoring_guidance', 'c3_broken_chain_examples',
        'c4_required_patient_facts', 'c4_scoring_guidance', 'c4_critical_errors',
      ],
      properties: {
        c1_exact_answer:           { type: 'string' },
        c1_accepted_synonyms:      { type: 'array', items: { type: 'string' } },
        c1_scoring_guidance:       { type: 'string' },
        c1_wrong_answers:          { type: 'array', items: { type: 'string' } },
        c2_required_labs_summary:  { type: 'string', description: 'One line per lab: LAB (VALUE) — why it drives the decision.' },
        c2_scoring_guidance:       { type: 'string' },
        c2_insufficient_examples:  { type: 'array', items: { type: 'string' } },
        c3_causal_chain:           { type: 'string' },
        c3_required_steps:         { type: 'array', items: { type: 'string' } },
        c3_scoring_guidance:       { type: 'string' },
        c3_broken_chain_examples:  { type: 'array', items: { type: 'string' } },
        c4_required_patient_facts: { type: 'string', description: 'One line per fact: FACT — why it matters.' },
        c4_scoring_guidance:       { type: 'string' },
        c4_critical_errors:        { type: 'array', items: { type: 'string' } },
      },
    },
    lab_scoring_rubric: {
      type: 'object',
      required: [
        'L_core_summary', 'L_optional_summary', 'L_irrelevant_summary',
        'R_core_formula', 'R_core_weight', 'R_core_interpretation',
        'R_wrong_formula', 'R_wrong_weight', 'R_wrong_interpretation',
        'R_under_formula', 'R_under_weight', 'R_under_beta', 'R_under_interpretation',
        'R_over_formula', 'R_over_weight', 'R_over_alpha', 'R_over_interpretation',
        'justification_weight', 'justification_score_0', 'justification_score_0_5', 'justification_score_1',
        'justification_patient_examples', 'justification_generic_examples',
      ],
      properties: {
        L_core_summary:                { type: 'string' },
        L_optional_summary:            { type: 'string' },
        L_irrelevant_summary:          { type: 'string' },
        R_core_formula:                { type: 'string' },
        R_core_weight:                 { type: 'number' },
        R_core_interpretation:         { type: 'string' },
        R_wrong_formula:               { type: 'string' },
        R_wrong_weight:                { type: 'number' },
        R_wrong_interpretation:        { type: 'string' },
        R_under_formula:               { type: 'string' },
        R_under_weight:                { type: 'number' },
        R_under_beta:                  { type: 'number' },
        R_under_interpretation:        { type: 'string' },
        R_over_formula:                { type: 'string' },
        R_over_weight:                 { type: 'number' },
        R_over_alpha:                  { type: 'number' },
        R_over_interpretation:         { type: 'string' },
        justification_weight:          { type: 'number' },
        justification_score_0:         { type: 'string' },
        justification_score_0_5:       { type: 'string' },
        justification_score_1:         { type: 'string' },
        justification_patient_examples:{ type: 'array', items: { type: 'string' } },
        justification_generic_examples:{ type: 'array', items: { type: 'string' } },
      },
    },
    final_reward_formula: {
      type: 'object',
      required: ['formula_string', 'max_lab_score', 'max_answer_score', 'notes'],
      properties: {
        formula_string:   { type: 'string' },
        max_lab_score:    { type: 'number' },
        max_answer_score: { type: 'number' },
        notes:            { type: 'string' },
      },
    },
  },
}

// ─── main loop ────────────────────────────────────────────────────────────────

const MAX_ROUNDS = 5
let question   = null
let evaluation = null
let round      = 0
let feedback   = ''

phase('Generate')

while (round < MAX_ROUNDS) {
  round++
  log(`Round ${round} / ${MAX_ROUNDS}: generating question ...`)

  const genPrompt = round === 1
    ? `You are writing a next-event prediction benchmark question from a real AKI (acute kidney failure) EHR patient case.

════════════════════════════════════════
MANDATORY FIRST STEP — do this BEFORE writing anything
════════════════════════════════════════
Call mcp__pubmed-server__search_articles RIGHT NOW with query:
  "KDIGO acute kidney injury renal replacement therapy indications criteria 2012"
Use the results to ground your L_core labs in specific KDIGO guideline citations.

FORBIDDEN: Do NOT use WebSearch, Bash, or Read.

════════════════════════════════════════
PATIENT — USE THESE EXACT DETAILS. DO NOT CHANGE THEM.
════════════════════════════════════════
Patient ID: ${PATIENT.patient_id}
Age:        ${PATIENT.age}
Gender:     ${PATIENT.gender}
Diagnoses:  ${PATIENT.diagnoses.join('; ')}
Prior history summary: ${JSON.stringify(PATIENT.admission_history)}

Your question stem MUST start with: "A ${PATIENT.age}-year-old ${PATIENT.gender} ..."
Do NOT change the age or gender. Do NOT invent a different patient.

════════════════════════════════════════
AVAILABLE LAB DATA (reference only — do NOT put values in the stem)
════════════════════════════════════════
${JSON.stringify(PATIENT.lab_data, null, 2)}

════════════════════════════════════════
TASK 1 — Write the question stem
════════════════════════════════════════
• Begin with "A ${PATIENT.age}-year-old ${PATIENT.gender} ..."
• Use their actual diagnoses and history from above
• Do NOT include any lab values, numeric test results, or biomarker readings
• End with: "What is the next most probable major procedural intervention for this patient?"
• The question must be impossible to answer without requesting specific labs
• The answer must be a major procedure (CRRT, RRT, dialysis, ventilation, surgery) — not a medication or IV line

════════════════════════════════════════
TASK 2 — Classify the lab sets
════════════════════════════════════════
L_core — ESSENTIAL, guideline-grounded (cite KDIGO 2012 section). At least 3 labs.
L_optional — Acceptable extras, commonly ordered alongside core labs.
L_irrelevant — Available in the EHR but irrelevant to this specific decision. At least 3 labs.
Every lab in the data above must appear in exactly one category.`

    : `You are revising a rejected benchmark question. Address ALL evaluator feedback.

FEEDBACK:
${feedback}

PREVIOUS QUESTION (rejected):
${JSON.stringify(question, null, 2)}

PATIENT (do NOT change these):
  Age: ${PATIENT.age}, Gender: ${PATIENT.gender}
  Diagnoses: ${PATIENT.diagnoses.join('; ')}

Call mcp__pubmed-server__search_articles with a refined query before rewriting.
FORBIDDEN: Do NOT use WebSearch, Bash, or Read.

LAB DATA (do NOT put values in stem):
${JSON.stringify(PATIENT.lab_data, null, 2)}

Fix every issue in the feedback. Keep "A ${PATIENT.age}-year-old ${PATIENT.gender} ..." as the opening.`

  question = await agent(genPrompt, {
    label:  `generator-round-${round}`,
    phase:  'Generate',
    schema: QUESTION_SCHEMA,
  })

  if (!question) { log(`Round ${round}: generator returned null.`); break }

  log(`Round ${round}: evaluating ...`)
  phase('Evaluate')

  evaluation = await agent(
    `You are a STRICT benchmark evaluator for AKI next-event prediction. Reject on ANY failure.

REQUIRED PATIENT:
  Age:    ${PATIENT.age}
  Gender: ${PATIENT.gender}
  Diagnoses: ${PATIENT.diagnoses.join('; ')}

QUESTION STEM:
"""
${question.question_stem}
"""
REASONING GAP: ${question.reasoning_gap}
L_core:      ${question.lab_sets.L_core.map(l => l.lab_name).join(', ')}
L_optional:  ${question.lab_sets.L_optional.map(l => l.lab_name).join(', ')}
L_irrelevant:${question.lab_sets.L_irrelevant.map(l => l.lab_name).join(', ')}

━━━ CRITERION A — Unanswerable without labs?
FAIL if: any numeric lab value in stem, OR diagnosis alone names the procedure, OR clinician has >50% chance of guessing correctly from stem alone.

━━━ CRITERION B — Next MAJOR procedure?
PASS: CRRT, RRT, dialysis, mechanical ventilation, major surgery.
FAIL: medication change, IV line, imaging order.

━━━ CRITERION C — Lab sets correctly classified?
FAIL if: any L_core lab lacks a specific KDIGO citation, any L_irrelevant is actually relevant, any L_optional belongs in L_core, fewer than 3 in L_irrelevant, or L_core has fewer than 2 labs.

━━━ CRITERION D — Correct patient demographics?
Required age: ${PATIENT.age}. Required gender: ${PATIENT.gender}.
FAIL if: stem states wrong age OR wrong gender. Quote what the stem actually says.

pass = true ONLY if ALL FOUR criteria pass.`,
    {
      label:  `evaluator-round-${round}`,
      phase:  'Evaluate',
      schema: EVAL_SCHEMA,
    }
  )

  if (!evaluation) { log(`Round ${round}: evaluator returned null.`); break }

  if (evaluation.pass) {
    log(`Question PASSED all four criteria at round ${round}.`)
    break
  }

  feedback = [
    `A: ${evaluation.criterion_a_verdict} — ${evaluation.criterion_a_feedback}`,
    `B: ${evaluation.criterion_b_verdict} — ${evaluation.criterion_b_feedback}`,
    `C: ${evaluation.criterion_c_verdict} — ${evaluation.criterion_c_feedback}`,
    `D: ${evaluation.criterion_d_verdict} — ${evaluation.criterion_d_feedback}`,
  ].join('\n')

  log(`Round ${round}: REJECTED — regenerating.`)
  phase('Generate')
}

// ─── rubric ───────────────────────────────────────────────────────────────────
phase('Rubric')
log('Generating scoring rubric ...')

const rubric = await agent(
  `Build a complete scoring rubric for this benchmark question about a real AKI patient.

Call mcp__pubmed-server__search_articles with query "${PATIENT.ground_truth} AKI indications KDIGO" before writing.
FORBIDDEN: Do NOT use WebSearch, Bash, or Read.

QUESTION: "${question.question_stem}"
GROUND TRUTH: ${PATIENT.ground_truth}
PATIENT: ${PATIENT.age}-year-old ${PATIENT.gender}, diagnoses: ${PATIENT.diagnoses.join('; ')}

LAB DATA (with actual values):
${JSON.stringify(PATIENT.lab_data, null, 2)}

APPROVED LAB SETS:
  L_core (essential): ${JSON.stringify(question.lab_sets.L_core.map(l => l.lab_name))}
  L_optional:         ${JSON.stringify(question.lab_sets.L_optional.map(l => l.lab_name))}
  L_irrelevant:       ${JSON.stringify(question.lab_sets.L_irrelevant.map(l => l.lab_name))}

WEIGHTS: w1=0.35 (R_core), w2=0.20 (R_wrong), w3=0.10 (R_under), w4=0.20 (R_over), w5=0.15 (R_justification)
PENALTY: β=${PENALTY_PARAMS.beta}, α=${PENALTY_PARAMS.alpha}, ε=${PENALTY_PARAMS.epsilon}

PART 1 — Answer rubric (4 criteria × 0.25):
  c1: exact correct procedure name + synonyms + scoring guidance + likely wrong answers
  c2: for c2_required_labs_summary write one line per lab: "LAB (VALUE) — why this value drives the decision"
  c3: full causal chain for THIS patient using their actual values; list each required step
  c4: for c4_required_patient_facts write one line per fact: "FACT — why it matters"

PART 2 — Lab scoring rubric:
  L_core/optional/irrelevant summaries: one line per lab: "LAB (VALUE) — SOURCE — reason"
  R_core, R_wrong, R_under, R_over: formula + weight + patient-specific interpretation
  R_justification (0/0.5/1): describe each score level + 2-3 patient-specific examples for score 1 + generic examples for score 0.5

PART 3 — Final formula: w1*R_core + w2*R_wrong + w3*R_under + w4*R_over + w5*R_justification + answer_score
  max_lab_score=0.70, max_answer_score=1.0`,
  {
    label:  'rubric-generator',
    phase:  'Rubric',
    schema: RUBRIC_SCHEMA,
  }
)

// ─── output ───────────────────────────────────────────────────────────────────
return {
  patient_id:        PATIENT.patient_id,
  rounds_taken:      round,
  passed_evaluation: evaluation ? evaluation.pass : false,
  question: {
    stem:          question.question_stem,
    reasoning_gap: question.reasoning_gap,
    lab_sets:      question.lab_sets,
  },
  rubric,
  ground_truth:   PATIENT.ground_truth,
  scoring_params: { weights: WEIGHTS, penalty_params: PENALTY_PARAMS },
  eval_summary: evaluation ? {
    criterion_a: evaluation.criterion_a_verdict,
    criterion_b: evaluation.criterion_b_verdict,
    criterion_c: evaluation.criterion_c_verdict,
    criterion_d: evaluation.criterion_d_verdict,
  } : null,
}
