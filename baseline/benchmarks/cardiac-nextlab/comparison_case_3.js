export const meta = {
  name: 'aki-comparison-case-3',
  description: 'Compare with_lab_tools vs no_tools for one AKI benchmark case: tokens, score, n_labs',
  phases: [
    { title: 'with_lab_tools', detail: 'Answer + grade under with_lab_tools condition' },
    { title: 'no_tools',       detail: 'Answer + grade under no_tools condition' },
    { title: 'Compare',        detail: 'Print side-by-side comparison' },
  ],
}

const ANSWER_PATH     = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-nextlab/answer_agent.js'
const SUPERVISOR_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-nextlab/supervisor_grader.js'

const _case_id = 3

const runOne = async (condition) => {
  phase(condition)
  log(`Answering (${condition}) ...`)
  const t0 = budget.spent()

  const run = await workflow({ scriptPath: ANSWER_PATH }, { condition, case_id: _case_id })
  if (!run) { log(`Answer agent failed for ${condition}`); return null }

  const t1 = budget.spent()
  log(`Answer done — ${run.trajectory.lab_requests.length} labs requested. Grading ...`)

  const graded = await workflow({ scriptPath: SUPERVISOR_PATH }, {
    case_id:    run.case_id,
    trajectory: run.trajectory,
  })

  const t2 = budget.spent()

  return {
    condition,
    case_id:      _case_id,
    patient_id:   run.patient_id,
    final_answer: run.trajectory.final_answer,
    total_score:  graded?.reward?.total_score        ?? null,
    lab_score:    graded?.reward?.lab_score          ?? null,
    answer_score: graded?.reward?.answer_score       ?? null,
    R_core:       graded?.reward?.R_core             ?? null,
    R_just:       graded?.reward?.R_justification    ?? null,
    c1:           graded?.reward?.c1_score           ?? null,
    c2:           graded?.reward?.c2_score           ?? null,
    c3:           graded?.reward?.c3_score           ?? null,
    c4:           graded?.reward?.c4_score           ?? null,
    n_labs:       run.trajectory.lab_requests.length,
    tokens_answer: t1 - t0,
    tokens_grade:  t2 - t1,
    tokens_total:  t2 - t0,
  }
}

// Sequential — required for accurate budget.spent() deltas
const withTools = await runOne('with_lab_tools')
const noTools   = await runOne('no_tools')

phase('Compare')

const rows = [withTools, noTools].filter(Boolean)
const pid = withTools?.patient_id ?? noTools?.patient_id

log('')
log('╔══════════════════════════════════════════════════════════════════════════════════╗')
log(`║  CASE ${_case_id} — Patient ${pid}                                                 `)
log('╠══════════════════════════════════════════════════════════════════════════════════╣')
log('║  condition        | total    | lab    | answer | n_labs | tok_answer | tok_grade ')
log('║  -----------------|----------|--------|--------|--------|------------|----------')
for (const r of rows) {
  const cond    = r.condition.padEnd(17)
  const total   = r.total_score  !== null ? (r.total_score.toFixed(3)  + '/1.70').padEnd(8) : 'n/a     '
  const lab     = r.lab_score    !== null ? (r.lab_score.toFixed(3)   + '/0.70').padEnd(6) : 'n/a   '
  const ans     = r.answer_score !== null ? (r.answer_score.toFixed(3) + '/1.00').padEnd(6) : 'n/a   '
  const nlabs   = String(r.n_labs).padStart(6)
  const tokA    = String(r.tokens_answer).padStart(10)
  const tokG    = String(r.tokens_grade).padStart(10)
  log(`║  ${cond}| ${total} | ${lab} | ${ans} | ${nlabs} | ${tokA} | ${tokG}`)
}
log('╠══════════════════════════════════════════════════════════════════════════════════╣')
log('║  Subscores (c1–c4 and R_core / R_just):')
for (const r of rows) {
  const cond = r.condition.padEnd(17)
  const c1   = r.c1    !== null ? r.c1.toFixed(2)    : 'n/a'
  const c2   = r.c2    !== null ? r.c2.toFixed(2)    : 'n/a'
  const c3   = r.c3    !== null ? r.c3.toFixed(2)    : 'n/a'
  const c4   = r.c4    !== null ? r.c4.toFixed(2)    : 'n/a'
  const rc   = r.R_core !== null ? r.R_core.toFixed(2) : 'n/a'
  const rj   = r.R_just !== null ? r.R_just.toFixed(2) : 'n/a'
  log(`║  ${cond}  c1=${c1}  c2=${c2}  c3=${c3}  c4=${c4}  R_core=${rc}  R_just=${rj}`)
}
log('╚══════════════════════════════════════════════════════════════════════════════════╝')

return { case_id: _case_id, results: rows }
