export const meta = {
  name: 'test-supervisor',
  description: 'Smoke test for Reward, Critic, Optimizer agents using hardcoded case 1 trajectory',
  phases: [
    { title: 'Load',     detail: 'Read case 1 rubric from aki_benchmark_v1.json' },
    { title: 'Reward',   detail: 'Compute scalar scores' },
    { title: 'Critique', detail: 'Explain scores' },
    { title: 'Optimize', detail: 'Policy suggestions' },
  ],
}

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/output/aki_benchmark_v1.json'
const WEIGHTS = { w1: 0.35, w2: 0.20, w3: 0.10, w4: 0.20, w5: 0.15 }
const PENALTY = { beta: 2.0, alpha: 0.5 }

// Hardcoded test trajectory — case 1 (patient 10039708, CRRT)
// Missing Urine Casts (one L_core lab) to test partial scoring
const CASE_ID = 1
const TRAJECTORY = {
  lab_requests: [
    {
      lab_name: 'Creatinine',
      date_taken: '2148-08-16',
      justification: 'KDIGO 2012 Section 2.1.1 defines AKI Stage 3 as creatinine exceeding 3x baseline or rising above 4.0 mg/dL. This patient has ATN; establishing creatinine trajectory confirms AKI severity and determines whether RRT threshold is met.',
      value_received: '| Creatinine | 2148-08-16 | 2.2 | mg/dL | 0.6 | 1.1 | abnormal |',
    },
    {
      lab_name: 'BUN',
      date_taken: '2148-08-16',
      justification: 'KDIGO 2012 Section 5.3 identifies uremic complications as an absolute RRT indication. BUN trajectory alongside creatinine quantifies uremic solute burden and determines whether azotemia crosses the intervention threshold.',
      value_received: '| BUN | 2148-08-16 | 45 | mg/dL | 6 | 20 | abnormal |',
    },
    {
      lab_name: 'Potassium',
      date_taken: '2148-08-16',
      justification: 'Refractory hyperkalemia is an absolute emergent RRT indication per KDIGO 2012 Section 5.3. In this patient with oliguric AKI and tubular necrosis, distal potassium excretion is absent.',
      value_received: '| Potassium | 2148-08-16 | 5.8 | mEq/L | 3.5 | 5.0 | abnormal |',
    },
    {
      lab_name: 'Bicarbonate',
      date_taken: '2148-08-16',
      justification: 'KDIGO 2012 Section 5.3 lists refractory metabolic acidosis as an absolute RRT indication. Low bicarbonate in this patient with ATN and hemodynamic compromise confirms the acid-base threshold for CRRT.',
      value_received: '| Bicarbonate | 2148-08-16 | 16 | mEq/L | 22 | 29 | abnormal |',
    },
    {
      lab_name: 'Lactate',
      date_taken: '2148-08-16',
      justification: 'Elevated lactate confirms hemodynamic instability from CHF and NSTEMI, the primary reason to choose CRRT over intermittent hemodialysis.',
      value_received: '| Lactate | 2148-08-16 | 3.4 | mmol/L | 0.5 | 2.2 | abnormal |',
    },
    {
      lab_name: 'Glucose',
      date_taken: '2148-08-16',
      justification: 'Glucose is routinely checked in ICU patients for glycemic control.',
      value_received: '| Glucose | 2148-08-16 | 142 | mg/dL | 70 | 100 | abnormal |',
    },
  ],
  final_answer: 'Continuous Renal Replacement Therapy (CRRT)',
  reasoning_summary: 'This 46-year-old female with ATN, acute systolic CHF, and NSTEMI has creatinine 2.2 mg/dL (2x female ULN of 1.1), confirming AKI Stage 2. BUN 45 indicates azotemia. Potassium 5.8 mEq/L represents hyperkalemia meeting KDIGO 2012 Section 5.3 RRT threshold. Bicarbonate 16 mEq/L confirms refractory metabolic acidosis, another absolute KDIGO 5.3 indication. Lactate 3.4 confirms hemodynamic instability mandating the continuous modality over intermittent hemodialysis. The patient is on mechanical ventilation.',
}

// ─── Schemas ─────────────────────────────────────────────────────────────────

const CASE_SCHEMA = {
  type: 'object',
  required: [
    'patient_id', 'demographics_age', 'demographics_gender', 'ground_truth',
    'l_core_names', 'l_optional_names', 'l_irrelevant_names',
    'answer_rubric_c1_exact', 'answer_rubric_c1_synonyms',
    'answer_rubric_c2_labs', 'answer_rubric_c3_steps',
    'answer_rubric_c4_facts',
    'justification_score_0', 'justification_score_0_5', 'justification_score_1',
  ],
  properties: {
    patient_id:                  { type: 'string' },
    demographics_age:            { type: 'number' },
    demographics_gender:         { type: 'string' },
    ground_truth:                { type: 'string' },
    l_core_names:                { type: 'array', items: { type: 'string' } },
    l_optional_names:            { type: 'array', items: { type: 'string' } },
    l_irrelevant_names:          { type: 'array', items: { type: 'string' } },
    answer_rubric_c1_exact:      { type: 'string' },
    answer_rubric_c1_synonyms:   { type: 'array', items: { type: 'string' } },
    answer_rubric_c2_labs:       { type: 'string' },
    answer_rubric_c3_steps:      { type: 'array', items: { type: 'string' } },
    answer_rubric_c4_facts:      { type: 'string' },
    justification_score_0:       { type: 'string' },
    justification_score_0_5:     { type: 'string' },
    justification_score_1:       { type: 'string' },
  },
}

const REWARD_SCHEMA = {
  type: 'object',
  required: [
    'R_core', 'R_wrong', 'R_under', 'R_over', 'R_justification',
    'lab_score', 'c1_score', 'c2_score', 'c3_score', 'c4_score',
    'answer_score', 'total_score',
    'core_labs_cited', 'core_labs_missing',
    'irrelevant_cited_as_driver', 'justification_quality_per_lab',
  ],
  properties: {
    R_core:                     { type: 'number' },
    R_wrong:                    { type: 'number' },
    R_under:                    { type: 'number' },
    R_over:                     { type: 'number' },
    R_justification:            { type: 'number' },
    lab_score:                  { type: 'number' },
    c1_score:                   { type: 'number' },
    c2_score:                   { type: 'number' },
    c3_score:                   { type: 'number' },
    c4_score:                   { type: 'number' },
    answer_score:               { type: 'number' },
    total_score:                { type: 'number' },
    core_labs_cited:            { type: 'array', items: { type: 'string' } },
    core_labs_missing:          { type: 'array', items: { type: 'string' } },
    irrelevant_cited_as_driver: { type: 'array', items: { type: 'string' } },
    justification_quality_per_lab: {
      type: 'array',
      items: {
        type: 'object',
        required: ['lab_name', 'lab_category', 'score', 'reason'],
        properties: {
          lab_name:     { type: 'string' },
          lab_category: { type: 'string', enum: ['L_core', 'L_optional', 'L_irrelevant'] },
          score:        { type: 'number' },
          reason:       { type: 'string' },
        },
      },
    },
  },
}

const OPTIMIZER_SCHEMA = {
  type: 'object',
  required: ['policy_suggestions', 'priority_improvements', 'estimated_score_delta'],
  properties: {
    policy_suggestions:    { type: 'array', items: { type: 'string' } },
    priority_improvements: { type: 'array', items: { type: 'string' } },
    estimated_score_delta: { type: 'string' },
  },
}

// ─── Phase 0: Load ────────────────────────────────────────────────────────────

phase('Load')
log('Loading case 1 rubric ...')

const benchCase = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}. Find case_id = 1. Return:
- patient_id, demographics_age, demographics_gender, ground_truth
- l_core_names: array of lab_name from question.lab_sets.L_core
- l_optional_names: array of lab_name from question.lab_sets.L_optional
- l_irrelevant_names: array of lab_name from question.lab_sets.L_irrelevant
- answer_rubric_c1_exact, answer_rubric_c1_synonyms
- answer_rubric_c2_labs (c2_required_labs_summary), answer_rubric_c3_steps (c3_required_steps array)
- answer_rubric_c4_facts (c4_required_patient_facts)
- justification_score_0, justification_score_0_5, justification_score_1 (from lab_scoring_rubric)`,
  { label: 'case-loader', phase: 'Load', schema: CASE_SCHEMA }
)

if (!benchCase) throw new Error('Failed to load case')

const nCore      = benchCase.l_core_names.length
const nOptional  = benchCase.l_optional_names.length
const nIrrelevant = benchCase.l_irrelevant_names.length

log(`Patient ${benchCase.patient_id} — ground truth: ${benchCase.ground_truth}`)
log(`L_core (${nCore}): ${benchCase.l_core_names.join(', ')}`)

// ─── Phase 1: Reward Agent ────────────────────────────────────────────────────

phase('Reward')
log('Scoring trajectory ...')

const reward = await agent(
  `You are the Reward Agent. Compute all numeric scores for this trajectory against the rubric. Show all steps.

RUBRIC:
Ground truth: ${benchCase.ground_truth}
Synonyms: ${JSON.stringify(benchCase.answer_rubric_c1_synonyms)}

L_core (${nCore}): ${benchCase.l_core_names.map((n,i) => `${i+1}. ${n}`).join(', ')}
L_optional (${nOptional}): ${benchCase.l_optional_names.map((n,i) => `${i+1}. ${n}`).join(', ')}
L_irrelevant (${nIrrelevant}): ${benchCase.l_irrelevant_names.map((n,i) => `${i+1}. ${n}`).join(', ')}

c2 required labs: ${benchCase.answer_rubric_c2_labs}
c3 steps: ${benchCase.answer_rubric_c3_steps.map((s,i) => `${i+1}. ${s}`).join(' | ')}
c4 facts: ${benchCase.answer_rubric_c4_facts}

Justification scoring:
  0:   ${benchCase.justification_score_0}
  0.5: ${benchCase.justification_score_0_5}
  1:   ${benchCase.justification_score_1}

TRAJECTORY:
Lab requests (${TRAJECTORY.lab_requests.length}):
${JSON.stringify(TRAJECTORY.lab_requests, null, 2)}

Final answer: "${TRAJECTORY.final_answer}"
Reasoning: ${TRAJECTORY.reasoning_summary}

FORMULAS (weights: w1=${WEIGHTS.w1} w2=${WEIGHTS.w2} w3=${WEIGHTS.w3} w4=${WEIGHTS.w4} w5=${WEIGHTS.w5}; β=${PENALTY.beta} α=${PENALTY.alpha}):
  R_core  = n_core_cited / ${nCore}
  R_wrong = 1 - (n_irrelevant_driver / ${nIrrelevant})
  R_under = exp(-${PENALTY.beta} * max(0, (${nCore} - n_core_cited) / ${nCore}))
  R_over  = exp(-${PENALTY.alpha} * max(0, (n_optional_cited + n_irrelevant_cited - ${nCore}) / ${nOptional}))
  R_justification = mean 0/0.5/1 score across ALL lab requests
  lab_score = min(0.70, w1*R_core + w2*R_wrong + w3*R_under + w4*R_over + w5*R_justification)
  answer_score = mean(c1, c2, c3, c4); total = lab_score + answer_score

For justification_quality_per_lab: score every request (all categories) with lab_category = L_core / L_optional / L_irrelevant.`,
  { label: 'reward-agent', phase: 'Reward', schema: REWARD_SCHEMA }
)

if (!reward) throw new Error('Reward agent returned null')
log(`lab=${reward.lab_score.toFixed(3)}/0.70  answer=${reward.answer_score.toFixed(3)}/1.00  total=${reward.total_score.toFixed(3)}/1.70`)
log(`R_core=${reward.R_core.toFixed(3)} R_wrong=${reward.R_wrong.toFixed(3)} R_under=${reward.R_under.toFixed(3)} R_over=${reward.R_over.toFixed(3)} R_just=${reward.R_justification.toFixed(3)}`)
log(`Missing: ${reward.core_labs_missing.join(', ') || 'none'}`)

// ─── Phase 2: Critic Agent ────────────────────────────────────────────────────

phase('Critique')
log('Critiquing ...')

const critique = await agent(
  `You are the Critic Agent. Scores are final — explain them and suggest improvements.

SCORES:
lab_score=${reward.lab_score.toFixed(3)}/0.70 (R_core=${reward.R_core.toFixed(3)} R_wrong=${reward.R_wrong.toFixed(3)} R_under=${reward.R_under.toFixed(3)} R_over=${reward.R_over.toFixed(3)} R_just=${reward.R_justification.toFixed(3)})
answer_score=${reward.answer_score.toFixed(3)}/1.00 (c1=${reward.c1_score.toFixed(2)} c2=${reward.c2_score.toFixed(2)} c3=${reward.c3_score.toFixed(2)} c4=${reward.c4_score.toFixed(2)})
total=${reward.total_score.toFixed(3)}/1.70

Missing core labs: ${reward.core_labs_missing.join(', ') || 'none'}
Irrelevant cited as driver: ${reward.irrelevant_cited_as_driver.join(', ') || 'none'}
Weak justifications: ${reward.justification_quality_per_lab.filter(j => j.score < 1).map(j => j.lab_name + '(' + j.lab_category + ' ' + j.score + ')').join(', ') || 'none'}

TRAJECTORY:
${JSON.stringify(TRAJECTORY.lab_requests, null, 2)}
Final answer: "${TRAJECTORY.final_answer}"

RUBRIC REFERENCE:
c2 labs: ${benchCase.answer_rubric_c2_labs}
c3 steps: ${benchCase.answer_rubric_c3_steps.map((s,i) => '(' + (i+1) + ') ' + s).join(' → ')}
c4 facts: ${benchCase.answer_rubric_c4_facts}
Score-1 justification: ${benchCase.justification_score_1}

Write four sections: 1) Lab Coverage, 2) Justification Quality, 3) Answer Quality (c1-c4), 4) Overall Assessment.`,
  { label: 'critic-agent', phase: 'Critique' }
)

log('Critique done.')

// ─── Phase 3: Optimizer Agent ─────────────────────────────────────────────────

phase('Optimize')
log('Generating policy suggestions ...')

const optimizerResult = await agent(
  `You are the Optimizer Agent. No RL yet — produce prompt-level improvement suggestions.

SCORES: total=${reward.total_score.toFixed(3)}/1.70, lab=${reward.lab_score.toFixed(3)}, answer=${reward.answer_score.toFixed(3)}
Missing core labs: ${reward.core_labs_missing.join(', ') || 'none'}
Weak justifications: ${reward.justification_quality_per_lab.filter(j => j.score < 1).map(j => j.lab_name).join(', ') || 'none'}

CRITIC: ${critique}

Return:
- policy_suggestions: specific prompt instructions to add (complete sentences, copy-paste ready)
- priority_improvements: top 3 ranked by score impact, format "[Target +X.XX] instruction"
- estimated_score_delta: "+X.XX to +X.XX total (...)"`,
  { label: 'optimizer-agent', phase: 'Optimize', schema: OPTIMIZER_SCHEMA }
)

log(`Optimizer: ${optimizerResult ? optimizerResult.priority_improvements.length : 0} priority improvements. Delta: ${optimizerResult ? optimizerResult.estimated_score_delta : 'n/a'}`)

return {
  case_id: CASE_ID,
  patient_id: benchCase.patient_id,
  reward,
  critique,
  optimizer_suggestions: optimizerResult,
}
