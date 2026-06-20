export const meta = {
  name: 'aki-benchmark-10015860',
  description: 'AKI next-event benchmark — patient 10015860 (53M) ground truth: Performance of Urinary Filtration, Intermittent, L',
  phases: [
    { title: 'Generate', detail: 'Draft question stem (no lab values) + classify L_core / L_optional / L_irrelevant' },
    { title: 'Evaluate', detail: 'Strict 4-criterion check (A/B/C/D); reject and loop up to 5x if any fails' },
    { title: 'Rubric',   detail: 'Build personalized answer rubric + full lab-set scoring rubric' },
  ],
}

// ─── patient data (embedded — no args dependency) ─────────────────────────────
const PATIENT = {
  "patient_id": "10015860",
  "age": 53,
  "gender": "Male",
  "ground_truth": "Performance of Urinary Filtration, Intermittent, Less than 6 Hours Per Day",
  "diagnoses": [
    "Sepsis, unspecified organism",
    "End stage renal disease",
    "Necrotizing fasciitis",
    "Acidosis",
    "Hypertensive chronic kidney disease with stage 5 chronic kidney disease or end stage renal disease",
    "Type 2 diabetes mellitus with diabetic peripheral angiopathy with gangrene",
    "Other acute osteomyelitis, right ankle and foot",
    "Hypo-osmolality and hyponatremia"
  ],
  "admission_history": [
    {
      "admit_date": "2186-09-15",
      "discharge_date": "2186-09-29",
      "admission_type": "EW EMER.",
      "discharge_location": "REHAB",
      "diagnoses": [
        "Streptococcal septicemia",
        "Diabetes with ketoacidosis, type II or unspecified type, uncontrolled",
        "Cellulitis and abscess of foot, except toes",
        "Cellulitis and abscess of leg, except foot",
        "Hyposmolality and/or hyponatremia",
        "Ulcer of other part of foot",
        "Diabetes with neurological manifestations, type II or unspecified type, uncontrolled",
        "Sepsis"
      ],
      "procedures_performed": [
        "Other incision with drainage of skin and subcutaneous tissue",
        "Other incision with drainage of skin and subcutaneous tissue",
        "Other incision with drainage of skin and subcutaneous tissue",
        "Other skin graft to other sites",
        "Other fasciectomy",
        "Central venous catheter placement with guidance"
      ],
      "medications": [
        "0.45% Sodium Chloride",
        "0.9% Sodium Chloride",
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "5% Dextrose",
        "Acetaminophen",
        "Bag",
        "Bisacodyl",
        "Calcium Carbonate",
        "Calcium Gluconate",
        "CefePIME",
        "CeftriaXONE",
        "Ciprofloxacin HCl"
      ]
    },
    {
      "admit_date": "2187-09-15",
      "discharge_date": "2187-09-19",
      "admission_type": "EW EMER.",
      "discharge_location": "HOME HEALTH CARE",
      "diagnoses": [
        "Ulcer of other part of foot",
        "Cellulitis and abscess of foot, except toes",
        "Diabetes mellitus without mention of complication, type II or unspecified type, not stated as uncontrolled",
        "Unspecified essential hypertension",
        "Pure hypercholesterolemia",
        "Personal history of tobacco use"
      ],
      "procedures_performed": [
        "Excisional debridement of wound, infection, or burn"
      ],
      "medications": [
        "Aspirin",
        "Atenolol",
        "Ciprofloxacin HCl",
        "Dextrose 50%",
        "Docusate Sodium",
        "Glucagon",
        "Glucose Gel",
        "GlyBURIDE",
        "Heparin",
        "Influenza Virus Vaccine",
        "Insulin",
        "Iso-Osmotic Dextrose"
      ]
    },
    {
      "admit_date": "2187-12-14",
      "discharge_date": "2187-12-16",
      "admission_type": "EU OBSERVATION",
      "discharge_location": "",
      "diagnoses": [
        "Cellulitis and abscess of foot, except toes",
        "Ulcer of other part of foot",
        "Hyposmolality and/or hyponatremia",
        "Hypertensive chronic kidney disease, unspecified, with chronic kidney disease stage I through stage IV, or unspecified",
        "Chronic kidney disease, unspecified",
        "Diabetes with neurological manifestations, type II or unspecified type, uncontrolled",
        "Polyneuropathy in diabetes",
        "Pure hypercholesterolemia"
      ],
      "procedures_performed": [],
      "medications": [
        "Acetaminophen",
        "Aspirin",
        "Atenolol",
        "Dextrose 50%",
        "Docusate Sodium",
        "Doxycycline Hyclate",
        "Glucagon",
        "Glucose Gel",
        "Heparin",
        "Insulin",
        "Iso-Osmotic Dextrose",
        "Lisinopril"
      ]
    },
    {
      "admit_date": "2188-03-29",
      "discharge_date": "2188-04-02",
      "admission_type": "DIRECT EMER.",
      "discharge_location": "HOME HEALTH CARE",
      "diagnoses": [
        "Diabetes with other specified manifestations, type II or unspecified type, not stated as uncontrolled",
        "Ulcer of other part of foot",
        "Unspecified osteomyelitis, ankle and foot",
        "Diabetes with neurological manifestations, type II or unspecified type, not stated as uncontrolled",
        "Long-term (current) use of insulin",
        "Other bone involvement in diseases classified elsewhere",
        "Unspecified essential hypertension",
        "Esophageal reflux"
      ],
      "procedures_performed": [
        "Other partial ostectomy, tarsals and metatarsals"
      ],
      "medications": [
        "5% Dextrose",
        "Acetaminophen",
        "Atenolol",
        "Bisacodyl",
        "Ciprofloxacin HCl",
        "Dextrose 50%",
        "DiphenhydrAMINE",
        "Docusate Sodium",
        "Glucagon",
        "Glucose Gel",
        "Heparin",
        "Insulin"
      ]
    },
    {
      "admit_date": "2188-08-06",
      "discharge_date": "2188-08-12",
      "admission_type": "EW EMER.",
      "discharge_location": "HOME HEALTH CARE",
      "diagnoses": [
        "Diabetes with other specified manifestations, type II or unspecified type, uncontrolled",
        "Streptococcal septicemia",
        "Sepsis",
        "Diabetes with neurological manifestations, type II or unspecified type, uncontrolled",
        "Ulcer of other part of foot",
        "Unspecified osteomyelitis, ankle and foot",
        "Other bone involvement in diseases classified elsewhere",
        "Acute kidney failure, unspecified"
      ],
      "procedures_performed": [
        "Other incision with drainage of skin and subcutaneous tissue",
        "Local excision of lesion or tissue of bone, other bones",
        "Local excision of lesion or tissue of bone, other bones",
        "Venous catheterization, not elsewhere classified"
      ],
      "medications": [
        "*NF* Ertapenem Sodium",
        "0.9% Sodium Chloride",
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "5% Dextrose",
        "Acetaminophen",
        "Amlodipine",
        "Aspirin",
        "Atorvastatin",
        "CefePIME",
        "Ciprofloxacin HCl",
        "Dextrose 50%",
        "Docusate Sodium"
      ]
    },
    {
      "admit_date": "2189-05-23",
      "discharge_date": "2189-05-25",
      "admission_type": "EW EMER.",
      "discharge_location": "HOME HEALTH CARE",
      "diagnoses": [
        "Unspecified septicemia",
        "Acute kidney failure, unspecified",
        "Diabetes with other specified manifestations, type II or unspecified type, uncontrolled",
        "Diabetes with neurological manifestations, type II or unspecified type, uncontrolled",
        "Chronic kidney disease, Stage III (moderate)",
        "Hyposmolality and/or hyponatremia",
        "Need for prophylactic vaccination and inoculation against influenza",
        "Ulcer of other part of foot"
      ],
      "procedures_performed": [
        "Excisional debridement of wound, infection, or burn"
      ],
      "medications": [
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "Acetaminophen",
        "Amlodipine",
        "Aquaphor Ointment",
        "Aspirin",
        "Atorvastatin",
        "CeftriaXONE",
        "Dextrose 50%",
        "Docusate Sodium",
        "Glucagon",
        "Glucose Gel",
        "Heparin"
      ]
    },
    {
      "admit_date": "2190-05-15",
      "discharge_date": "2190-05-16",
      "admission_type": "EU OBSERVATION",
      "discharge_location": "",
      "diagnoses": [
        "Type 2 diabetes mellitus with hyperglycemia",
        "Type 2 diabetes mellitus with diabetic nephropathy",
        "Type 2 diabetes mellitus with foot ulcer",
        "Non-pressure chronic ulcer of other part of right foot with unspecified severity",
        "Type 2 diabetes mellitus with diabetic neuropathy, unspecified",
        "Long term (current) use of insulin",
        "Acute kidney failure, unspecified",
        "Hypertensive chronic kidney disease with stage 1 through stage 4 chronic kidney disease, or unspecified chronic kidney disease"
      ],
      "procedures_performed": [],
      "medications": [
        "Acetaminophen",
        "Amlodipine",
        "Aspirin",
        "Atorvastatin",
        "Dextrose 50%",
        "Glucagon",
        "Glucose Gel",
        "Heparin",
        "Influenza Vaccine Quadrivalent",
        "Insulin",
        "Levofloxacin",
        "Lisinopril"
      ]
    },
    {
      "admit_date": "2191-01-15",
      "discharge_date": "2191-01-30",
      "admission_type": "OBSERVATION ADMIT",
      "discharge_location": "SKILLED NURSING FACILITY",
      "diagnoses": [
        "Other streptococcal sepsis",
        "Severe sepsis without septic shock",
        "Acidosis",
        "Acute kidney failure, unspecified",
        "Chronic kidney disease, stage 3 (moderate)",
        "Type 2 diabetes mellitus with diabetic chronic kidney disease",
        "Tinea cruris",
        "Hypo-osmolality and hyponatremia"
      ],
      "procedures_performed": [
        "Drainage of Right Hip Joint, Percutaneous Approach, Diagnostic"
      ],
      "medications": [
        "0.9% Sodium Chloride (Mini Bag Plus)",
        "5% Dextrose",
        "ALPRAZolam",
        "Acetaminophen",
        "Acetaminophen IV",
        "Aluminum-Magnesium Hydrox.-Simethicone",
        "Aspirin",
        "Atorvastatin",
        "Bag",
        "CefTRIAXone",
        "Cepacol (Sore Throat Lozenge)",
        "Ciprofloxacin IV"
      ]
    }
  ],
  "lab_data": [
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Creatinine",
      "value": "8.8",
      "flag": "abnormal",
      "ref_lower": "0.5",
      "ref_upper": "1.2"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "BUN",
      "value": "83",
      "flag": "abnormal",
      "ref_lower": "6",
      "ref_upper": "20"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Sodium",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "135",
      "ref_upper": "147"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Bicarbonate",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "22",
      "ref_upper": "32"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Anion Gap",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "10",
      "ref_upper": "18"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Phosphate",
      "value": "4.9",
      "flag": "abnormal",
      "ref_lower": "2.7",
      "ref_upper": "4.5"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Magnesium",
      "value": "1.4",
      "flag": "abnormal",
      "ref_lower": "1.6",
      "ref_upper": "2.6"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "WBC",
      "value": "26.4",
      "flag": "abnormal",
      "ref_lower": "4",
      "ref_upper": "10"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Hemoglobin",
      "value": "8.9",
      "flag": "abnormal",
      "ref_lower": "13.7",
      "ref_upper": "17.5"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Hematocrit",
      "value": "26.4",
      "flag": "abnormal",
      "ref_lower": "40",
      "ref_upper": "51"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-25",
      "label": "Platelet Count",
      "value": "413",
      "flag": "abnormal",
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "BNP",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "21",
      "ref_upper": "30"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "INR",
      "value": "1.3",
      "flag": "abnormal",
      "ref_lower": "0.9",
      "ref_upper": "1.1"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "100"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-13",
      "label": "Calcium, Total",
      "value": "8.2",
      "flag": "abnormal",
      "ref_lower": "8.4",
      "ref_upper": "10.3"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Chloride",
      "value": "90",
      "flag": "abnormal",
      "ref_lower": "96",
      "ref_upper": "108"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Prothrombin Time",
      "value": "13.7",
      "flag": "abnormal",
      "ref_lower": "9.4",
      "ref_upper": "12.5"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Neutrophils",
      "value": "1.7",
      "flag": "abnormal",
      "ref_lower": "19",
      "ref_upper": "53"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Eosinophils",
      "value": "0.0",
      "flag": "abnormal",
      "ref_lower": "1",
      "ref_upper": "7"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-15",
      "label": "C-Reactive Protein",
      "value": "149.1",
      "flag": "abnormal",
      "ref_lower": "0",
      "ref_upper": "5"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Potassium",
      "value": "___",
      "flag": null,
      "ref_lower": "3.3",
      "ref_upper": "5.1"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Urine Casts",
      "value": "6.0",
      "flag": null,
      "ref_lower": "5",
      "ref_upper": "8"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Albumin",
      "value": "3.5",
      "flag": null,
      "ref_lower": "3.5",
      "ref_upper": "5.2"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Lactate",
      "value": "1.1",
      "flag": null,
      "ref_lower": "0.5",
      "ref_upper": "2"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "PT",
      "value": "27.1",
      "flag": null,
      "ref_lower": "25",
      "ref_upper": "36.5"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "ALT",
      "value": "12",
      "flag": null,
      "ref_lower": "0",
      "ref_upper": "40"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "AST",
      "value": "11",
      "flag": null,
      "ref_lower": "0",
      "ref_upper": "40"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Uric Acid",
      "value": "64",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Lymphocytes",
      "value": "6.4",
      "flag": null,
      "ref_lower": "5",
      "ref_upper": "13"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-11",
      "label": "Lipase",
      "value": "32",
      "flag": null,
      "ref_lower": "0",
      "ref_upper": "60"
    },
    {
      "hadm_id": "24698912",
      "date": "2192-05-13",
      "label": "CK",
      "value": "___",
      "flag": null,
      "ref_lower": "47",
      "ref_upper": "322"
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

Your question stem MUST start with EXACTLY:
  "Patient subject_id: ${PATIENT.patient_id}\n\nA ${PATIENT.age}-year-old ${PATIENT.gender} ..."
Do NOT change the age, gender, or patient_id. Do NOT invent a different patient.

════════════════════════════════════════
AVAILABLE LAB DATA (reference only — do NOT put values in the stem)
════════════════════════════════════════
${JSON.stringify(PATIENT.lab_data, null, 2)}

════════════════════════════════════════
TASK 1 — Write the question stem
════════════════════════════════════════
• Begin with "Patient MIMIC subject_id: ${PATIENT.patient_id}\n\nA ${PATIENT.age}-year-old ${PATIENT.gender} ..."
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
