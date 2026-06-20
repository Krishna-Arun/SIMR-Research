export const meta = {
  name: 'test-schemas',
  description: 'Test: verify QUESTION_SCHEMA, EVAL_SCHEMA (4 criteria), and RUBRIC_SCHEMA all validate without retry loops',
  phases: [
    { title: 'Question', detail: 'Agent produces QUESTION_SCHEMA output' },
    { title: 'Eval',     detail: 'Agent produces EVAL_SCHEMA output (4 criteria)' },
    { title: 'Rubric',   detail: 'Agent produces RUBRIC_SCHEMA output' },
  ],
}

// ─── QUESTION_SCHEMA ──────────────────────────────────────────────────────────
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
    question_stem:  { type: 'string' },
    reasoning_gap:  { type: 'string' },
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

// ─── EVAL_SCHEMA (4 criteria) ─────────────────────────────────────────────────
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

// ─── RUBRIC_SCHEMA (flattened — no nested arrays of objects) ──────────────────
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
        c2_required_labs_summary:  { type: 'string' },
        c2_scoring_guidance:       { type: 'string' },
        c2_insufficient_examples:  { type: 'array', items: { type: 'string' } },
        c3_causal_chain:           { type: 'string' },
        c3_required_steps:         { type: 'array', items: { type: 'string' } },
        c3_scoring_guidance:       { type: 'string' },
        c3_broken_chain_examples:  { type: 'array', items: { type: 'string' } },
        c4_required_patient_facts: { type: 'string' },
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

// ─── run all three schema tests in parallel ───────────────────────────────────
phase('Question')
const [qResult, evalResult, rubricResult] = await parallel([

  () => agent(
    `Produce a minimal benchmark question for a 46-year-old Female patient with AKI and CRRT as the ground truth.
Keep everything very short — just enough to fill each required field.
question_stem: One sentence describing the patient without lab values.
reasoning_gap: One sentence about what labs are missing.
lab_sets:
  L_core: exactly 2 labs (Creatinine, Potassium) with one-line rationales
  L_optional: exactly 1 lab (BUN) with one-line rationale
  L_irrelevant: exactly 1 lab (TSH) with one-line why_irrelevant`,
    { label: 'question-schema-test', phase: 'Question', schema: QUESTION_SCHEMA }
  ),

  () => agent(
    `Evaluate this benchmark question using all four criteria.

REQUIRED PATIENT: age=46, gender=Female

QUESTION STEM:
"A 70-year-old male with ESRD on dialysis presents with septic shock. What is the next procedure?"

L_core: Creatinine, Potassium
L_optional: BUN
L_irrelevant: TSH

Criterion A: Does the question require labs to answer? (This question has dialysis-dependent ESRD so the answer is obvious — FAIL A)
Criterion B: Is the procedure major? (Yes — PASS B)
Criterion C: Are lab sets classified correctly? (Creatinine has no guideline citation — FAIL C)
Criterion D: Does the question use correct patient demographics? (Says 70-year-old male, required is 46 Female — FAIL D)

Set pass=false since multiple criteria fail.`,
    { label: 'eval-schema-test', phase: 'Eval', schema: EVAL_SCHEMA }
  ),

  () => agent(
    `Build a minimal scoring rubric for a 46-year-old Female AKI patient whose ground truth procedure is CRRT.
Keep each field very short — one or two sentences max. Just enough to fill every required field.

answer_rubric:
  c1_exact_answer: "Continuous Renal Replacement Therapy (CRRT)"
  c1_accepted_synonyms: ["CRRT", "continuous dialysis"]
  c1_scoring_guidance: "Full credit for CRRT or synonym; zero for hemodialysis or peritoneal dialysis."
  c1_wrong_answers: ["Intermittent hemodialysis", "Peritoneal dialysis"]
  c2_required_labs_summary: "Creatinine (2.2) — AKI staging.\nPotassium (abnormal) — hyperkalemia RRT trigger."
  c2_scoring_guidance: "Full credit if both labs cited with values and rationale."
  c2_insufficient_examples: ["Patient needs dialysis."]
  c3_causal_chain: "AKI with tubular necrosis → rising creatinine → KDIGO Stage 2+ → CRRT initiated."
  c3_required_steps: ["AKI staging", "Electrolyte assessment", "CRRT indication confirmed"]
  c3_scoring_guidance: "All steps must be present."
  c3_broken_chain_examples: ["Creatinine elevated therefore CRRT without staging."]
  c4_required_patient_facts: "46-year-old Female — demographics.\nAKI with tubular necrosis — primary diagnosis."
  c4_scoring_guidance: "Must reference correct age, gender, and AKI diagnosis."
  c4_critical_errors: ["States patient is male", "States patient is elderly"]

lab_scoring_rubric:
  L_core_summary: "Creatinine (2.2) — KDIGO 2012 Ch2 — AKI staging\nPotassium (abnormal) — KDIGO 2012 Ch5 Rec 5.3 — hyperkalemia RRT trigger"
  L_optional_summary: "BUN (45) — azotemia severity"
  L_irrelevant_summary: "TSH — thyroid function, unrelated to RRT"
  R_core_formula: "R_core = |Lp ∩ Lcore| / |Lcore|"
  R_core_weight: 0.35
  R_core_interpretation: "R_core=1.0 means both core labs requested. R_core=0.5 means one missed."
  R_wrong_formula: "R_wrong = 1 - |Lp - (Lcore ∪ Lopt)| / (|Lp| + epsilon)"
  R_wrong_weight: 0.20
  R_wrong_interpretation: "Requesting TSH costs R_wrong penalty."
  R_under_formula: "R_under = -beta * (|Lcore| - |Lp ∩ Lcore|)"
  R_under_weight: 0.10
  R_under_beta: 2.0
  R_under_interpretation: "Missing Potassium is most egregious omission — hyperkalemia is time-critical."
  R_over_formula: "R_over = -alpha * max(0, |Lp| - |Lcore| - |Lopt|)"
  R_over_weight: 0.20
  R_over_alpha: 0.5
  R_over_interpretation: "Requesting more than 3 total labs triggers penalty."
  justification_weight: 0.15
  justification_score_0: "No justification given."
  justification_score_0_5: "Generic: creatinine elevated in AKI."
  justification_score_1: "Patient-specific: 46F with creatinine 2.2 above baseline, rising — KDIGO Stage 2 AKI."
  justification_patient_examples: ["This 46-year-old female has creatinine 2.2, consistent with KDIGO Stage 2 AKI requiring CRRT evaluation."]
  justification_generic_examples: ["Creatinine is elevated in AKI and should be monitored."]

final_reward_formula:
  formula_string: "w1*R_core + w2*R_wrong + w3*R_under + w4*R_over + w5*R_justification + answer_score"
  max_lab_score: 0.70
  max_answer_score: 1.0
  notes: "R_under penalty is heaviest per missed lab (beta=2.0)."`,
    { label: 'rubric-schema-test', phase: 'Rubric', schema: RUBRIC_SCHEMA }
  ),

])

// ─── verify results ───────────────────────────────────────────────────────────
const qOk = qResult && qResult.question_stem && qResult.lab_sets && qResult.lab_sets.L_core.length >= 2
const evalOk = evalResult && evalResult.criterion_d_verdict === 'FAIL' && evalResult.pass === false
const rubricOk = rubricResult && rubricResult.answer_rubric && rubricResult.lab_scoring_rubric && rubricResult.final_reward_formula

log(`QUESTION_SCHEMA:  ${qOk ? 'PASS' : 'FAIL'}`)
log(`EVAL_SCHEMA (D):  ${evalOk ? 'PASS — criterion D correctly fired' : 'FAIL — criterion D did not fire or schema broken'}`)
log(`RUBRIC_SCHEMA:    ${rubricOk ? 'PASS' : 'FAIL'}`)

return {
  question_schema_ok: qOk,
  eval_schema_ok:     evalOk,
  rubric_schema_ok:   rubricOk,
  question_sample:    qResult ? qResult.question_stem : null,
  eval_criterion_d:   evalResult ? evalResult.criterion_d_verdict : null,
  rubric_c1_answer:   rubricResult ? rubricResult.answer_rubric.c1_exact_answer : null,
  all_pass:           qOk && evalOk && rubricOk,
}
