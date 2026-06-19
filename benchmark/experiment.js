export const meta = {
  name: 'aki-experiment',
  description: 'Two-condition AKI experiment: runs with_lab_tools and no_tools agents then grades each with supervisor',
  phases: [
    { title: 'Answer',  detail: 'Run answering agents for all conditions × cases in parallel' },
    { title: 'Grade',   detail: 'Grade each trajectory with supervisor_grader in parallel' },
    { title: 'Compare', detail: 'Build score comparison table' },
  ],
}

// ─── Configuration ────────────────────────────────────────────────────────────
// Control scope via args: { case_ids?: number[], conditions?: string[] }
// Defaults to all 4 cases and both conditions.
// Examples:
//   Quick test: { case_ids: [1], conditions: ['with_lab_tools', 'no_tools'] }
//   Single condition: { conditions: ['no_tools'] }

const ANSWER_AGENT_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/answer_agent.js'
const SUPERVISOR_PATH   = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/supervisor_grader.js'

const _conditions = (args && args.conditions) ? args.conditions : ['with_lab_tools', 'no_tools']
const _case_ids   = (args && args.case_ids)   ? args.case_ids.map(Number) : [1, 2, 3, 4]

const totalRuns = _conditions.length * _case_ids.length

// ─── Phase 0: Answer ─────────────────────────────────────────────────────────
// All (condition × case_id) combinations run in parallel.

phase('Answer')
log(`Running ${_conditions.length} condition(s) × ${_case_ids.length} case(s) = ${totalRuns} answering agents`)

const answeredRuns = await parallel(
  _case_ids.flatMap(case_id =>
    _conditions.map(condition => () =>
      workflow({ scriptPath: ANSWER_AGENT_PATH }, { condition, case_id })
        .then(r => ({ ...r, condition, case_id }))
        .catch(err => {
          log(`FAILED: answer_agent case=${case_id} condition=${condition} — ${err.message}`)
          return null
        })
    )
  )
)

const validAnswers = answeredRuns.filter(Boolean)
log(`${validAnswers.length}/${totalRuns} answering runs completed`)

if (validAnswers.length === 0) throw new Error('All answering agents failed — cannot grade')

// ─── Phase 1: Grade ───────────────────────────────────────────────────────────
// All trajectories graded in parallel.

phase('Grade')
log(`Grading ${validAnswers.length} trajectories ...`)

const gradedRuns = await parallel(
  validAnswers.map(run => () =>
    workflow(
      { scriptPath: SUPERVISOR_PATH },
      { case_id: run.case_id, trajectory: run.trajectory }
    )
      .then(g => ({
        condition:       run.condition,
        case_id:         run.case_id,
        patient_id:      run.patient_id,
        total_score:     g.reward ? g.reward.total_score     : null,
        lab_score:       g.reward ? g.reward.lab_score       : null,
        answer_score:    g.reward ? g.reward.answer_score    : null,
        R_core:          g.reward ? g.reward.R_core          : null,
        R_justification: g.reward ? g.reward.R_justification : null,
        n_labs:          run.trajectory.lab_requests.length,
        trajectory:      run.trajectory,
        reward:          g.reward,
        critique:        g.critique,
      }))
      .catch(err => {
        log(`FAILED: supervisor case=${run.case_id} condition=${run.condition} — ${err.message}`)
        return null
      })
  )
)

const gradedValid = gradedRuns.filter(Boolean)
log(`${gradedValid.length}/${validAnswers.length} grading runs completed`)

// ─── Phase 2: Compare ─────────────────────────────────────────────────────────

phase('Compare')

const rows = gradedValid
  .sort((a, b) => a.case_id - b.case_id || a.condition.localeCompare(b.condition))
  .map(r => ({
    case_id:      r.case_id,
    patient_id:   r.patient_id,
    condition:    r.condition,
    total_score:  r.total_score  !== null ? r.total_score.toFixed(3)  : 'n/a',
    lab_score:    r.lab_score    !== null ? r.lab_score.toFixed(3)    : 'n/a',
    answer_score: r.answer_score !== null ? r.answer_score.toFixed(3) : 'n/a',
    n_labs:       r.n_labs,
  }))

log('\n=== SCORE COMPARISON TABLE ===')
log('case | patient    | condition       | total  | lab    | answer | labs_n')
log('-----|------------|-----------------|--------|--------|--------|-------')
for (const row of rows) {
  const cond = row.condition.padEnd(15)
  const pid  = row.patient_id.padEnd(10)
  log(`  ${row.case_id}  | ${pid} | ${cond} | ${row.total_score}/1.70 | ${row.lab_score}/0.70 | ${row.answer_score}/1.00 | ${row.n_labs}`)
}

return {
  experiment: {
    conditions: _conditions,
    case_ids:   _case_ids,
    n_completed: gradedValid.length,
    n_total:     totalRuns,
  },
  results: rows,
  raw: gradedValid,
}
