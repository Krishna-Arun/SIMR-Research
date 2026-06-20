export const meta = {
  name: 'aki-benchmark-115973778',
  description: 'AKI next-event benchmark — patient 115973778 (23F) ground truth: Dialysis Procedure (Non-Hemodialysis), Single Eval',
  phases: [
    { title: 'Generate', detail: 'Draft question stem (no lab values) + classify L_core / L_optional / L_irrelevant' },
    { title: 'Evaluate', detail: 'Strict 4-criterion check (A/B/C/D); reject and loop up to 5x if any fails' },
    { title: 'Rubric',   detail: 'Build personalized answer rubric + full lab-set scoring rubric' },
  ],
}

// ─── patient data (embedded — no args dependency) ─────────────────────────────
const PATIENT = {
  "patient_id": "115973778",
  "age": 23,
  "gender": "Female",
  "ground_truth": "Dialysis Procedure (Non-Hemodialysis), Single Evaluation",
  "diagnoses": [
    "D57.40",
    "D62",
    "F32.9",
    "I51.7",
    "M32.14",
    "Acute kidney failure, unspecified",
    "R52",
    "R94.31"
  ],
  "admission_history": [
    {
      "admit_date": "2023-01-13",
      "discharge_date": "2023-01-13",
      "admission_type": "Inpatient",
      "diagnoses": [],
      "procedures_performed": [],
      "medications": []
    },
    {
      "admit_date": "2023-01-13",
      "discharge_date": "2023-01-13",
      "admission_type": "Inpatient",
      "diagnoses": [],
      "procedures_performed": [],
      "medications": []
    },
    {
      "admit_date": "2023-01-15",
      "discharge_date": "2023-01-15",
      "admission_type": "Inpatient",
      "diagnoses": [],
      "procedures_performed": [],
      "medications": []
    },
    {
      "admit_date": "2023-01-18",
      "discharge_date": "2023-01-18",
      "admission_type": "Inpatient",
      "diagnoses": [],
      "procedures_performed": [],
      "medications": []
    },
    {
      "admit_date": "2023-02-04",
      "discharge_date": "2023-02-04",
      "admission_type": "Inpatient",
      "diagnoses": [
        "D57.439",
        "D68.61",
        "E83.19"
      ],
      "procedures_performed": [],
      "medications": []
    }
  ],
  "lab_data": [
    {
      "date": "2018-05-05",
      "label": "Anion Gap",
      "value": "16.0",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    },
    {
      "date": "2018-05-05",
      "label": "BUN",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "7.0",
      "ref_upper": "25.0"
    },
    {
      "date": "2018-05-05",
      "label": "Calcium",
      "value": "6.6",
      "flag": "low",
      "ref_lower": "8.5",
      "ref_upper": "10.5"
    },
    {
      "date": "2018-05-05",
      "label": "Chloride",
      "value": "102.0",
      "flag": null,
      "ref_lower": "98",
      "ref_upper": "107"
    },
    {
      "date": "2018-05-05",
      "label": "Creatinine",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0.5",
      "ref_upper": "1.2"
    },
    {
      "date": "2018-05-05",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "99"
    },
    {
      "date": "2018-05-05",
      "label": "Hemoglobin",
      "value": "9.0",
      "flag": "low",
      "ref_lower": "12.0",
      "ref_upper": "17.5"
    },
    {
      "date": "2018-05-05",
      "label": "INR",
      "value": "1.3",
      "flag": "abnormal",
      "ref_lower": "0.9",
      "ref_upper": "1.1"
    },
    {
      "date": "2018-05-05",
      "label": "Phosphorus",
      "value": "11.4",
      "flag": "abnormal",
      "ref_lower": "2.5",
      "ref_upper": "4.5"
    },
    {
      "date": "2018-05-05",
      "label": "Platelets",
      "value": "290.0",
      "flag": null,
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "date": "2018-05-05",
      "label": "Potassium",
      "value": "___",
      "flag": null,
      "ref_lower": "3.5",
      "ref_upper": "5.0"
    },
    {
      "date": "2018-05-05",
      "label": "Sodium",
      "value": "139.0",
      "flag": null,
      "ref_lower": "136",
      "ref_upper": "145"
    },
    {
      "date": "2018-05-06",
      "label": "ALT",
      "value": "23.0",
      "flag": null,
      "ref_lower": "7",
      "ref_upper": "56"
    },
    {
      "date": "2018-05-06",
      "label": "Albumin",
      "value": "2.0",
      "flag": "low",
      "ref_lower": "3.5",
      "ref_upper": "5.0"
    },
    {
      "date": "2018-05-06",
      "label": "Anion Gap",
      "value": "20.0",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    },
    {
      "date": "2018-05-06",
      "label": "BUN",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "7.0",
      "ref_upper": "25.0"
    },
    {
      "date": "2018-05-06",
      "label": "Calcium",
      "value": "6.2",
      "flag": "low",
      "ref_lower": "8.5",
      "ref_upper": "10.5"
    },
    {
      "date": "2018-05-06",
      "label": "Chloride",
      "value": "102.0",
      "flag": null,
      "ref_lower": "98",
      "ref_upper": "107"
    },
    {
      "date": "2018-05-06",
      "label": "Creatinine",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0.5",
      "ref_upper": "1.2"
    },
    {
      "date": "2018-05-06",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "99"
    },
    {
      "date": "2018-05-06",
      "label": "Hemoglobin",
      "value": "7.9",
      "flag": "low",
      "ref_lower": "12.0",
      "ref_upper": "17.5"
    },
    {
      "date": "2018-05-06",
      "label": "INR",
      "value": "1.4",
      "flag": "abnormal",
      "ref_lower": "0.9",
      "ref_upper": "1.1"
    },
    {
      "date": "2018-05-06",
      "label": "Phosphorus",
      "value": "11.1",
      "flag": "abnormal",
      "ref_lower": "2.5",
      "ref_upper": "4.5"
    },
    {
      "date": "2018-05-06",
      "label": "Platelets",
      "value": "273.0",
      "flag": null,
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "date": "2018-05-06",
      "label": "Potassium",
      "value": "___",
      "flag": null,
      "ref_lower": "3.5",
      "ref_upper": "5.0"
    },
    {
      "date": "2018-05-06",
      "label": "Sodium",
      "value": "142.0",
      "flag": null,
      "ref_lower": "136",
      "ref_upper": "145"
    },
    {
      "date": "2018-05-07",
      "label": "Anion Gap",
      "value": "16.0",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    },
    {
      "date": "2018-05-07",
      "label": "BUN",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "7.0",
      "ref_upper": "25.0"
    },
    {
      "date": "2018-05-07",
      "label": "Calcium",
      "value": "6.0",
      "flag": "low",
      "ref_lower": "8.5",
      "ref_upper": "10.5"
    },
    {
      "date": "2018-05-07",
      "label": "Chloride",
      "value": "103.0",
      "flag": null,
      "ref_lower": "98",
      "ref_upper": "107"
    },
    {
      "date": "2018-05-07",
      "label": "Creatinine",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0.5",
      "ref_upper": "1.2"
    },
    {
      "date": "2018-05-07",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "99"
    },
    {
      "date": "2018-05-07",
      "label": "Hemoglobin",
      "value": "8.2",
      "flag": "low",
      "ref_lower": "12.0",
      "ref_upper": "17.5"
    },
    {
      "date": "2018-05-07",
      "label": "Phosphorus",
      "value": "10.0",
      "flag": "abnormal",
      "ref_lower": "2.5",
      "ref_upper": "4.5"
    },
    {
      "date": "2018-05-07",
      "label": "Platelets",
      "value": "289.0",
      "flag": null,
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "date": "2018-05-07",
      "label": "Potassium",
      "value": "___",
      "flag": null,
      "ref_lower": "3.5",
      "ref_upper": "5.0"
    },
    {
      "date": "2018-05-07",
      "label": "Sodium",
      "value": "140.0",
      "flag": null,
      "ref_lower": "136",
      "ref_upper": "145"
    },
    {
      "date": "2018-05-08",
      "label": "Anion Gap",
      "value": "17.0",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    },
    {
      "date": "2018-05-08",
      "label": "BUN",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "7.0",
      "ref_upper": "25.0"
    },
    {
      "date": "2018-05-08",
      "label": "Calcium",
      "value": "6.5",
      "flag": "low",
      "ref_lower": "8.5",
      "ref_upper": "10.5"
    },
    {
      "date": "2018-05-08",
      "label": "Chloride",
      "value": "101.0",
      "flag": null,
      "ref_lower": "98",
      "ref_upper": "107"
    },
    {
      "date": "2018-05-08",
      "label": "Creatinine",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0.5",
      "ref_upper": "1.2"
    },
    {
      "date": "2018-05-08",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "99"
    },
    {
      "date": "2018-05-08",
      "label": "Hemoglobin",
      "value": "9.2",
      "flag": "low",
      "ref_lower": "12.0",
      "ref_upper": "17.5"
    },
    {
      "date": "2018-05-08",
      "label": "Phosphorus",
      "value": "9.9",
      "flag": "abnormal",
      "ref_lower": "2.5",
      "ref_upper": "4.5"
    },
    {
      "date": "2018-05-08",
      "label": "Platelets",
      "value": "279.0",
      "flag": null,
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "date": "2018-05-08",
      "label": "Potassium",
      "value": "___",
      "flag": null,
      "ref_lower": "3.5",
      "ref_upper": "5.0"
    },
    {
      "date": "2018-05-08",
      "label": "Sodium",
      "value": "139.0",
      "flag": null,
      "ref_lower": "136",
      "ref_upper": "145"
    },
    {
      "date": "2018-05-09",
      "label": "Anion Gap",
      "value": "14.0",
      "flag": null,
      "ref_lower": null,
      "ref_upper": null
    },
    {
      "date": "2018-05-09",
      "label": "BUN",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "7.0",
      "ref_upper": "25.0"
    },
    {
      "date": "2018-05-09",
      "label": "Calcium",
      "value": "6.6",
      "flag": "low",
      "ref_lower": "8.5",
      "ref_upper": "10.5"
    },
    {
      "date": "2018-05-09",
      "label": "Chloride",
      "value": "103.0",
      "flag": null,
      "ref_lower": "98",
      "ref_upper": "107"
    },
    {
      "date": "2018-05-09",
      "label": "Creatinine",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "0.5",
      "ref_upper": "1.2"
    },
    {
      "date": "2018-05-09",
      "label": "Glucose",
      "value": "___",
      "flag": "abnormal",
      "ref_lower": "70",
      "ref_upper": "99"
    },
    {
      "date": "2018-05-09",
      "label": "Hemoglobin",
      "value": "8.4",
      "flag": "low",
      "ref_lower": "12.0",
      "ref_upper": "17.5"
    },
    {
      "date": "2018-05-09",
      "label": "Phosphorus",
      "value": "8.7",
      "flag": "abnormal",
      "ref_lower": "2.5",
      "ref_upper": "4.5"
    },
    {
      "date": "2018-05-09",
      "label": "Platelets",
      "value": "292.0",
      "flag": null,
      "ref_lower": "150",
      "ref_upper": "400"
    },
    {
      "date": "2018-05-09",
      "label": "Potassium",
      "value": "___",
      "flag": null,
      "ref_lower": "3.5",
      "ref_upper": "5.0"
    },
    {
      "date": "2018-05-09",
      "label": "Sodium",
      "value": "139.0",
      "flag": null,
      "ref_lower": "136",
      "ref_upper": "145"
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
