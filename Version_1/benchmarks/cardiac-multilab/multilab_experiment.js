export const meta = {
  name: 'cardiac-multilab-experiment',
  description: 'Troponin I prediction with masked last value — full EHR vs labs only',
  phases: [
    { title: 'Predict', detail: 'Run prediction agents for all cases in parallel' },
    { title: 'Score',   detail: 'Score predictions and compare conditions' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const MULTILAB_DIR  = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-multilab/output/multilab_v1'
const MANIFEST_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-multilab/output/cardiac_multilab_benchmark_v1.json'

const _case_ids   = (args && args.case_ids)   ? args.case_ids   : null
const _conditions = (args && args.conditions) ? args.conditions : ['full_ehr', 'labs_only']
const _n_cases    = (args && args.n_cases)    ? args.n_cases    : 20

// ─── Schemas ─────────────────────────────────────────────────────────────────
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

// ─── Load manifest then all case files ────────────────────────────────────────
phase('Predict')

const manifest = await agent(
  `Read the JSON file at ${MANIFEST_PATH}. Return the full object including the cases array.`,
  { label: 'load-manifest', schema: CASES_SCHEMA }
)
if (!manifest || !manifest.cases.length) throw new Error('Failed to load manifest')

let selectedMeta = manifest.cases
if (_case_ids) selectedMeta = selectedMeta.filter(c => _case_ids.includes(c.case_id))
else           selectedMeta = selectedMeta.slice(0, _n_cases)

log(`Loading ${selectedMeta.length} case files ...`)

const caseDataList = await parallel(
  selectedMeta.map(m => () => {
    const paddedId = String(m.case_id).padStart(3, '0')
    return agent(
      `Read the JSON file at ${MULTILAB_DIR}/case_${paddedId}.json.
Return an object with these keys: case_id, patient_id, difficulty, gap_hours,
last_value_heuristic_error_pct, question, ground_truth, trop_context,
lab_timeline, diagnoses, medications, procedures, observations, visit_history.
Return the full arrays without truncation.`,
      { label: `load-${m.case_id}`, schema: CASES_SCHEMA }
    ).then(r => r && r.cases ? r.cases[0] : r)
  })
)

const loadedCases = caseDataList.filter(Boolean)
log(`Loaded ${loadedCases.length} cases. Running predictions ...`)

// ─── Predict all cases × conditions in parallel ───────────────────────────────
const results = await parallel(
  loadedCases.flatMap(caseData =>
    _conditions.map(condition => () => {

      // trop_context holds visible troponins (may be cut from lab_timeline by 500-row cap)
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
${condition === 'full_ehr' ? diagMd : '  None recorded'}

═══════════════════════════════════════════════════════════════
MEDICATIONS
═══════════════════════════════════════════════════════════════
${condition === 'full_ehr' ? medsMd : '  None recorded'}

═══════════════════════════════════════════════════════════════
PROCEDURES
═══════════════════════════════════════════════════════════════
${condition === 'full_ehr' ? procsMd : '  None recorded'}

═══════════════════════════════════════════════════════════════
OBSERVATIONS
═══════════════════════════════════════════════════════════════
${condition === 'full_ehr' ? obsMd : '  None recorded'}

═══════════════════════════════════════════════════════════════
VISIT HISTORY
═══════════════════════════════════════════════════════════════
${condition === 'full_ehr' ? visitsMd : '  None recorded'}

═══════════════════════════════════════════════════════════════
LAB TIMELINE (all labs up to target time — troponin masked after cutoff)
═══════════════════════════════════════════════════════════════
${labTableMd}

═══════════════════════════════════════════════════════════════
TROPONIN I HISTORY (extracted for quick reference — cutoff shown above)
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
        label:  `predict-${caseData.case_id}-${condition}`,
        phase:  'Predict',
        schema: PREDICTION_SCHEMA,
      }).then(prediction => ({
        case_id:      caseData.case_id,
        patient_id:   caseData.patient_id,
        condition,
        difficulty:   caseData.difficulty,
        gap_hours:    caseData.gap_hours,
        lv_err_pct:   caseData.last_value_heuristic_error_pct,
        prediction,
        ground_truth: caseData.ground_truth,
      })).catch(err => ({ case_id: caseData.case_id, condition, error: String(err) }))
    })
  )
)

// ─── Score ────────────────────────────────────────────────────────────────────
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
    condition:         r.condition,
    difficulty:        r.difficulty,
    gap_hours:         r.gap_hours,
    lv_err_pct:        r.lv_err_pct,
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

const condStats = {}
for (const cond of _conditions) {
  const s = scored.filter(r => r.condition === cond)
  condStats[cond] = {
    n:       s.length,
    mean:    mean(s, 'score'),
    dir_acc: rate(s, 'direction_correct'),
    w50:     rate(s, 'within_50pct'),
    w20:     rate(s, 'within_20pct'),
  }
  log(`${cond}: n=${condStats[cond].n} mean=${condStats[cond].mean} dir_acc=${condStats[cond].dir_acc}`)
}

// Last-value heuristic: always predicts "stable" at last known troponin
const lvScores = selectedMeta.slice(0, loadedCases.length).map(m => {
  const dirCorrect = m.actual_dir === 'stable'
  const w50 = m.lv_err_pct <= 50
  const w20 = m.lv_err_pct <= 20
  let sc = 0
  if (dirCorrect) sc += 0.40
  if (w50)        sc += 0.35
  if (w20)        sc += 0.25
  return sc
})
const lvMean   = Math.round(lvScores.reduce((s, v) => s + v, 0) / lvScores.length * 1000) / 1000
const lvDirAcc = Math.round(selectedMeta.slice(0, loadedCases.length).filter(m => m.actual_dir === 'stable').length / lvScores.length * 1000) / 1000
log(`last-value heuristic: mean=${lvMean} dir_acc=${lvDirAcc}`)

const caseMap = {}
for (const r of scored) {
  if (!caseMap[r.case_id]) caseMap[r.case_id] = {
    case_id:    r.case_id,
    actual_dir: r.actual_dir,
    difficulty: r.difficulty,
    gap_hours:  r.gap_hours,
    lv_err_pct: r.lv_err_pct,
  }
  caseMap[r.case_id][r.condition] = {
    predicted_dir: r.predicted_dir,
    score:         r.score,
    dir_correct:   r.direction_correct,
    rel_error_pct: r.rel_error_pct,
  }
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

const summary = await agent(
  `Analyze these next-Troponin I prediction results.
BENCHMARK: ${loadedCases.length} cases, last troponin masked, model predicts using cross-lab signal.
50% hard (1 visible troponin), 50% medium/easy (2+ visible).
SCORING: direction=0.40, within_50%=0.35, within_20%=0.25 (max 1.0)
Last-value heuristic: predict "stable" at last known troponin.

AGGREGATE:
  lv_heuristic: mean=${lvMean}, dir_acc=${lvDirAcc}
${_conditions.map(c => `  ${c}: ${JSON.stringify(condStats[c])}`).join('\n')}

PER-CASE:
${JSON.stringify(Object.values(caseMap), null, 2)}

Produce:
1. comparison_table — markdown: Metric | Last-Value Heuristic | ${_conditions.join(' | ')}
2. per_case_table — markdown: Case | Diff | Gap(h) | True Dir | LV Err% | ${_conditions.map(c => c + ' (dir, score)').join(' | ')} | Winner
3. analysis — 5-7 sentences on: does full EHR beat labs-only, rising-bias, hard vs easy gap, does last-value heuristic still win`,
  { label: 'summarizer', phase: 'Score', schema: SUMMARY_SCHEMA }
)

return {
  n_cases:          loadedCases.length,
  conditions:       _conditions,
  stats:            condStats,
  lv_baseline:      { mean: lvMean, dir_acc: lvDirAcc },
  comparison_table: summary.comparison_table,
  per_case_table:   summary.per_case_table,
  analysis:         summary.analysis,
  per_case:         Object.values(caseMap),
  all_scored:       scored,
}
