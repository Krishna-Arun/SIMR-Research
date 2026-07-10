export const meta = {
  name: 'cardiac-dirchange-v2-pubmed-experiment',
  description: 'Compare Troponin I prediction with vs without PubMed MCP access across 100 direction-reversal cases (v2)',
  phases: [
    { title: 'Predict', detail: 'Run both conditions (with/without PubMed) for every case' },
    { title: 'Score',   detail: 'Score each prediction and compare conditions' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const AGENT_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/nextlab_answer_agent.js'
const OUTPUT_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/output/dirchange_v2_pubmed_results.json'

// All 100 cases
const _case_ids = (args && args.case_ids) ? args.case_ids
  : Array.from({ length: 100 }, (_, i) => i + 1)

// ─── Phase 1: Predict all cases × both conditions ─────────────────────────────
phase('Predict')
log(`Running ${_case_ids.length} cases × 2 conditions = ${_case_ids.length * 2} predictions ...`)

const allResults = await pipeline(
  _case_ids,
  case_id => parallel([
    () => workflow({ scriptPath: AGENT_PATH }, { case_id, condition: 'without_pubmed' })
           .then(r => ({ ...r, condition: 'without_pubmed' }))
           .catch(err => ({ case_id, condition: 'without_pubmed', error: String(err) })),
    () => workflow({ scriptPath: AGENT_PATH }, { case_id, condition: 'with_pubmed' })
           .then(r => ({ ...r, condition: 'with_pubmed' }))
           .catch(err => ({ case_id, condition: 'with_pubmed', error: String(err) })),
  ]).then(([without, with_]) => ({ case_id, without_pubmed: without, with_pubmed: with_ }))
)

// ─── Phase 2: Score ───────────────────────────────────────────────────────────
phase('Score')

function scoreResult(r) {
  if (!r || r.error || !r.prediction || !r.ground_truth) return null
  const pred    = r.prediction
  const actual  = r.ground_truth.value
  const predicted = pred.predicted_value

  let score = 0
  const directionMatch = pred.direction === r.ground_truth.direction
  score += directionMatch ? 0.40 : 0.0

  const relError = actual > 0 ? Math.abs(predicted - actual) / actual : 1.0
  const within50 = relError <= 0.50
  const within20 = relError <= 0.20
  score += within50 ? 0.35 : 0.0
  score += within20 ? 0.25 : 0.0

  return {
    case_id:            r.case_id,
    patient_id:         r.patient_id,
    condition:          r.condition,
    predicted_value:    predicted,
    predicted_dir:      pred.direction,
    actual_value:       actual,
    actual_dir:         r.ground_truth.direction,
    confidence:         pred.confidence,
    direction_correct:  directionMatch,
    relative_error_pct: Math.round(relError * 100),
    within_50pct:       within50,
    within_20pct:       within20,
    score:              Math.round(score * 100) / 100,
  }
}

const scored = allResults
  .filter(Boolean)
  .flatMap(pair => [scoreResult(pair.without_pubmed), scoreResult(pair.with_pubmed)])
  .filter(Boolean)

const withoutScores = scored.filter(s => s.condition === 'without_pubmed')
const withScores    = scored.filter(s => s.condition === 'with_pubmed')

function mean(arr, key) {
  return arr.length ? arr.reduce((s, x) => s + x[key], 0) / arr.length : 0
}
function rate(arr, key) {
  return arr.length ? arr.filter(x => x[key]).length / arr.length : 0
}

const summary = {
  without_pubmed: {
    mean_score:         Math.round(mean(withoutScores, 'score') * 1000) / 1000,
    direction_accuracy: Math.round(rate(withoutScores, 'direction_correct') * 1000) / 1000,
    within_50pct_rate:  Math.round(rate(withoutScores, 'within_50pct') * 1000) / 1000,
    within_20pct_rate:  Math.round(rate(withoutScores, 'within_20pct') * 1000) / 1000,
  },
  with_pubmed: {
    mean_score:         Math.round(mean(withScores, 'score') * 1000) / 1000,
    direction_accuracy: Math.round(rate(withScores, 'direction_correct') * 1000) / 1000,
    within_50pct_rate:  Math.round(rate(withScores, 'within_50pct') * 1000) / 1000,
    within_20pct_rate:  Math.round(rate(withScores, 'within_20pct') * 1000) / 1000,
  },
}

log(`without_pubmed: mean=${summary.without_pubmed.mean_score}, dir_acc=${(summary.without_pubmed.direction_accuracy*100).toFixed(1)}%`)
log(`with_pubmed:    mean=${summary.with_pubmed.mean_score}, dir_acc=${(summary.with_pubmed.direction_accuracy*100).toFixed(1)}%`)

// ─── Comparison summary agent ─────────────────────────────────────────────────
const COMPARE_SCHEMA = {
  type: 'object',
  required: ['comparison_table', 'per_case_table', 'analysis'],
  properties: {
    comparison_table: { type: 'string' },
    per_case_table:   { type: 'string' },
    analysis:         { type: 'string' },
  },
}

const comparison = await agent(
  `Analyze these Troponin I prediction results comparing two conditions on the direction-reversal benchmark (v2):
  1. without_pubmed — no external tools available; agent must reason from provided lab data only
  2. with_pubmed    — identical prompt and data, but agent is told it has PubMed MCP access and may search

SCORING (max 1.0): direction=0.40, within_50pct=0.35, within_20pct=0.25
Design note: every case has a visible troponin trend that REVERSES at the target time, making both last-value and trend-extrapolation heuristics wrong by construction. Agents must use cross-lab signals to detect the reversal.

AGGREGATE:
${JSON.stringify(summary, null, 2)}

PER-CASE:
${JSON.stringify(scored, null, 2)}

Produce:
1. comparison_table — markdown: Metric | without_pubmed | with_pubmed | Delta
2. per_case_table   — markdown: Case | True Dir | without (dir, score) | with (dir, score) | Winner
3. analysis         — 4-6 sentences on: Did PubMed access change performance? The direction-reversal design tests whether agents use cross-lab signals rather than troponin trend extrapolation. Does PubMed help or hurt here? Could it introduce distraction from the actual clinical data?`,
  { label: 'condition-comparator', phase: 'Score', schema: COMPARE_SCHEMA }
)

// ─── Save results to file ─────────────────────────────────────────────────────
const fs = await import('fs')
const resultsOutput = {
  benchmark: 'cardiac-dirchange-v2-pubmed-ablation',
  n_cases: _case_ids.length,
  summary,
  comparison_table: comparison.comparison_table,
  per_case_table: comparison.per_case_table,
  analysis: comparison.analysis,
  per_case: scored,
}
fs.writeFileSync(OUTPUT_PATH, JSON.stringify(resultsOutput, null, 2))
log(`Results saved to ${OUTPUT_PATH}`)

return resultsOutput
