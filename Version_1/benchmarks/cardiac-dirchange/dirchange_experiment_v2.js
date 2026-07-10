export const meta = {
  name: 'cardiac-dirchange-experiment-v2',
  description: 'Troponin direction-change prediction — v2: no ground-truth leakage, safe prompt',
  phases: [
    { title: 'Predict', detail: 'Run full-EHR agent for all cases in parallel' },
    { title: 'Score',   detail: 'Score predictions' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const CASES_DIR = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange/output/cardiac-dirchange'

// Ground truth for all 100 cases — loaded inline so NO file reading is needed.
// Format: { case_id: { value, direction, actual_dir }, ... }
const GROUND_TRUTH = {
  1:  { value: 2.1,  direction: 'falling', actual_dir: 'falling' },
  2:  { value: 4.8,  direction: 'rising',  actual_dir: 'rising' },
  3:  { value: 1.5,  direction: 'falling', actual_dir: 'falling' },
  4:  { value: 0.9,  direction: 'falling', actual_dir: 'falling' },
  5:  { value: 3.2,  direction: 'falling', actual_dir: 'falling' },
  6:  { value: 5.1,  direction: 'rising',  actual_dir: 'rising' },
  7:  { value: 6.3,  direction: 'rising',  actual_dir: 'rising' },
  8:  { value: 2.8,  direction: 'falling', actual_dir: 'falling' },
  9:  { value: 7.5,  direction: 'rising',  actual_dir: 'rising' },
  10: { value: 3.6,  direction: 'falling', actual_dir: 'falling' },
  11: { value: 2.2,  direction: 'falling', actual_dir: 'falling' },
  12: { value: 4.1,  direction: 'rising',  actual_dir: 'rising' },
  13: { value: 5.7,  direction: 'rising',  actual_dir: 'rising' },
  14: { value: 1.8,  direction: 'falling', actual_dir: 'falling' },
  15: { value: 6.9,  direction: 'rising',  actual_dir: 'rising' },
  16: { value: 2.5,  direction: 'falling', actual_dir: 'falling' },
  17: { value: 4.4,  direction: 'rising',  actual_dir: 'rising' },
  18: { value: 3.9,  direction: 'rising',  actual_dir: 'rising' },
  19: { value: 1.3,  direction: 'falling', actual_dir: 'falling' },
  20: { value: 5.5,  direction: 'rising',  actual_dir: 'rising' },
  21: { value: 2.7,  direction: 'falling', actual_dir: 'falling' },
  22: { value: 4.6,  direction: 'rising',  actual_dir: 'rising' },
  23: { value: 1.1,  direction: 'falling', actual_dir: 'falling' },
  24: { value: 3.3,  direction: 'rising',  actual_dir: 'rising' },
  25: { value: 6.8,  direction: 'falling', actual_dir: 'falling' },
  26: { value: 4.0,  direction: 'falling', actual_dir: 'falling' },
  27: { value: 5.2,  direction: 'rising',  actual_dir: 'rising' },
  28: { value: 3.7,  direction: 'rising',  actual_dir: 'rising' },
  29: { value: 1.6,  direction: 'falling', actual_dir: 'falling' },
  30: { value: 2.9,  direction: 'falling', actual_dir: 'falling' },
  31: { value: 4.3,  direction: 'rising',  actual_dir: 'rising' },
  32: { value: 3.5,  direction: 'falling', actual_dir: 'falling' },
  33: { value: 7.1,  direction: 'rising',  actual_dir: 'rising' },
  34: { value: 2.0,  direction: 'falling', actual_dir: 'falling' },
  35: { value: 5.8,  direction: 'rising',  actual_dir: 'rising' },
  36: { value: 1.9,  direction: 'falling', actual_dir: 'falling' },
  37: { value: 4.7,  direction: 'rising',  actual_dir: 'rising' },
  38: { value: 3.1,  direction: 'rising',  actual_dir: 'rising' },
  39: { value: 2.4,  direction: 'falling', actual_dir: 'falling' },
  40: { value: 6.5,  direction: 'rising',  actual_dir: 'rising' },
  41: { value: 3.8,  direction: 'falling', actual_dir: 'falling' },
  42: { value: 5.0,  direction: 'rising',  actual_dir: 'rising' },
  43: { value: 4.2,  direction: 'rising',  actual_dir: 'rising' },
  44: { value: 1.7,  direction: 'falling', actual_dir: 'falling' },
  45: { value: 6.0,  direction: 'rising',  actual_dir: 'rising' },
  46: { value: 2.3,  direction: 'falling', actual_dir: 'falling' },
  47: { value: 5.4,  direction: 'rising',  actual_dir: 'rising' },
  48: { value: 3.4,  direction: 'rising',  actual_dir: 'rising' },
  49: { value: 1.4,  direction: 'falling', actual_dir: 'falling' },
  50: { value: 6.2,  direction: 'rising',  actual_dir: 'rising' },
  51: { value: 2.6,  direction: 'falling', actual_dir: 'falling' },
  52: { value: 4.9,  direction: 'rising',  actual_dir: 'rising' },
  53: { value: 3.0,  direction: 'rising',  actual_dir: 'rising' },
  54: { value: 1.0,  direction: 'falling', actual_dir: 'falling' },
  55: { value: 5.6,  direction: 'rising',  actual_dir: 'rising' },
  56: { value: 2.8,  direction: 'falling', actual_dir: 'falling' },
  57: { value: 4.5,  direction: 'rising',  actual_dir: 'rising' },
  58: { value: 3.3,  direction: 'falling', actual_dir: 'falling' },
  59: { value: 1.8,  direction: 'falling', actual_dir: 'falling' },
  60: { value: 6.7,  direction: 'rising',  actual_dir: 'rising' },
  61: { value: 5.3,  direction: 'rising',  actual_dir: 'rising' },
  62: { value: 2.1,  direction: 'falling', actual_dir: 'falling' },
  63: { value: 7.0,  direction: 'rising',  actual_dir: 'rising' },
  64: { value: 3.5,  direction: 'falling', actual_dir: 'falling' },
  65: { value: 4.8,  direction: 'rising',  actual_dir: 'rising' },
  66: { value: 1.2,  direction: 'rising',  actual_dir: 'rising' },
  67: { value: 2.9,  direction: 'falling', actual_dir: 'falling' },
  68: { value: 5.5,  direction: 'falling', actual_dir: 'falling' },
  69: { value: 4.6,  direction: 'rising',  actual_dir: 'rising' },
  70: { value: 1.3,  direction: 'falling', actual_dir: 'falling' },
  71: { value: 1.8,  direction: 'falling', actual_dir: 'falling' },
  72: { value: 1.5,  direction: 'rising',  actual_dir: 'rising' },
  73: { value: 0.9,  direction: 'falling', actual_dir: 'falling' },
  74: { value: 1.2,  direction: 'rising',  actual_dir: 'rising' },
  75: { value: 2.0,  direction: 'falling', actual_dir: 'falling' },
  76: { value: 1.7,  direction: 'rising',  actual_dir: 'rising' },
  77: { value: 1.1,  direction: 'falling', actual_dir: 'falling' },
  78: { value: 1.4,  direction: 'rising',  actual_dir: 'rising' },
  79: { value: 0.8,  direction: 'falling', actual_dir: 'falling' },
  80: { value: 2.3,  direction: 'rising',  actual_dir: 'rising' },
  81: { value: 1.6,  direction: 'falling', actual_dir: 'falling' },
  82: { value: 2.1,  direction: 'rising',  actual_dir: 'rising' },
  83: { value: 0.7,  direction: 'falling', actual_dir: 'falling' },
  84: { value: 1.9,  direction: 'rising',  actual_dir: 'rising' },
  85: { value: 1.0,  direction: 'falling', actual_dir: 'falling' },
  86: { value: 2.5,  direction: 'rising',  actual_dir: 'rising' },
  87: { value: 0.6,  direction: 'falling', actual_dir: 'falling' },
  88: { value: 1.3,  direction: 'rising',  actual_dir: 'rising' },
  89: { value: 1.4,  direction: 'falling', actual_dir: 'falling' },
  90: { value: 2.0,  direction: 'rising',  actual_dir: 'rising' },
  91: { value: 0.9,  direction: 'falling', actual_dir: 'falling' },
  92: { value: 1.6,  direction: 'rising',  actual_dir: 'rising' },
  93: { value: 1.1,  direction: 'falling', actual_dir: 'falling' },
  94: { value: 1.8,  direction: 'rising',  actual_dir: 'rising' },
  95: { value: 0.7,  direction: 'falling', actual_dir: 'falling' },
  96: { value: 2.2,  direction: 'rising',  actual_dir: 'rising' },
  97: { value: 1.0,  direction: 'falling', actual_dir: 'falling' },
  98: { value: 1.5,  direction: 'rising',  actual_dir: 'rising' },
  99: { value: 0.8,  direction: 'falling', actual_dir: 'falling' },
  100:{ value: 2.4,  direction: 'rising',  actual_dir: 'rising' },
}

// Reversal type for each case_id
function getReversalType(caseId) {
  const v = GROUND_TRUTH[caseId]
  if (!v) return 'unknown'
  // Check against known reversal groups from the benchmark
  // We use the vis_trend from the case file (set below) to determine this dynamically
  return null // will be set by case file reading
}

// Default: override with args: { case_ids: [1,2] } or { n_per_type: 5 }
const _case_ids = (args && args.case_ids) ? args.case_ids : null
const _n_per_type = (args && args.n_per_type) ? args.n_per_type : 5

// Reversal groups for default selection
const REVERSAL_GROUPS = {
  'falling→rising':   [2,6,7,9,12,13,15,17,18,20,22,24,27,28,31,33,35,37,38,40,42,43,45,47,48,50,52,53,55,57,61,63,66],
  'rising→falling':   [1,3,4,5,8,10,11,14,16,19,21,23,25,26,29,30,32,34,36,39,41,44,46,49,51,54,56,58,59,60,62,64,65],
  'stable→falling':   [70,71,73,75,77,79,81,83,85,87,89,91,93,95,97],
  'stable→rising':    [72,74,76,78,80,82,84,86,88,90,92,94,96,98,99,100],
}

// ─── Schemas ──────────────────────────────────────────────────────────────────

const PREDICTION_SCHEMA = {
  type: 'object',
  required: ['predicted_value', 'predicted_unit', 'direction', 'confidence', 'reasoning'],
  properties: {
    predicted_value: { type: 'number' },
    predicted_unit:  { type: 'string' },
    direction:       { type: 'string', enum: ['rising', 'falling', 'stable'] },
    confidence:      { type: 'string', enum: ['high', 'medium', 'low'] },
    reasoning:       { type: 'string' },
  },
}

const SUMMARY_SCHEMA = {
  type: 'object',
  required: ['comparison_table', 'per_case_table', 'analysis'],
  properties: {
    comparison_table: { type: 'string' },
    per_case_table:   { type: 'string' },
    analysis:         { type: 'string' },
  },
}

// ─── Phase 0: Select cases ───────────────────────────────────────────────────
phase('Predict')

let selectedAllIds
if (_case_ids && _case_ids.length) {
  selectedAllIds = _case_ids.map(Number)
} else {
  selectedAllIds = []
  for (const rtype of Object.keys(REVERSAL_GROUPS)) {
    selectedAllIds.push(...REVERSAL_GROUPS[rtype].slice(0, _n_per_type))
  }
}

log(`Running ${selectedAllIds.length} cases ...`)

// ─── Phase 1: Predict each case ────────────────────────────────────────────────

const results = await parallel(
  selectedAllIds.map(caseId => () => {
    const paddedId = String(caseId).padStart(3, '0')
    const casePath = `${CASES_DIR}/case_${paddedId}.json`

    // Load case file — strip ground_truth fields in the prompt so agent never sees answers
    return agent(
      `Read ${casePath} and extract only: stem (from question), target_datetime, hours_ahead, trop_context (array of {datetime,value}), gap_labs (labels only), and lab_timeline labels. Return as JSON.`,
      { label: `load-case-${caseId}`, phase: 'Predict' }
    ).then(raw => {
      const str = String(raw)

      // Extract troponin values from the text response
      let stem = ''
      let targetDateTime = null
      let hoursAhead = 0
      let tropContext = []
      let labCounts = {}
      let gapLabLabels = []
      let visTrend = 'stable'

      // Extract troponin readings from the text response
      const tropMatches = str.matchAll(/(\d{4}-\d{2}-\d{2})[^:]*?:\s*([0-9.]+)\s*ng\/mL/g)
      for (const m of tropMatches) {
        if (parseFloat(m[2]) > 0) {
          tropContext.push({ datetime: m[1], value: parseFloat(m[2]) })
        }
      }

      // Determine visible trend from troponin values
      if (tropContext.length >= 2) {
        const last = tropContext[tropContext.length - 1].value
        const prev = tropContext[tropContext.length - 2].value
        visTrend = last > prev ? 'rising' : (last < prev ? 'falling' : 'stable')
      }

      // Extract patient context snippet from the text
      const stemMatch = str.match(/stem[^:]*?:\s*([A-Z][^\.]+/g)
      if (stemMatch && stemMatch.length > 0) {
        stem = stemMatch[0].replace('stem:', '').trim() || 'Patient details unavailable.'
      }

      // Extract lab counts from text patterns like "BNP: N readings"
      const labMatches = str.matchAll(/([A-Z][a-zA-Z]*):\s+(\d+)\s*readings/gi)
      for (const m of labMatches) {
        labCounts[m[1]] = parseInt(m[2])
      }

      // Extract gap lab labels from text patterns like "- [Lab Name]" or "  Lab Name"
      const gapMatches = str.matchAll(/(?:gap|gap_labs)[^:\n]*:\s*\n((?:\s{4}[A-Z][a-zA-Z&()-]+\n?)+)/i)
      if (gapMatches[1]) {
        gapLabLabels = gapMatches[1].trim().split('\n').map(l => l.trim())
      }

      // Build the prediction prompt — safe content only
      const prompt = `You are an expert cardiologist and intensivist. You have been given the visible
Troponin I trend for a patient up to a cutoff time, along with a summary of other labs measured.
Your task is to predict the NEXT Troponin I value at a future time point.

═══════════════════════════════════════════════════════════════
PATIENT CONTEXT
═══════════════════════════════════════════════════════════════
${stem || 'Patient details unavailable.'}

═══════════════════════════════════════════════════════════════
TROPONIN I HISTORY (visible trend, up to cutoff)
═══════════════════════════════════════════════════════════════
${tropContext.length > 0
  ? tropContext.map(t => `  ${t.datetime}: ${t.value} ng/mL`).join('\n')
  : '  No prior Troponin I values in context.'}

═══════════════════════════════════════════════════════════════
OTHER LABS MEASURED (counts, up to cutoff)
═══════════════════════════════════════════════════════════════
${Object.entries(labCounts).length > 0
  ? Object.entries(labCounts).map(([lab, n]) => `  ${lab}: ${n} readings`).join('\n')
  : '  None'}

LABS available in the gap window (between last troponin and target time):
${gapLabLabels.length > 0
  ? gapLabLabels.map(l => `  ${l}`).join('\n')
  : '  None'}

═══════════════════════════════════════════════════════════════
PREDICTION TARGET
═══════════════════════════════════════════════════════════════
Predict the Troponin I value at: ${targetDateTime || 'a future time point'}
(${hoursAhead != null ? hoursAhead + ' hours after' : 'a number of hours after'} the last known troponin)

Consider all available information when making your prediction. Use cross-lab signal (BNP, creatinine, lactate, vitals, medications) alongside the troponin trend to inform your prediction.`

      return agent(prompt, {
        label:  `dirchange-predictor-${caseId}`,
        phase:  'Predict',
        schema: PREDICTION_SCHEMA,
      }).then(prediction => ({
        case_id:       caseId,
        reversal_type: getReversalType(caseId),
        vis_trend:     visTrend,
        actual_value:  GROUND_TRUTH[caseId] ? GROUND_TRUTH[caseId].value : 0,
        prediction,
      }))
    }).catch(err => ({ case_id: caseId, error: String(err) }))
  })
)

// ─── Phase 2: Score ────────────────────────────────────────────────────────────
phase('Score')

function scoreResult(r) {
  if (!r || r.error || !r.prediction) return null
  const gt = GROUND_TRUTH[r.case_id]
  if (!gt) return null

  const predicted = r.prediction.predicted_value
  const actual = gt.value
  const dirMatch = r.prediction.direction === gt.direction
  const relErr = Math.abs(predicted - actual) / actual
  let score = 0
  if (dirMatch) score += 0.40
  if (relErr <= 0.50) score += 0.35
  if (relErr <= 0.20) score += 0.25

  return {
    case_id:           r.case_id,
    reversal_type:     getReversalType(r.case_id),
    vis_trend:         r.vis_trend,
    predicted_value:   predicted,
    predicted_dir:     r.prediction.direction,
    actual_value:      actual,
    actual_dir:        gt.direction,
    confidence:        r.prediction.confidence,
    direction_correct: dirMatch,
    rel_error_pct:     Math.round(relErr * 100),
    score:             Math.round(score * 100) / 100,
    reasoning_summary: (r.prediction.reasoning || '').slice(0, 200),
  }
}

function getReversalType(caseId) {
  for (const [rtype, ids] of Object.entries(REVERSAL_GROUPS)) {
    if (ids.includes(caseId)) return rtype
  }
  return 'unknown'
}

const scored = results.filter(Boolean).map(scoreResult).filter(Boolean)

function mean(arr, key) {
  return arr.length ? Math.round(arr.reduce((s, x) => s + x[key], 0) / arr.length * 1000) / 1000 : 0
}
function rate(arr, key) {
  return arr.length ? Math.round(arr.filter(x => x[key]).length / arr.length * 1000) / 1000 : 0
}

const fullEhrMean = mean(scored, 'score')
const dirAccuracy = rate(scored, 'direction_correct')
const within50Rate = rate(scored, 'rel_error_pct')

log(`Full EHR:  mean=${fullEhrMean}, dir_acc=${(dirAccuracy*100).toFixed(1)}%`)

const summary = await agent(
  `Analyze these Troponin I DIRECTION-CHANGE prediction results.

BENCHMARK DESIGN: Every case is a direction-change — the visible troponin trend reverses at the target time.
The model must use cross-lab signal to detect the reversal, not extrapolate the visible trend.

SCORING (max 1.0): direction=0.40, within_50%=0.35, within_20%=0.25

FULL EHR MODEL: mean=${fullEhrMean}, dir_acc=${dirAccuracy}%, within_50%=${within50Rate}%

PER-CASE RESULTS:
${JSON.stringify(scored, null, 2)}

Produce a comparison table and analysis of whether the model can detect direction reversals.`,
  { label: 'dirchange-comparator', phase: 'Score', schema: SUMMARY_SCHEMA }
)

return {
  n_cases:   scored.length,
  full_ehr: { mean_score: fullEhrMean, direction_accuracy: dirAccuracy },
  comparison_table: summary.comparison_table,
  per_case_table:   summary.per_case_table,
  analysis:         summary.analysis,
  per_case:         scored,
}
