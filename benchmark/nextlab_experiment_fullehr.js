export const meta = {
  name: 'cardiac-nextlab-fullehr-experiment',
  description: 'Troponin I prediction with full EHR context — compare against labs-only baseline',
  phases: [
    { title: 'Predict', detail: 'Run full-EHR agent for all 20 cases in parallel' },
    { title: 'Score',   detail: 'Score predictions and compare to labs-only baseline' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/output/cardiac_nextlab_fullehr_benchmark_v1.json'
const _case_ids      = (args && args.case_ids) ? args.case_ids
  : [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]

// Labs-only baseline scores (from nextlab_experiment.js run)
const BASELINE_SCORES = {
  1:  0.60, 2:  0.75, 3:  0.35, 4:  0.00, 5:  0.60,
  6:  0.00, 7:  0.75, 8:  0.00, 9:  0.40, 10: 0.00,
  11: 0.00, 12: 0.00, 13: 0.00, 14: 0.35, 15: 0.00,
  16: 0.35, 17: 0.35, 18: 0.00, 19: 0.60, 20: 0.00,
}
const BASELINE_DIRS = {
  1:  'falling', 2:  'rising',  3:  'stable',  4:  'stable',  5:  'rising',
  6:  'stable',  7:  'rising',  8:  'rising',  9:  'rising',  10: 'rising',
  11: 'rising',  12: 'rising',  13: 'rising',  14: 'rising',  15: 'rising',
  16: 'stable',  17: 'falling', 18: 'stable',  19: 'stable',  20: 'rising',
}

// ─── Phase 0: Load all cases once ─────────────────────────────────────────────
phase('Predict')
log(`Loading ${_case_ids.length} cases from benchmark ...`)

const CASES_SCHEMA = {
  type: 'object',
  required: ['cases'],
  properties: {
    cases: { type: 'array' },
  },
}

const benchmarkData = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Return an object with a "cases" key containing only the cases where case_id is in: ${JSON.stringify(_case_ids)}.
Return the full objects without truncation.`,
  { label: 'bulk-case-loader', phase: 'Predict', schema: CASES_SCHEMA }
)

if (!benchmarkData || !benchmarkData.cases.length) throw new Error('Failed to load cases')
log(`Loaded ${benchmarkData.cases.length} cases. Running predictions ...`)

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

// ─── Phase 1: Predict all cases in parallel ───────────────────────────────────
const results = await parallel(
  benchmarkData.cases.map(caseData => () => {
    const troponins = caseData.lab_timeline.filter(l => l.label === 'Troponin I')

    const labTableMd = [
      '| Datetime | Lab | Value | Unit | Flag |',
      '|---|---|---|---|---|',
      ...caseData.lab_timeline.map(l =>
        `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} | ${l.flag || ''} |`
      ),
    ].join('\n')

    const diagMd  = caseData.diagnoses.length
      ? caseData.diagnoses.map(d => `  ${d.date}  ${d.code}  ${d.description}`).join('\n')
      : '  None recorded'
    const medsMd  = caseData.medications.length
      ? caseData.medications.map(m => `  ${m.date}  ${m.name}`).join('\n')
      : '  None recorded'
    const procsMd = caseData.procedures.length
      ? caseData.procedures.map(p => `  ${p.date}  ${p.code}  ${p.description}`).join('\n')
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
  ? troponins.map(t => `  ${t.datetime}: ${t.value} ${t.unit} (${t.flag || 'normal'})`).join('\n')
  : '  No prior Troponin I values in context.'}

═══════════════════════════════════════════════════════════════
PREDICTION TASK
═══════════════════════════════════════════════════════════════
Predict the Troponin I value at: ${caseData.question.target_datetime}
(${caseData.question.hours_ahead} hours after the last measurement)

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
      label:  `fullehr-predictor-${caseData.case_id}`,
      phase:  'Predict',
      schema: PREDICTION_SCHEMA,
    }).then(prediction => ({
      case_id:      caseData.case_id,
      patient_id:   caseData.patient_id,
      condition:    'full_ehr',
      prediction,
      ground_truth: caseData.ground_truth,
    })).catch(err => ({ case_id: caseData.case_id, condition: 'full_ehr', error: String(err) }))
  })
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
    baseline_score:     BASELINE_SCORES[r.case_id] ?? null,
    baseline_dir:       BASELINE_DIRS[r.case_id] ?? null,
    delta:              Math.round((Math.round(score * 100) / 100 - (BASELINE_SCORES[r.case_id] ?? 0)) * 100) / 100,
  }
}

const scored = results.filter(Boolean).map(scoreResult).filter(Boolean)

function mean(arr, key) {
  return arr.length ? Math.round(arr.reduce((s, x) => s + x[key], 0) / arr.length * 1000) / 1000 : 0
}
function rate(arr, key) {
  return arr.length ? Math.round(arr.filter(x => x[key]).length / arr.length * 1000) / 1000 : 0
}

const fullEhrMean    = mean(scored, 'score')
const baselineMean   = mean(scored, 'baseline_score')
const dirAccuracy    = rate(scored, 'direction_correct')
const within50Rate   = rate(scored, 'within_50pct')
const within20Rate   = rate(scored, 'within_20pct')
const baselineDirAcc = scored.filter(s => s.baseline_dir === s.actual_dir).length / scored.length

log(`Full EHR:  mean=${fullEhrMean}, dir_acc=${(dirAccuracy*100).toFixed(1)}%`)
log(`Baseline:  mean=${baselineMean}, dir_acc=${(baselineDirAcc*100).toFixed(1)}%`)
log(`Delta:     ${Math.round((fullEhrMean - baselineMean)*1000)/1000}`)

// ─── Summary agent ────────────────────────────────────────────────────────────
const SUMMARY_SCHEMA = {
  type: 'object',
  required: ['comparison_table', 'per_case_table', 'analysis'],
  properties: {
    comparison_table: { type: 'string' },
    per_case_table:   { type: 'string' },
    analysis:         { type: 'string' },
  },
}

const summary = await agent(
  `Analyze these Troponin I prediction results comparing two conditions:
  1. baseline (labs only) — 80-row lab table, no other EHR data
  2. full_ehr — same lab table + complete diagnoses, medications, procedures, observations, visit history

SCORING (max 1.0): direction=0.40, within_50pct=0.35, within_20pct=0.25

AGGREGATE:
  full_ehr  mean=${fullEhrMean}, dir_acc=${dirAccuracy}, within_50%=${within50Rate}, within_20%=${within20Rate}
  baseline  mean=${baselineMean}, dir_acc=${baselineDirAcc}

PER-CASE RESULTS:
${JSON.stringify(scored, null, 2)}

Produce:
1. comparison_table — markdown: Metric | Baseline (labs only) | Full EHR | Delta
2. per_case_table   — markdown: Case | True Dir | Baseline (dir, score) | Full EHR (dir, score) | Delta | Winner
3. analysis         — 4-6 sentences: did full EHR context improve performance? Which data types
   (meds, procedures, diagnoses) appear to have helped or hurt on specific cases? Does the model
   show any new failure modes or fix existing ones (e.g., the rising-bias problem)?`,
  { label: 'fullehr-comparator', phase: 'Score', schema: SUMMARY_SCHEMA }
)

return {
  n_cases:          scored.length,
  full_ehr: {
    mean_score:         fullEhrMean,
    direction_accuracy: dirAccuracy,
    within_50pct_rate:  within50Rate,
    within_20pct_rate:  within20Rate,
  },
  baseline: {
    mean_score:         baselineMean,
    direction_accuracy: baselineDirAcc,
  },
  comparison_table: summary.comparison_table,
  per_case_table:   summary.per_case_table,
  analysis:         summary.analysis,
  per_case:         scored,
}
