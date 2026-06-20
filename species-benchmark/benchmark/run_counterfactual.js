export const meta = {
  name: 'run-counterfactual',
  description: 'Counterfactual sensitivity test: swap pivot lab to VN-normal, check if answer changes',
  phases: [
    { title: 'Answer' },
    { title: 'Grade' },
  ],
}

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/output/species_benchmark_v1.json'

// One case_id per action type (from the benchmark — first case of each action when sorted by case_id)
// anticoagulation_reversal=1, dka_hhs_protocol=6, emergent_rrt=11,
// nephrology_consult=16, potassium_repletion=21, prbc_transfusion=26, severe_hyponatremia=31
const TEST_CASE_IDS = [1, 6, 11, 16, 21, 26, 31]

const ANSWER_SCHEMA = {
  type: 'object',
  properties: {
    immediate_action:     { type: 'string' },
    definitive_treatment: { type: 'string' },
    reasoning:            { type: 'string' },
  },
  required: ['immediate_action', 'definitive_treatment', 'reasoning']
}

phase('Answer')

const answerResults = await parallel(TEST_CASE_IDS.flatMap(caseId => [
  () => agent(
    `Read the benchmark file at ${BENCHMARK_PATH} and find the case with case_id=${caseId}.
Then answer the REAL condition question_stem (the "question_stem" field, NOT "counterfactual").
Return your clinical answer as the structured output.`,
    { label: `real-${caseId}`, phase: 'Answer', schema: ANSWER_SCHEMA }
  ).then(a => ({ caseId, condition: 'real', answer: a })),

  () => agent(
    `Read the benchmark file at ${BENCHMARK_PATH} and find the case with case_id=${caseId}.
Then answer the COUNTERFACTUAL question stem found at case.counterfactual.question_stem.
Return your clinical answer as the structured output.`,
    { label: `cf-${caseId}`, phase: 'Answer', schema: ANSWER_SCHEMA }
  ).then(a => ({ caseId, condition: 'counterfactual', answer: a })),
]))

// Pair by caseId
const byCase = {}
for (const r of answerResults.filter(Boolean)) {
  if (!byCase[r.caseId]) byCase[r.caseId] = {}
  byCase[r.caseId][r.condition] = r.answer
}

phase('Grade')

const GRADE_SCHEMA = {
  type: 'object',
  properties: {
    action_label:         { type: 'string' },
    real_correct_action:  { type: 'number' },
    cf_correct_action:    { type: 'number', description: '1 if CF answer ALSO recommends the same intervention as real — bad, shows insensitivity' },
    answers_differ:       { type: 'number', description: '1 if real and counterfactual recommend meaningfully different primary interventions; 0 if same' },
    real_answer_summary:  { type: 'string', description: 'One-phrase summary of real condition primary intervention' },
    cf_answer_summary:    { type: 'string', description: 'One-phrase summary of counterfactual condition primary intervention' },
    why_no_change:        { type: 'string', description: 'If answers_differ=0, explain which other lab(s) drove the same answer in the CF condition. Empty string if answers_differ=1.' },
    explanation:          { type: 'string' },
  },
  required: ['action_label', 'real_correct_action', 'cf_correct_action', 'answers_differ', 'real_answer_summary', 'cf_answer_summary', 'why_no_change', 'explanation']
}

const grades = await parallel(TEST_CASE_IDS.map(caseId => () => {
  const pair = byCase[caseId]
  if (!pair || !pair.real || !pair.counterfactual) return Promise.resolve(null)

  return agent(
    `Read the benchmark file at ${BENCHMARK_PATH} and find the case with case_id=${caseId}.
Extract: action_label, rubric.correct_synonyms, rubric.wrong_answers, counterfactual.pivot_lab, counterfactual.pivot_val_real, counterfactual.pivot_val_cf, counterfactual.pivot_range.

Then grade the following two answers:

REAL CONDITION (pivot lab is ABNORMAL — outside the VN reference range):
  Immediate: ${pair.real.immediate_action}
  Definitive: ${pair.real.definitive_treatment}

COUNTERFACTUAL CONDITION (pivot lab set to VN-NORMAL midpoint — all other labs unchanged):
  Immediate: ${pair.counterfactual.immediate_action}
  Definitive: ${pair.counterfactual.definitive_treatment}

Grade:
- action_label: the case's action_label string
- real_correct_action: 1 if real answer matches correct_synonyms for this case's action
- cf_correct_action: 1 if counterfactual answer ALSO recommends the same action as the real case (this is bad — it means normalizing the pivot lab didn't change the answer)
- answers_differ: 1 if the two answers recommend meaningfully different primary interventions, 0 if same
- real_answer_summary: one phrase for real condition primary action
- cf_answer_summary: one phrase for CF condition primary action
- why_no_change: if answers_differ=0, name the other lab(s) in the CF condition that still drove the same answer despite the pivot being normalized
- explanation: brief explanation of scoring`,
    { label: `grade-${caseId}`, phase: 'Grade', schema: GRADE_SCHEMA }
  ).then(g => ({ caseId, grade: g }))
}))

// Print results table
log('')
log('═══════════════════════════════════════════════════════════════════════════════')
log('  COUNTERFACTUAL SENSITIVITY RESULTS')
log('  answers_differ=1 → agent changed answer when pivot lab normalized (GOOD)')
log('  answers_differ=0 → same answer regardless of pivot value (MEMORIZATION/CONFOUNDER)')
log('═══════════════════════════════════════════════════════════════════════════════')
log(`  ${'Action'.padEnd(28)} ${'Correct'.padEnd(8)} ${'Differ'.padEnd(8)} Real → CF`)

const rows = []
for (const g of grades.filter(Boolean)) {
  if (!g.grade) continue
  const { action_label, real_correct_action, answers_differ, real_answer_summary, cf_answer_summary, why_no_change } = g.grade
  const confounders = why_no_change ? `  [confounders: ${why_no_change}]` : ''
  log(`  ${action_label.padEnd(28)} ${String(real_correct_action).padEnd(8)} ${String(answers_differ).padEnd(8)} "${real_answer_summary}" → "${cf_answer_summary}"${confounders}`)
  rows.push({ caseId: g.caseId, ...g.grade })
}

const avgSensitivity = rows.reduce((s, r) => s + r.answers_differ, 0) / rows.length
const avgCorrect     = rows.reduce((s, r) => s + r.real_correct_action, 0) / rows.length
log('')
log(`  Mean real accuracy:             ${avgCorrect.toFixed(2)}`)
log(`  Mean counterfactual sensitivity: ${avgSensitivity.toFixed(2)}  (ideal=1.0, random≈0.5)`)
log('═══════════════════════════════════════════════════════════════════════════════')

return { rows, avgSensitivity, avgCorrect }
