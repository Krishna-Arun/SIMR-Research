export const meta = {
  name: 'cardiac-dirchange-v2-experiment',
  description: 'Run direction-change Troponin I prediction across all cases and score each (nextlab format)',
  phases: [
    { title: 'Predict', detail: 'Run nextlab_answer_agent.js for each direction-change case in parallel' },
    { title: 'Score',   detail: 'Compute direction accuracy and value error per reversal type' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const NEXTLAB_AGENT_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/nextlab_answer_agent.js'
const BENCHMARK_PATH     = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/output/cardiac_dirchange_v2_benchmark_v1.json'

// ─── Load benchmark to get case count ────────────────────────────────────────
phase('Predict')

const MANIFEST_SCHEMA = {
  type: 'object',
  required: ['n_cases', 'cases'],
  properties: {
    n_cases: { type: 'number' },
    cases: {
      type: 'array',
      items: {
        type: 'object',
        required: ['case_id', 'reversal_type'],
        properties: {
          case_id:      { type: 'number' },
          reversal_type: { type: 'string' },
        },
      },
    },
  },
}

const manifest = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Return an object with:
  n_cases: the value of the top-level "n_cases" field
  cases: an array of objects, one per case, each with case_id and reversal_type fields only.`,
  { label: 'manifest-loader', phase: 'Predict', schema: MANIFEST_SCHEMA }
)

// Allow args to override which cases to run: { case_ids: [1, 2, 3] }
const _case_ids = (args && args.case_ids)
  ? args.case_ids
  : manifest.cases.map(c => c.case_id)

// Build a lookup: case_id → reversal_type
const reversalTypeMap = {}
for (const c of manifest.cases) reversalTypeMap[c.case_id] = c.reversal_type

log(`Running ${_case_ids.length} direction-change cases ...`)

// ─── Phase 1: Predict all cases in parallel ───────────────────────────────────
const results = await parallel(
  _case_ids.map(case_id => () =>
    workflow({ scriptPath: NEXTLAB_AGENT_PATH }, { case_id })
      .then(r => ({ case_id, reversal_type: reversalTypeMap[case_id] || 'unknown', ...r }))
      .catch(err => ({ case_id, reversal_type: reversalTypeMap[case_id] || 'unknown', error: String(err) }))
  )
)

// ─── Phase 2: Score ───────────────────────────────────────────────────────────
phase('Score')

function scoreCase(r) {
  if (r.error || !r.prediction || !r.ground_truth) return null

  const pred      = r.prediction
  const truth     = r.ground_truth
  const actual    = truth.value
  const predicted = pred.predicted_value

  let score = 0
  let breakdown = {}

  // Direction score (0.40) — checks reversed direction, not visible trend
  const directionMatch = pred.direction === truth.direction
  breakdown.direction_correct = directionMatch
  breakdown.direction_score   = directionMatch ? 0.40 : 0.0
  score += breakdown.direction_score

  // Value error
  const relError = actual > 0 ? Math.abs(predicted - actual) / actual : 1.0
  breakdown.relative_error_pct = Math.round(relError * 100)

  // Within 50% (0.35)
  const within50 = relError <= 0.50
  breakdown.within_50pct       = within50
  breakdown.within_50pct_score = within50 ? 0.35 : 0.0
  score += breakdown.within_50pct_score

  // Within 20% (0.25)
  const within20 = relError <= 0.20
  breakdown.within_20pct       = within20
  breakdown.within_20pct_score = within20 ? 0.25 : 0.0
  score += breakdown.within_20pct_score

  breakdown.total_score = Math.round(score * 100) / 100

  return {
    case_id:          r.case_id,
    patient_id:       r.patient_id,
    reversal_type:    r.reversal_type,
    visible_trend:    truth.visible_trend || r.reversal_type?.split('→')[0] || '',
    predicted_value:  predicted,
    predicted_dir:    pred.direction,
    actual_value:     actual,
    actual_dir:       truth.direction,
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
    summary_table:      { type: 'string' },
    mean_score:         { type: 'number' },
    direction_accuracy: { type: 'number' },
    within_50pct_rate:  { type: 'number' },
    within_20pct_rate:  { type: 'number' },
    analysis:           { type: 'string' },
  },
}

const summary = await agent(
  `Compute summary statistics for these ${scored.length} cardiac direction-change Troponin I prediction results.

CONTEXT: This is a DIRECTION-CHANGE benchmark — every case has a visible troponin trend that REVERSES at
the target time. Both last-value and trend-extrapolation heuristics fail by construction. A model that
detects the reversal must use cross-lab signals (BNP, creatinine, etc.) available in the gap window.

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
    Case | Patient | Reversal Type | Vis Trend | Pred Dir | True Dir | Dir✓ | Err% | Score

  analysis = 4-6 sentences interpreting the results specifically for direction-change cases:
    - What is the overall direction accuracy vs. the random baseline (~33%)?
    - Which reversal types does the model detect best (falling→rising vs rising→falling vs stable→X)?
    - Does the model show rising-bias (over-predicts rising regardless of actual direction)?
    - What cross-lab patterns might explain correct vs. incorrect predictions?`,
  { label: 'results-summarizer', phase: 'Score', schema: SCORER_SCHEMA }
)

log(`Mean score: ${summary.mean_score.toFixed(3)}`)
log(`Direction accuracy: ${(summary.direction_accuracy * 100).toFixed(1)}%  (random baseline ~33%)`)
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
