export const meta = {
  name: 'aki-supervisor-grader',
  description: 'Supervisor agent team: Reward, Critic, and Optimizer agents grade a pre-collected answering agent trajectory',
  phases: [
    { title: 'Load',     detail: 'Read benchmark case rubric from aki_benchmark_v1.json' },
    { title: 'Reward',   detail: 'Compute scalar scores against the rubric' },
    { title: 'Critique', detail: 'Explain each score and suggest improvements' },
    { title: 'Optimize', detail: 'Generate policy suggestions for future agents' },
  ],
}

// ─── Input (args) ─────────────────────────────────────────────────────────────
// Option A — inline:
//   { case_id: number, trajectory: { lab_requests, final_answer, reasoning_summary } }
//
// Option B — file path (use when trajectory is large):
//   { trajectory_file: "/path/to/trajectory.json" }
//   The JSON file must contain both case_id and trajectory at the top level.

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/aki/output/aki_benchmark_v1.json'
const WEIGHTS = { w1: 0.35, w2: 0.20, w3: 0.10, w4: 0.20, w5: 0.15 }
const PENALTY = { beta: 2.0, alpha: 0.5 }

// Resolve args — inline or file
let _resolvedArgs = args || {}
if (_resolvedArgs.trajectory_file) {
  const _loaded = await agent(
    `Read the JSON file at ${_resolvedArgs.trajectory_file} and return its full contents as a JSON object with case_id (number) and trajectory (object with lab_requests array, final_answer string, reasoning_summary string).`,
    {
      label: 'trajectory-loader',
      schema: {
        type: 'object',
        required: ['case_id', 'trajectory'],
        properties: {
          case_id: { type: 'number' },
          trajectory: {
            type: 'object',
            required: ['lab_requests', 'final_answer', 'reasoning_summary'],
            properties: {
              lab_requests: { type: 'array', items: { type: 'object' } },
              final_answer: { type: 'string' },
              reasoning_summary: { type: 'string' },
            },
          },
        },
      },
    }
  )
  if (!_loaded) throw new Error(`Could not load trajectory file: ${_resolvedArgs.trajectory_file}`)
  _resolvedArgs = _loaded
}

const CASE_ID    = _resolvedArgs.case_id    ? Number(_resolvedArgs.case_id)    : 1
const TRAJECTORY = _resolvedArgs.trajectory ? _resolvedArgs.trajectory          : null

if (!TRAJECTORY) throw new Error('args.trajectory is required. Pass { case_id, trajectory: { lab_requests, final_answer, reasoning_summary } } or { trajectory_file: "/path/to/file.json" }')

// ─── Schemas ──────────────────────────────────────────────────────────────────

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
    'lab_score',
    'c1_score', 'c2_score', 'c3_score', 'c4_score',
    'answer_score', 'total_score',
    'core_labs_cited', 'core_labs_missing',
    'irrelevant_cited_as_driver',
    'justification_quality_per_lab',
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
      description: 'One entry for EVERY lab request in the trajectory, regardless of category',
      items: {
        type: 'object',
        required: ['lab_name', 'lab_category', 'score', 'reason'],
        properties: {
          lab_name:     { type: 'string' },
          lab_category: { type: 'string', enum: ['L_core', 'L_optional', 'L_irrelevant'] },
          score:        { type: 'number', description: '0, 0.5, or 1' },
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

// ─── Phase 0: Load Case ───────────────────────────────────────────────────────

phase('Load')
log(`Loading benchmark case ${CASE_ID} ...`)

const benchCase = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Find the case object where case_id equals ${CASE_ID}.

Return exactly these fields:
- patient_id: case.patient_id
- demographics_age: case.demographics.age
- demographics_gender: case.demographics.gender
- ground_truth: case.ground_truth
- l_core_names: array of lab_name strings from case.question.lab_sets.L_core
- l_optional_names: array of lab_name strings from case.question.lab_sets.L_optional
- l_irrelevant_names: array of lab_name strings from case.question.lab_sets.L_irrelevant
- answer_rubric_c1_exact: case.rubric.answer_rubric.c1_exact_answer
- answer_rubric_c1_synonyms: case.rubric.answer_rubric.c1_accepted_synonyms
- answer_rubric_c2_labs: case.rubric.answer_rubric.c2_required_labs_summary (full text)
- answer_rubric_c3_steps: case.rubric.answer_rubric.c3_required_steps array
- answer_rubric_c4_facts: case.rubric.answer_rubric.c4_required_patient_facts (full text)
- justification_score_0: case.rubric.lab_scoring_rubric.justification_score_0
- justification_score_0_5: case.rubric.lab_scoring_rubric.justification_score_0_5
- justification_score_1: case.rubric.lab_scoring_rubric.justification_score_1`,
  { label: 'case-loader', phase: 'Load', schema: CASE_SCHEMA }
)

if (!benchCase) throw new Error(`Failed to load case ${CASE_ID}`)

const nCore      = benchCase.l_core_names.length
const nOptional  = benchCase.l_optional_names.length
const nIrrelevant = benchCase.l_irrelevant_names.length

log(`Patient ${benchCase.patient_id} — ${benchCase.demographics_age}y ${benchCase.demographics_gender}`)
log(`Ground truth: ${benchCase.ground_truth}`)
log(`L_core (${nCore}): ${benchCase.l_core_names.join(', ')}`)

// ─── Phase 1: Reward Agent ────────────────────────────────────────────────────

phase('Reward')
log('Computing reward scores ...')

const reward = await agent(
  `You are the Reward Agent for the AKI benchmark supervisor team.
Your sole responsibility: compute every numeric score in the rubric from the trajectory. Output authority only — no critique, no suggestions.
Show all intermediate steps before returning the schema.

════════════════════════════════════════
OFFICIAL RUBRIC
════════════════════════════════════════
Ground truth: ${benchCase.ground_truth}
Accepted synonyms: ${JSON.stringify(benchCase.answer_rubric_c1_synonyms)}

L_core labs (${nCore} total — missing any is heavily penalised):
${benchCase.l_core_names.map((n, i) => `  ${i+1}. ${n}`).join('\n')}

L_optional labs (${nOptional} total — acceptable extras):
${benchCase.l_optional_names.map((n, i) => `  ${i+1}. ${n}`).join('\n')}

L_irrelevant labs (${nIrrelevant} total — citing as PRIMARY drivers is penalised):
${benchCase.l_irrelevant_names.map((n, i) => `  ${i+1}. ${n}`).join('\n')}

c2 required labs (one per line — lab name, expected value, and why it drives the decision):
${benchCase.answer_rubric_c2_labs}

c3 required causal chain steps:
${benchCase.answer_rubric_c3_steps.map((s, i) => `  ${i+1}. ${s}`).join('\n')}

c4 required patient facts:
${benchCase.answer_rubric_c4_facts}

Justification scoring:
  Score 0:   ${benchCase.justification_score_0}
  Score 0.5: ${benchCase.justification_score_0_5}
  Score 1:   ${benchCase.justification_score_1}

════════════════════════════════════════
TRAJECTORY TO GRADE
════════════════════════════════════════
Lab requests (${TRAJECTORY.lab_requests.length} total):
${JSON.stringify(TRAJECTORY.lab_requests, null, 2)}

Final answer: "${TRAJECTORY.final_answer}"
Reasoning summary: ${TRAJECTORY.reasoning_summary}

════════════════════════════════════════
SCORING PROCEDURE
════════════════════════════════════════
Weights: w1=${WEIGHTS.w1}(R_core) w2=${WEIGHTS.w2}(R_wrong) w3=${WEIGHTS.w3}(R_under) w4=${WEIGHTS.w4}(R_over) w5=${WEIGHTS.w5}(R_just)
β=${PENALTY.beta}, α=${PENALTY.alpha}

Step 1 — core_labs_cited: L_core labs present in lab_requests WITH a correct directional interpretation in value_received.
Step 2 — core_labs_missing: L_core labs NOT cited or cited with wrong interpretation.
Step 3 — irrelevant_cited_as_driver: L_irrelevant labs used as PRIMARY justification for the procedure (not merely mentioned in passing).
Step 4 — justification_quality_per_lab: score EVERY lab request in the trajectory 0/0.5/1 using these criteria:
  L_core labs:
    0   = no justification, generic, or factually wrong
    0.5 = correct clinical context but generic — could apply to any AKI patient
    1   = patient-specific — references this patient's actual values, diagnoses, or clinical context (no guideline citation required)
  L_optional labs:
    0   = no justification or clinically irrelevant reason given
    0.5 = reasonable but vague (e.g. "commonly ordered alongside core labs")
    1   = specific clinical reason tied to this patient's presentation
  L_irrelevant labs:
    0   = justification incorrectly claims this lab drives the procedure decision
    0.5 = lab requested but justification correctly notes it is supporting context only
    1   = lab explicitly justified as contextual/completeness only, not a primary driver
  R_justification = mean score across ALL lab requests (not just L_core).

Formulas:
  n_core_cited       = |core_labs_cited|
  n_optional_cited   = number of L_optional labs in lab_requests
  n_irrelevant_cited = number of L_irrelevant labs in lab_requests
  n_irrelevant_driver= |irrelevant_cited_as_driver|

  R_core  = n_core_cited / ${nCore}
  R_wrong = 1 - (n_irrelevant_driver / ${nIrrelevant})
  R_under = exp(-${PENALTY.beta} * max(0, (${nCore} - n_core_cited) / ${nCore}))
  R_over  = exp(-${PENALTY.alpha} * max(0, (n_optional_cited + n_irrelevant_cited - ${nCore}) / ${nOptional}))
  lab_score = min(0.70, ${WEIGHTS.w1}*R_core + ${WEIGHTS.w2}*R_wrong + ${WEIGHTS.w3}*R_under + ${WEIGHTS.w4}*R_over + ${WEIGHTS.w5}*R_justification)

  c1_score: 1.0 = exact match or accepted synonym; 0.5 = clearly close but not exact; 0.0 = wrong
  c2_score: fraction of required labs (from c2 list) cited with their correct values in the trajectory
  c3_score: fraction of required causal chain steps present in reasoning_summary
  c4_score: fraction of required patient facts correctly stated in final_answer + reasoning_summary
  answer_score = (c1_score + c2_score + c3_score + c4_score) / 4
  total_score = lab_score + answer_score`,
  { label: 'reward-agent', phase: 'Reward', schema: REWARD_SCHEMA }
)

if (!reward) throw new Error('Reward agent returned null')

log(`lab_score=${reward.lab_score.toFixed(3)}/0.70  answer_score=${reward.answer_score.toFixed(3)}/1.00  total=${reward.total_score.toFixed(3)}/1.70`)
log(`R_core=${reward.R_core.toFixed(3)} R_wrong=${reward.R_wrong.toFixed(3)} R_under=${reward.R_under.toFixed(3)} R_over=${reward.R_over.toFixed(3)} R_just=${reward.R_justification.toFixed(3)}`)
log(`c1=${reward.c1_score.toFixed(2)} c2=${reward.c2_score.toFixed(2)} c3=${reward.c3_score.toFixed(2)} c4=${reward.c4_score.toFixed(2)}`)
log(`Missing core labs: ${reward.core_labs_missing.length ? reward.core_labs_missing.join(', ') : 'none'}`)

// ─── Phase 2: Critic Agent ────────────────────────────────────────────────────

phase('Critique')
log('Running critic agent ...')

const critique = await agent(
  `You are the Critic Agent for the AKI benchmark supervisor team.
You have NO scoring authority — the reward scores below are final and you must not change them.
Your role: explain WHY each score was given and HOW the agent could have scored higher.

════════════════════════════════════════
REWARD SCORES (final)
════════════════════════════════════════
lab_score: ${reward.lab_score.toFixed(3)} / 0.70
  R_core:          ${reward.R_core.toFixed(3)}  — ${reward.core_labs_cited.length}/${nCore} core labs correctly cited
  R_wrong:         ${reward.R_wrong.toFixed(3)}  — ${reward.irrelevant_cited_as_driver.length} irrelevant labs cited as drivers
  R_under:         ${reward.R_under.toFixed(3)}  — under-coverage penalty
  R_over:          ${reward.R_over.toFixed(3)}  — over-coverage penalty
  R_justification: ${reward.R_justification.toFixed(3)}  — mean justification quality

answer_score: ${reward.answer_score.toFixed(3)} / 1.00
  c1 (correct procedure): ${reward.c1_score.toFixed(2)}
  c2 (lab use):           ${reward.c2_score.toFixed(2)}
  c3 (causal chain):      ${reward.c3_score.toFixed(2)}
  c4 (patient accuracy):  ${reward.c4_score.toFixed(2)}

total_score: ${reward.total_score.toFixed(3)} / 1.70

Core labs missing:          ${reward.core_labs_missing.join(', ') || 'none'}
Irrelevant cited as driver: ${reward.irrelevant_cited_as_driver.join(', ') || 'none'}

Justification quality per lab:
${JSON.stringify(reward.justification_quality_per_lab, null, 2)}

════════════════════════════════════════
TRAJECTORY
════════════════════════════════════════
Lab requests:
${JSON.stringify(TRAJECTORY.lab_requests, null, 2)}

Final answer: "${TRAJECTORY.final_answer}"
Reasoning: ${TRAJECTORY.reasoning_summary}

════════════════════════════════════════
RUBRIC REFERENCE
════════════════════════════════════════
Ground truth: ${benchCase.ground_truth}
Synonyms: ${benchCase.answer_rubric_c1_synonyms.join(', ')}
c2 required labs: ${benchCase.answer_rubric_c2_labs}
c3 required steps: ${benchCase.answer_rubric_c3_steps.map((s, i) => `(${i+1}) ${s}`).join(' → ')}
c4 required facts: ${benchCase.answer_rubric_c4_facts}
Score-1 justification: ${benchCase.justification_score_1}

════════════════════════════════════════
WRITE YOUR CRITIQUE IN FOUR SECTIONS
════════════════════════════════════════

**1. Lab Coverage**
For each missing L_core lab: what should have been requested, what value the rubric expected, and how many points this miss cost.
For each correctly cited L_core lab: briefly confirm it.

**2. Justification Quality**
For each lab request (L_core, L_optional, or L_irrelevant) with justification score < 1: quote the agent's exact justification, identify the lab's category, explain why it scored 0 or 0.5, and give a model score-1 example for that same lab and category.

**3. Answer Quality (c1–c4)**
For any criterion below 1.0: identify what was missing or wrong, quote the relevant text from the trajectory, and state what was needed for full credit.

**4. Overall Assessment**
One paragraph: what the agent did well, the most impactful failures, and the single highest-priority fix.`,
  { label: 'critic-agent', phase: 'Critique' }
)

log('Critique complete.')

// ─── Phase 3: Optimizer Agent ─────────────────────────────────────────────────

phase('Optimize')
log('Running optimizer agent ...')

const optimizerResult = await agent(
  `You are the Optimizer Agent for the AKI benchmark supervisor team.
No RL algorithm is implemented yet — your output is a placeholder for future policy updates.
Produce actionable PROMPT-LEVEL improvements that would raise the answering agent's score on this case.

════════════════════════════════════════
SCORE SUMMARY
════════════════════════════════════════
Case ${CASE_ID} — Patient ${benchCase.patient_id} (${benchCase.demographics_age}y ${benchCase.demographics_gender})
Ground truth: ${benchCase.ground_truth}

total_score:  ${reward.total_score.toFixed(3)} / 1.70
lab_score:    ${reward.lab_score.toFixed(3)} / 0.70  (R_core=${reward.R_core.toFixed(3)} R_wrong=${reward.R_wrong.toFixed(3)} R_under=${reward.R_under.toFixed(3)} R_over=${reward.R_over.toFixed(3)} R_just=${reward.R_justification.toFixed(3)})
answer_score: ${reward.answer_score.toFixed(3)} / 1.00  (c1=${reward.c1_score.toFixed(2)} c2=${reward.c2_score.toFixed(2)} c3=${reward.c3_score.toFixed(2)} c4=${reward.c4_score.toFixed(2)})

Missing core labs:  ${reward.core_labs_missing.join(', ') || 'none'}
Weak justifications: ${reward.justification_quality_per_lab.filter(j => j.score < 1).map(j => `${j.lab_name}(${j.lab_category} score=${j.score})`).join(', ') || 'none'}

════════════════════════════════════════
CRITIC ANALYSIS
════════════════════════════════════════
${critique}

════════════════════════════════════════
YOUR OUTPUT
════════════════════════════════════════
policy_suggestions: Complete, copy-paste-ready instruction sentences to add to the answering agent's prompt. Address each observed gap directly.

priority_improvements: The top 3 improvements ranked by expected score impact.
  Format: "[Target +X.XX] Instruction here"
  Example: "[R_core +0.20] Always request Potassium and Bicarbonate when the AKI diagnosis includes tubular necrosis before finalising the procedure decision."

estimated_score_delta: Estimated total score gain if the top 3 suggestions were applied.
  Format: "+X.XX to +X.XX total (lab: +X.XX via R_core/R_under, answer: +X.XX via c2/c3)"`,
  { label: 'optimizer-agent', phase: 'Optimize', schema: OPTIMIZER_SCHEMA }
)

if (optimizerResult) {
  log(`${optimizerResult.priority_improvements.length} priority improvements. Estimated delta: ${optimizerResult.estimated_score_delta}`)
}

// ─── Return ───────────────────────────────────────────────────────────────────

return {
  case_id:    CASE_ID,
  patient_id: benchCase.patient_id,
  reward,
  critique,
  optimizer_suggestions: optimizerResult,
}
