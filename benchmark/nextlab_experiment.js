export const meta = {
  name: 'cardiac-nextlab-experiment',
  description: 'Run Troponin I next-value prediction across all 20 cardiac cases and score each',
  phases: [
    { title: 'Predict', detail: 'Run nextlab_answer_agent.js for each case in parallel' },
    { title: 'Score',   detail: 'Compute direction accuracy and value error for each case' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const NEXTLAB_AGENT_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/nextlab_answer_agent.js'
const BENCHMARK_PATH     = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/output/cardiac_nextlab_benchmark_v1.json'

// Override with args if provided: { case_ids: [1, 2, 3] }
const _case_ids = (args && args.case_ids) ? args.case_ids : [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]

// ─── Phase 0: Load n_cases from benchmark ────────────────────────────────────
phase('Predict')
log(`Running ${_case_ids.length} cases ...`)

// ─── Phase 1: Predict all cases in parallel ───────────────────────────────────
const results = await parallel(
  _case_ids.map(case_id => () =>
    workflow({ scriptPath: NEXTLAB_AGENT_PATH }, { case_id })
      .then(r => ({ case_id, ...r }))
      .catch(err => ({ case_id, error: String(err) }))
  )
)

// ─── Phase 2: Score ───────────────────────────────────────────────────────────
phase('Score')

function scoreCase(r) {
  if (r.error || !r.prediction || !r.ground_truth) return null

  const pred   = r.prediction
  const truth  = r.ground_truth
  const actual = truth.value
  const predicted = pred.predicted_value

  let score = 0
  let breakdown = {}

  // Direction score (0.40)
  const directionMatch = pred.direction === truth.direction
  breakdown.direction_correct = directionMatch
  breakdown.direction_score   = directionMatch ? 0.40 : 0.0
  score += breakdown.direction_score

  // Value error
  const relError = actual > 0 ? Math.abs(predicted - actual) / actual : 1.0
  breakdown.relative_error_pct = Math.round(relError * 100)

  // Within 50% (0.35)
  const within50 = relError <= 0.50
  breakdown.within_50pct = within50
  breakdown.within_50pct_score = within50 ? 0.35 : 0.0
  score += breakdown.within_50pct_score

  // Within 20% (0.25)
  const within20 = relError <= 0.20
  breakdown.within_20pct = within20
  breakdown.within_20pct_score = within20 ? 0.25 : 0.0
  score += breakdown.within_20pct_score

  breakdown.total_score = Math.round(score * 100) / 100

  return {
    case_id:          r.case_id,
    patient_id:       r.patient_id,
    predicted_value:  predicted,
    predicted_dir:    pred.direction,
    actual_value:     actual,
    actual_dir:       truth.direction,
    hours_ahead:      r.ground_truth ? null : null,
    confidence:       pred.confidence,
    score:            breakdown.total_score,
    breakdown,
    reasoning_summary: pred.reasoning ? pred.reasoning.slice(0, 120) + '...' : '',
  }
}

const scored = results.filter(Boolean).map(scoreCase).filter(Boolean)

// ─── Summary stats ────────────────────────────────────────────────────────────
const SCORER_SCHEMA = {
  type: 'object',
  required: ['summary_table', 'mean_score', 'direction_accuracy', 'within_50pct_rate', 'within_20pct_rate', 'analysis'],
  properties: {
    summary_table:     { type: 'string' },
    mean_score:        { type: 'number' },
    direction_accuracy:{ type: 'number' },
    within_50pct_rate: { type: 'number' },
    within_20pct_rate: { type: 'number' },
    analysis:          { type: 'string' },
  },
}

const summary = await agent(
  `Compute summary statistics for these ${scored.length} cardiac next-Troponin-I prediction results and produce a readable report.

SCORING FORMULA (max 1.0 per case):
  direction_correct = 0.40  (rising/falling/stable, ±20% boundary)
  within_50pct      = 0.35  (|predicted - actual| / actual ≤ 0.50)
  within_20pct      = 0.25  (|predicted - actual| / actual ≤ 0.20)

RESULTS:
${JSON.stringify(scored, null, 2)}

Compute:
  mean_score         = average total_score across all cases
  direction_accuracy = fraction where direction_correct == true
  within_50pct_rate  = fraction where within_50pct == true
  within_20pct_rate  = fraction where within_20pct == true

  summary_table = a markdown table with columns:
    Case | Patient | Predicted | Actual | Pred Dir | True Dir | Dir✓ | Err% | Score

  analysis = 3-5 sentences interpreting the results: where does the model succeed
  (e.g., "rising" cases) and where does it fail (e.g., "falling" cases, large outliers).`,
  { label: 'results-summarizer', phase: 'Score', schema: SCORER_SCHEMA }
)

log(`Mean score: ${summary.mean_score.toFixed(3)}`)
log(`Direction accuracy: ${(summary.direction_accuracy * 100).toFixed(1)}%`)
log(`Within 50% error: ${(summary.within_50pct_rate * 100).toFixed(1)}%`)
log(`Within 20% error: ${(summary.within_20pct_rate * 100).toFixed(1)}%`)

return {
  n_cases:            scored.length,
  mean_score:         summary.mean_score,
  direction_accuracy: summary.direction_accuracy,
  within_50pct_rate:  summary.within_50pct_rate,
  within_20pct_rate:  summary.within_20pct_rate,
  summary_table:      summary.summary_table,
  analysis:           summary.analysis,
  per_case:           scored,
}
