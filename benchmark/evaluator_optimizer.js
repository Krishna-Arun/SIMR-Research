export const meta = {
  name: 'aki-benchmark-evaluator-optimizer',
  description: 'Generate and refine next-event prediction questions from AKI EHR data with lab-set scoring rubric (R_core, R_wrong, R_under, R_over, R_justification) and 4-criterion answer score',
  phases: [
    { title: 'Generate',  detail: 'Draft question stem (no lab values) + classify L_core / L_optional / L_irrelevant' },
    { title: 'Evaluate',  detail: 'Strict dual-criterion check; reject and loop up to 5× if either fails' },
    { title: 'Rubric',    detail: 'Build personalized answer rubric + full lab-set scoring rubric with formulas' },
  ],
}

// ─── args shape ───────────────────────────────────────────────────────────────
// {
//   patient_id:           string,
//   patient_context: {
//     demographics:       { age, gender },
//     admission_history:  [ { date, type, diagnoses, discharge_location, procedures } ],
//     current_admission:  { date, type, diagnoses, medications },
//   },
//   lab_data: [ { date, label, value, flag, ref_lower, ref_upper } ],
//   ground_truth_procedure: string,
// }
// ─────────────────────────────────────────────────────────────────────────────

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
    question_stem: {
      type: 'string',
      description: 'Full question for the answering agent. ZERO numeric lab values or test results.',
    },
    reasoning_gap: {
      type: 'string',
      description: 'One sentence: the specific clinical question that cannot be resolved from the stem alone.',
    },
    lab_sets: {
      type: 'object',
      required: ['L_core', 'L_optional', 'L_irrelevant'],
      properties: {
        L_core: {
          type: 'array',
          items: LAB_ITEM_SCHEMA,
          description: 'Essential, guideline-grounded labs. Missing any one is heavily penalised.',
        },
        L_optional: {
          type: 'array',
          items: LAB_ITEM_SCHEMA,
          description: 'Acceptable extra labs — reasonable but not strictly required.',
        },
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
          description: 'Labs available in the EHR but clinically irrelevant to this decision.',
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
    pass: { type: 'boolean', description: 'True only if ALL four criteria pass.' },
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
    criterion_d_feedback: { type: 'string', description: 'Quote the exact age/gender from the stem and compare to required values.' },
  },
}

// RUBRIC_SCHEMA — FLAT. No nested arrays-of-objects. All leaf values are string / number / array-of-string.
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
        // Criterion 1 — Actual event named (0.25 pts)
        c1_exact_answer:      { type: 'string', description: 'The exact correct procedure name.' },
        c1_accepted_synonyms: { type: 'array',  items: { type: 'string' }, description: 'Conservative list of acceptable synonyms.' },
        c1_scoring_guidance:  { type: 'string', description: 'Full credit / partial / zero rules.' },
        c1_wrong_answers:     { type: 'array',  items: { type: 'string' }, description: '2-3 likely wrong answers and why they fail.' },

        // Criterion 2 — Appropriate lab use (0.25 pts)
        c2_required_labs_summary: {
          type: 'string',
          description: 'Each required lab on its own line: "LAB_NAME (ACTUAL_VALUE) — why this value drives the procedure decision." E.g. "Creatinine (8.8 mg/dL) — severely elevated, indicates uremia requiring dialysis."',
        },
        c2_scoring_guidance:       { type: 'string' },
        c2_insufficient_examples:  { type: 'array', items: { type: 'string' }, description: 'Example phrases that earn only partial credit.' },

        // Criterion 3 — Clear causal relationship (0.25 pts)
        c3_causal_chain:           { type: 'string', description: 'Full step-by-step causal chain for THIS patient using their actual values.' },
        c3_required_steps:         { type: 'array', items: { type: 'string' }, description: 'Each logical step that must appear.' },
        c3_scoring_guidance:       { type: 'string' },
        c3_broken_chain_examples:  { type: 'array', items: { type: 'string' } },

        // Criterion 4 — Patient information accurate (0.25 pts)
        c4_required_patient_facts: {
          type: 'string',
          description: 'Each key patient fact on its own line: "FACT — why it matters." E.g. "53M with ESRD and diabetic nephropathy — establishes chronic baseline for AKI severity."',
        },
        c4_scoring_guidance:  { type: 'string' },
        c4_critical_errors:   { type: 'array', items: { type: 'string' }, description: 'Errors that auto-fail criterion 4.' },
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
        L_core_summary: {
          type: 'string',
          description: 'One lab per line: "LAB_NAME (VALUE) — GUIDELINE_SOURCE — why essential."',
        },
        L_optional_summary: {
          type: 'string',
          description: 'One lab per line: "LAB_NAME (VALUE) — why acceptable extra."',
        },
        L_irrelevant_summary: {
          type: 'string',
          description: 'One lab per line: "LAB_NAME (VALUE) — why irrelevant to this decision."',
        },

        R_core_formula:         { type: 'string' },
        R_core_weight:          { type: 'number' },
        R_core_interpretation:  { type: 'string' },

        R_wrong_formula:        { type: 'string' },
        R_wrong_weight:         { type: 'number' },
        R_wrong_interpretation: { type: 'string' },

        R_under_formula:        { type: 'string' },
        R_under_weight:         { type: 'number' },
        R_under_beta:           { type: 'number' },
        R_under_interpretation: { type: 'string' },

        R_over_formula:         { type: 'string' },
        R_over_weight:          { type: 'number' },
        R_over_alpha:           { type: 'number' },
        R_over_interpretation:  { type: 'string' },

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

// ─── pre-extract patient fields (safe, no chained access in template literals) ─
const _ctx    = args && args.patient_context
const _age    = _ctx && _ctx.demographics ? _ctx.demographics.age    : 'unknown'
const _gender = _ctx && _ctx.demographics ? _ctx.demographics.gender : 'unknown'
const _adm    = _ctx && _ctx.current_admission ? _ctx.current_admission.admission_type : 'unknown'
const _diags  = _ctx && _ctx.current_admission && Array.isArray(_ctx.current_admission.diagnoses)
  ? _ctx.current_admission.diagnoses.join('; ')
  : 'unknown'

// ─── main loop ────────────────────────────────────────────────────────────────

const MAX_ROUNDS = 5
let question   = null
let evaluation = null
let round      = 0
let feedback   = ''

phase('Generate')

while (round < MAX_ROUNDS) {
  round++
  log(`Round ${round} / ${MAX_ROUNDS}: generating question + lab sets ...`)

  const gen_prompt = round === 1
    ? `You are writing a next-event prediction benchmark question from a real AKI (acute kidney failure) EHR patient case.

════════════════════════════════════════
MANDATORY FIRST STEPS — do these BEFORE writing anything else
════════════════════════════════════════

STEP 1: Call mcp__kidney-guidelines-rag__search_kidney_guidelines NOW.
  Use query: "AKI renal replacement therapy indications criteria KDIGO"
  This is REQUIRED. Do not skip it.

STEP 2: Call mcp__pubmed-server__search_articles NOW.
  Use query: "KDIGO acute kidney injury renal replacement therapy initiation criteria"
  This is REQUIRED. Do not skip it.

Use the results to ground your L_core labs in specific guideline citations.

FORBIDDEN: Do NOT use WebSearch, Bash, Read, or any tool except the two MCP tools above.

════════════════════════════════════════
CRITICAL — USE THIS EXACT PATIENT. DO NOT INVENT A DIFFERENT PATIENT.
════════════════════════════════════════
Patient ID: ${args.patient_id}
Age: ${_age}
Gender: ${_gender}
Current Admission Type: ${_adm}
Current Diagnoses: ${_diags}

The question stem MUST describe THIS specific patient with these exact demographics and diagnoses.
Do NOT change the age, gender, or primary diagnoses. Do NOT substitute a different clinical scenario.

════════════════════════════════════════
FULL PATIENT DATA (no lab values — do NOT invent any)
════════════════════════════════════════
${JSON.stringify(args.patient_context, null, 2)}

════════════════════════════════════════
AVAILABLE LAB DATA (reference only — do NOT put values in the question stem)
════════════════════════════════════════
${JSON.stringify(args.lab_data, null, 2)}

════════════════════════════════════════
TASK 1 — Write the question stem
════════════════════════════════════════
YOUR QUESTION STEM MUST BEGIN WITH EXACTLY THIS OPENING (fill in the brackets from patient data):
  "A ${_age}-year-old ${_gender} with [relevant prior history from admission_history] presents to [admission_location] with [current ICD-coded diagnoses]. [Describe current clinical status from current_admission]. What is the next most probable major procedural intervention for this patient?"

Rules:
• The age MUST be ${_age}. The gender MUST be ${_gender}. Do NOT change either.
• The diagnoses MUST come from the patient_context current_admission.diagnoses list above.
• STRICT: Do NOT include any lab values, numeric test results, or biomarker readings in the stem.
• The question MUST be impossible to answer correctly without requesting specific labs.
• The answer must be a major procedure (RRT/dialysis/CRRT, ventilation, surgery, organ-level intervention) — NOT a medication adjustment or IV access alone.
• Create a clear reasoning gap where labs are the essential missing piece.

════════════════════════════════════════
TASK 2 — Classify the lab sets
════════════════════════════════════════
Classify every available lab into exactly one of three categories:

L_core — ESSENTIAL. Must be grounded directly in KDIGO or other AKI guidelines you found.
  For each: cite the specific guideline and why it is non-negotiable for this AKI decision.
  Include at least 3 labs here.

L_optional — ACCEPTABLE EXTRAS. Commonly ordered alongside core labs.
  Clinically reasonable but not strictly required.

L_irrelevant — AVAILABLE BUT IRRELEVANT. Present in the EHR but have no bearing on
  the specific procedure decision for this patient.
  Include at least 3 irrelevant labs.

Every lab in the available lab data must be assigned to exactly one category.`

    : `You are revising a benchmark question after REJECTION by the strict evaluator.

EVALUATOR FEEDBACK (address EVERY issue):
${feedback}

PREVIOUS QUESTION (rejected):
${JSON.stringify(question, null, 2)}

════════════════════════════════════════
MANDATORY FIRST STEPS — do these BEFORE writing anything
════════════════════════════════════════

STEP 1: Call mcp__kidney-guidelines-rag__search_kidney_guidelines NOW.
  Refine your query based on the evaluator feedback.

STEP 2: Call mcp__pubmed-server__search_articles NOW.
  Use a refined query based on the feedback.

FORBIDDEN: Do NOT use WebSearch, Bash, Read, or any tool except the two MCP tools above.

════════════════════════════════════════
CRITICAL — USE THIS EXACT PATIENT. DO NOT INVENT A DIFFERENT PATIENT.
════════════════════════════════════════
Patient ID: ${args.patient_id}
Age: ${_age}
Gender: ${_gender}
Current Diagnoses: ${_diags}

Keep these exact demographics and diagnoses in your revised question stem.

════════════════════════════════════════
FULL PATIENT DATA (no lab values)
════════════════════════════════════════
${JSON.stringify(args.patient_context, null, 2)}

AVAILABLE LAB DATA (classification reference only — do NOT put values in stem):
${JSON.stringify(args.lab_data, null, 2)}

Fix every issue the evaluator identified. Regenerate both the question stem AND the lab set classification.`

  question = await agent(gen_prompt, {
    label:  `generator-round-${round}`,
    phase:  'Generate',
    schema: QUESTION_SCHEMA,
  })

  if (!question) {
    log(`Round ${round}: generator returned null — stopping.`)
    break
  }

  log(`Round ${round}: evaluating ...`)
  phase('Evaluate')

  evaluation = await agent(
    `You are a STRICT benchmark quality evaluator for AKI (acute kidney failure) next-event prediction. Reject on ANY failure. When in doubt, FAIL.

REQUIRED PATIENT DEMOGRAPHICS (from the real EHR record):
  Age:    ${_age}
  Gender: ${_gender}
  Primary diagnoses: ${_diags}

QUESTION STEM:
"""
${question.question_stem}
"""

REASONING GAP (stated by generator): ${question.reasoning_gap}

L_core LABS PROPOSED: ${question.lab_sets.L_core.map(l => l.lab_name).join(', ')}
L_optional LABS PROPOSED: ${question.lab_sets.L_optional.map(l => l.lab_name).join(', ')}
L_irrelevant LABS PROPOSED: ${question.lab_sets.L_irrelevant.map(l => l.lab_name).join(', ')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERION A — Is the question unanswerable without lab values?

Fail triggers (any one = FAIL):
• Any numeric lab value or biomarker reading appears in the stem
• The diagnosis in the stem alone is sufficient to name the procedure
• A clinician has >50% chance of guessing the correct answer from the stem alone
• The stem is so specific that labs add no new information

Be maximally strict. If the diagnosis is clear-cut (e.g., "dialysis-dependent ESRD" → dialysis), FAIL it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERION B — Does the question target the next MAJOR treatment or procedure?

MAJOR (pass): CRRT, RRT, dialysis, mechanical ventilation, surgical intervention, organ-level procedures.
NOT MAJOR (fail): IV line placement, medication titration alone, routine imaging, monitoring escalation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERION C — Are the lab sets properly classified?

Fail triggers:
• Any L_core lab lacks a specific guideline citation (e.g., "KDIGO AKI 2012 Chapter 5")
• Any L_irrelevant lab is actually clinically relevant to this specific procedure decision
• Any L_optional lab clearly belongs in L_core (is actually guideline-mandated)
• Fewer than 3 labs in L_irrelevant
• L_core is empty or has fewer than 2 labs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERION D — Does the question describe the CORRECT patient?

Required: age = ${_age}, gender = ${_gender}.
Fail triggers (any one = FAIL):
• The stem states a different age (e.g., "60s", "70-year-old", "elderly male" when patient is ${_age}F)
• The stem states the wrong gender (e.g., "he/his/male" when patient is ${_gender})
• The primary diagnoses in the stem are completely different from the real patient's diagnoses

Quote the age and gender phrase from the stem in your feedback.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
pass = true ONLY if ALL FOUR criteria pass.`,
    {
      label:  `evaluator-round-${round}`,
      phase:  'Evaluate',
      schema: EVAL_SCHEMA,
    }
  )

  if (!evaluation) {
    log(`Round ${round}: evaluator returned null — stopping.`)
    break
  }

  if (evaluation.pass) {
    log(`Question PASSED all three criteria at round ${round}.`)
    break
  }

  feedback = [
    `Criterion A (labs required): ${evaluation.criterion_a_verdict} — ${evaluation.criterion_a_feedback}`,
    `Criterion B (major treatment): ${evaluation.criterion_b_verdict} — ${evaluation.criterion_b_feedback}`,
    `Criterion C (lab set classification): ${evaluation.criterion_c_verdict} — ${evaluation.criterion_c_feedback}`,
    `Criterion D (correct patient): ${evaluation.criterion_d_verdict} — ${evaluation.criterion_d_feedback}`,
  ].join('\n')

  log(`Round ${round}: REJECTED — regenerating with feedback.`)
  phase('Generate')
}

// ─── rubric generation ────────────────────────────────────────────────────────

phase('Rubric')
log('Generating scoring rubric ...')

const rubric = await agent(
  `You are building a complete scoring rubric for a benchmark question grounded in real AKI patient EHR data.

════════════════════════════════════════
MANDATORY FIRST STEPS — do these BEFORE writing anything
════════════════════════════════════════

STEP 1: Call mcp__kidney-guidelines-rag__search_kidney_guidelines NOW.
  Query: "renal replacement therapy indications AKI KDIGO criteria"
  This is REQUIRED. Do not skip it.

STEP 2: Call mcp__pubmed-server__search_articles NOW.
  Query relevant to: ${args.ground_truth_procedure}
  This is REQUIRED. Do not skip it.

FORBIDDEN: Do NOT use WebSearch, Bash, Read, or any tool except the two MCP tools above.

════════════════════════════════════════
INPUT
════════════════════════════════════════

QUESTION (approved after ${round} rounds):
"""
${question.question_stem}
"""

GROUND TRUTH NEXT PROCEDURE: ${args.ground_truth_procedure}

ACTUAL LAB DATA FOR THIS PATIENT:
${JSON.stringify(args.lab_data, null, 2)}

PATIENT CONTEXT:
${JSON.stringify(args.patient_context, null, 2)}

APPROVED LAB SETS:
  L_core (essential, guideline-grounded): ${JSON.stringify(question.lab_sets.L_core.map(l=>l.lab_name))}
  L_optional (acceptable extras):         ${JSON.stringify(question.lab_sets.L_optional.map(l=>l.lab_name))}
  L_irrelevant (should NOT be requested): ${JSON.stringify(question.lab_sets.L_irrelevant.map(l=>l.lab_name))}

SCORING PARAMETERS:
  Weights: w1=0.35 (R_core), w2=0.20 (R_wrong), w3=0.10 (R_under), w4=0.20 (R_over), w5=0.15 (R_justification)
  Penalty params: β=${PENALTY_PARAMS.beta}, α=${PENALTY_PARAMS.alpha}, ε=${PENALTY_PARAMS.epsilon}

════════════════════════════════════════
PART 1 — Answer Rubric (4 criteria × 0.25 = 1.0 max)
════════════════════════════════════════

c1 — Actual event named (0.25 pts)
  c1_exact_answer: exact correct procedure name
  c1_accepted_synonyms: 2-4 acceptable synonyms (conservative)
  c1_scoring_guidance: full credit / partial / zero rules
  c1_wrong_answers: 2-3 likely wrong answers and why they fail

c2 — Appropriate use of labs (0.25 pts)
  c2_required_labs_summary: each required lab on its own line as:
    "LAB_NAME (ACTUAL_VALUE) — why this specific value drives the procedure decision for THIS patient."
  c2_scoring_guidance: partial credit rules
  c2_insufficient_examples: 2-3 example phrases that earn only partial credit

c3 — Clear causal relationship for THIS patient (0.25 pts)
  c3_causal_chain: full step-by-step causal chain using this patient's actual lab values and history
  c3_required_steps: each logical step that must appear (list separately)
  c3_scoring_guidance: scoring rules
  c3_broken_chain_examples: 2-3 examples of broken or reversed chains

c4 — Patient information accurate (0.25 pts)
  c4_required_patient_facts: each key fact on its own line as:
    "FACT — why it matters (wrong = hallucination or patient confusion)."
  c4_scoring_guidance: scoring rules
  c4_critical_errors: errors that auto-fail criterion 4

════════════════════════════════════════
PART 2 — Lab Scoring Rubric
════════════════════════════════════════

L_core_summary: one lab per line: "LAB_NAME (VALUE) — GUIDELINE_SOURCE — why essential"
  Include specific guideline (e.g. "KDIGO AKI 2012 Section 5.3 — hyperkalemia RRT indication")
L_optional_summary: one lab per line: "LAB_NAME (VALUE) — why acceptable extra"
L_irrelevant_summary: one lab per line: "LAB_NAME (VALUE) — why irrelevant to this decision"

R_core = |L_p ∩ L_core| / |L_core|  (w=0.35)
  Interpret R_core=1.0, 0.5, and 0.0 for this specific case.
  Name the most likely missed core labs and their impact.

R_wrong = 1 − |L_p − (L_core ∪ L_opt)| / (|L_p| + ε)  (w=0.20)
  Which irrelevant labs are most likely to be mistakenly requested?
  Score impact of 1, 2, or 3 irrelevant requests.

R_under = −β × (|L_core| − |L_p ∩ L_core|)  (β=${PENALTY_PARAMS.beta}, w=0.10)
  Which core lab, if missed, is the most egregious omission for this patient?

R_over = −α × max(0, |L_p| − |L_core| − |L_opt|)  (α=${PENALTY_PARAMS.alpha}, w=0.20)
  At what threshold does over-requesting become penalised? Give a concrete example.

R_justification scored 0 / 0.5 / 1 (w=0.15):
  justification_score_0: no justification, or completely irrelevant to this patient
  justification_score_0_5: generic — could apply to any AKI patient
  justification_score_1: patient-specific — cites THIS patient's actual values, trajectory, history
  justification_patient_examples: 2-3 example phrases earning score 1 for this patient
  justification_generic_examples: 2-3 example phrases earning only score 0.5

════════════════════════════════════════
PART 3 — Final Reward Formula
════════════════════════════════════════

formula_string: "w1×R_core + w2×R_wrong + w3×R_under + w4×R_over + w5×R_justification + answer_score"
max_lab_score: 0.70
max_answer_score: 1.0
notes: any case-specific edge cases`,
  {
    label:  'rubric-generator',
    phase:  'Rubric',
    schema: RUBRIC_SCHEMA,
  }
)

// ─── final output ─────────────────────────────────────────────────────────────

return {
  patient_id:        args.patient_id,
  rounds_taken:      round,
  passed_evaluation: evaluation?.pass ?? false,
  question: {
    stem:           question.question_stem,
    reasoning_gap:  question.reasoning_gap,
    lab_sets: {
      L_core:       question.lab_sets.L_core,
      L_optional:   question.lab_sets.L_optional,
      L_irrelevant: question.lab_sets.L_irrelevant,
    },
  },
  rubric,
  ground_truth:    args.ground_truth_procedure,
  scoring_params:  { weights: WEIGHTS, penalty_params: PENALTY_PARAMS },
  eval_summary: evaluation
    ? {
        criterion_a: evaluation.criterion_a_verdict,
        criterion_b: evaluation.criterion_b_verdict,
        criterion_c: evaluation.criterion_c_verdict,
        criterion_d: evaluation.criterion_d_verdict,
      }
    : null,
}
