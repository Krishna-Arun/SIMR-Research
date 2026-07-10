export const meta = {
  name: 'cardiac-dirchange-experiment',
  description: 'Troponin direction-change prediction — visible trend reverses at target time',
  phases: [
    { title: 'Predict', detail: 'Run full-EHR agent for all cases in parallel' },
    { title: 'Score',   detail: 'Score predictions, compare vs trend-extrapolation baseline' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const MANIFEST_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange/output/cardiac_dirchange_benchmark_v1.json'
const CASES_DIR     = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange/output/cardiac-dirchange'

const _case_ids = (args && args.case_ids) ? args.case_ids : null
const _n_cases  = (args && args.n_cases)  ? args.n_cases  : 20

// ─── Schemas ──────────────────────────────────────────────────────────────────
const CASES_SCHEMA = {
  type: 'object',
  required: ['cases'],
  properties: { cases: { type: 'array' } },
}

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

// ─── Phase 0: Load manifest then case files ───────────────────────────────────
phase('Predict')

const manifest = await agent(
  `Read the JSON file at ${MANIFEST_PATH}. Return the full object including the cases array.`,
  { label: 'load-manifest', phase: 'Predict', schema: CASES_SCHEMA }
)
if (!manifest || !manifest.cases.length) throw new Error('Failed to load manifest')

let selectedMeta = manifest.cases
if (_case_ids) selectedMeta = selectedMeta.filter(c => _case_ids.includes(c.case_id))
else           selectedMeta = selectedMeta.slice(0, _n_cases)

log(`Loading ${selectedMeta.length} case files ...`)

const CASE_SCHEMA = { type: 'object' }

const caseDataList = await parallel(
  selectedMeta.map(m => () => {
    const paddedId = String(m.case_id).padStart(3, '0')
    return agent(
      `Read the JSON file at ${CASES_DIR}/case_${paddedId}.json. Return the full parsed object without truncating any arrays.`,
      { label: `load-${m.case_id}`, phase: 'Predict', schema: CASE_SCHEMA }
    )
  })
)

const loadedCases = caseDataList.filter(Boolean)
log(`Loaded ${loadedCases.length} cases. Running predictions ...`)

// ─── Phase 1: Predict all cases in parallel ───────────────────────────────────
const results = await parallel(
  loadedCases.map(caseData => () => {
    const troponins = caseData.trop_context || []

    const labTableMd = [
      '| Datetime | Lab | Value | Unit |',
      '|---|---|---|---|',
      ...caseData.lab_timeline.map(l =>
        `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} |`
      ),
    ].join('\n')

    const diagMd  = caseData.diagnoses.length
      ? caseData.diagnoses.map(d => `  ${d.date}  ${d.description || d.code}`).join('\n')
      : '  None recorded'
    const medsMd  = caseData.medications.length
      ? caseData.medications.map(m => `  ${m.date}  ${m.name}`).join('\n')
      : '  None recorded'
    const procsMd = caseData.procedures.length
      ? caseData.procedures.map(p => `  ${p.date}  ${p.description || p.code}`).join('\n')
      : '  None recorded'
    const obsMd   = caseData.observations.length
      ? caseData.observations.map(o => `  ${o.date}  ${o.observation}${o.value ? ': ' + o.value : ''}`).join('\n')
      : '  None recorded'
    const visitsMd = caseData.visit_history.length
      ? caseData.visit_history.map(v => `  ${v.date}  ${v.type}`).join('\n')
      : '  None recorded'

    const prompt = `You are an expert cardiologist and intensivist. You have been given the complete
available EHR record for a patient up to a cutoff time. Your task is to predict the NEXT Troponin I value.

═══════════════════════════════════════════════════════════════
PATIENT
═══════════════════════════════════════════════════════════════
${caseData.question.stem}

═══════════════════════════════════════════════════════════════
DIAGNOSIS HISTORY
═══════════════════════════════════════════════════════════════
${diagMd}

═══════════════════════════════════════════════════════════════
MEDICATIONS
═══════════════════════════════════════════════════════════════
${medsMd}

═══════════════════════════════════════════════════════════════
PROCEDURES
═══════════════════════════════════════════════════════════════
${procsMd}

═══════════════════════════════════════════════════════════════
OBSERVATIONS (social history, smoking, alcohol)
═══════════════════════════════════════════════════════════════
${obsMd}

═══════════════════════════════════════════════════════════════
VISIT HISTORY
═══════════════════════════════════════════════════════════════
${visitsMd}

═══════════════════════════════════════════════════════════════
LAB TIMELINE (all measurements up to cutoff)
═══════════════════════════════════════════════════════════════
${labTableMd}

═══════════════════════════════════════════════════════════════
TROPONIN I HISTORY (extracted for quick reference)
═══════════════════════════════════════════════════════════════
${troponins.length > 0
  ? troponins.map(t => `  ${t.datetime}: ${t.value} ng/mL`).join('\n')
  : '  No prior Troponin I values in context.'}

═══════════════════════════════════════════════════════════════
PREDICTION TASK
═══════════════════════════════════════════════════════════════
Predict the Troponin I value at: ${caseData.question.target_datetime}
(${caseData.question.hours_ahead} hours after the last known troponin)

Consider:
• Troponin kinetics: in STEMI, troponin typically peaks at 12–24h then falls. In NSTEMI/UA,
  the peak is lower and the rise is slower.
• Serial delta troponin: a ≥20% relative change within 3h is diagnostic for AMI (ESC 0h/3h rule).
• Medications: antiplatelet/anticoagulant therapy indicates active ACS treatment; diuretics
  suggest heart failure; prior PCI/cath affects post-procedural troponin release.
• Renal function: elevated creatinine slows troponin clearance, causing chronic elevation.
• Use the full clinical picture — diagnoses, medications, procedures, and lab trajectory together.

Call StructuredOutput with your prediction.`

    return agent(prompt, {
      label:  `dirchange-predictor-${caseData.case_id}`,
      phase:  'Predict',
      schema: PREDICTION_SCHEMA,
    }).then(prediction => ({
      case_id:        caseData.case_id,
      patient_id:     caseData.patient_id,
      reversal_type:  caseData.reversal_type,
      vis_trend:      caseData.vis_trend,
      prediction,
      ground_truth:   caseData.ground_truth,
    })).catch(err => ({ case_id: caseData.case_id, reversal_type: caseData.reversal_type, error: String(err) }))
  })
)

// ─── Phase 2: Score ───────────────────────────────────────────────────────────
phase('Score')

function scoreResult(r) {
  if (!r || r.error || !r.prediction || !r.ground_truth) return null
  const actual    = r.ground_truth.value
  const predicted = r.prediction.predicted_value
  const dirMatch  = r.prediction.direction === r.ground_truth.direction
  const relError  = actual > 0 ? Math.abs(predicted - actual) / actual : 1.0
  const within50  = relError <= 0.50
  const within20  = relError <= 0.20
  let score = 0
  if (dirMatch)  score += 0.40
  if (within50)  score += 0.35
  if (within20)  score += 0.25
  return {
    case_id:           r.case_id,
    patient_id:        r.patient_id,
    reversal_type:     r.reversal_type,
    vis_trend:         r.vis_trend,
    predicted_value:   predicted,
    predicted_dir:     r.prediction.direction,
    actual_value:      actual,
    actual_dir:        r.ground_truth.direction,
    confidence:        r.prediction.confidence,
    direction_correct: dirMatch,
    rel_error_pct:     Math.round(relError * 100),
    within_50pct:      within50,
    within_20pct:      within20,
    score:             Math.round(score * 100) / 100,
  }
}

const scored = results.filter(Boolean).map(scoreResult).filter(Boolean)

function mean(arr, key) {
  return arr.length ? Math.round(arr.reduce((s, x) => s + x[key], 0) / arr.length * 1000) / 1000 : 0
}
function rate(arr, key) {
  return arr.length ? Math.round(arr.filter(x => x[key]).length / arr.length * 1000) / 1000 : 0
}

const fullEhrMean  = mean(scored, 'score')
const dirAccuracy  = rate(scored, 'direction_correct')
const within50Rate = rate(scored, 'within_50pct')
const within20Rate = rate(scored, 'within_20pct')

// Baselines — both fail by construction on every case
// trend-extrapolation: always predicts vis_trend direction → always wrong
// last-value: always predicts "stable" → wrong on rising/falling cases
const lvMean = Math.round(
  selectedMeta.slice(0, loadedCases.length).reduce((s, m) => {
    const w50 = m.lv_err_pct <= 50, w20 = m.lv_err_pct <= 20
    let sc = 0  // direction always wrong (not stable)
    if (w50) sc += 0.35
    if (w20) sc += 0.25
    return s + sc
  }, 0) / loadedCases.length * 1000
) / 1000

log(`Full EHR:  mean=${fullEhrMean}, dir_acc=${(dirAccuracy*100).toFixed(1)}%`)
log(`LV heuristic: mean=${lvMean}, dir_acc=0% (always wrong by construction)`)
log(`Trend-extrap: mean=0–0.60, dir_acc=0% (always wrong by construction)`)

const summary = await agent(
  `Analyze these Troponin I DIRECTION-CHANGE prediction results.

BENCHMARK DESIGN: Every case is a direction-change — the visible troponin trend reverses at the target time.
Both the last-value heuristic AND trend-extrapolation heuristic predict the WRONG direction by construction.
The model must use cross-lab signal (BNP, creatinine, vitals, meds) to detect the reversal.

SCORING (max 1.0): direction=0.40, within_50%=0.35, within_20%=0.25

BASELINES (both always wrong on direction):
  trend-extrapolation heuristic: dir_acc=0%, magnitude may be partially right
  last-value heuristic: dir_acc=0%, mean=${lvMean}

FULL EHR MODEL:
  mean=${fullEhrMean}, dir_acc=${dirAccuracy}, within_50%=${within50Rate}, within_20%=${within20Rate}

PER-CASE RESULTS:
${JSON.stringify(scored, null, 2)}

Produce:
1. comparison_table — markdown: Metric | Trend-Extrap Heuristic | Last-Value Heuristic | Full EHR Model
2. per_case_table — markdown: Case | Reversal Type | Vis Trend | True Dir | Predicted Dir | Score | Correct?
3. analysis — 5-7 sentences: Can the model detect direction reversals? Which reversal types (falling→rising vs rising→falling) does it handle better? Does it still show rising-bias? What cross-lab signals seem to help?`,
  { label: 'dirchange-comparator', phase: 'Score', schema: SUMMARY_SCHEMA }
)

return {
  n_cases:   scored.length,
  full_ehr: {
    mean_score:         fullEhrMean,
    direction_accuracy: dirAccuracy,
    within_50pct_rate:  within50Rate,
    within_20pct_rate:  within20Rate,
  },
  baselines: {
    trend_extrapolation: { dir_acc: 0, note: 'always wrong by construction' },
    last_value:          { mean: lvMean, dir_acc: 0, note: 'always wrong by construction' },
  },
  comparison_table: summary.comparison_table,
  per_case_table:   summary.per_case_table,
  analysis:         summary.analysis,
  per_case:         scored,
}
