export const meta = {
  name: 'cardiac-multilab-answer-agent',
  description: 'Predict masked Troponin I using full EHR context — one case',
  phases: [
    { title: 'Load',    detail: 'Read case file from multilab_v1/' },
    { title: 'Predict', detail: 'Agent reads full EHR and predicts troponin value' },
  ],
}

// ─── Config ───────────────────────────────────────────────────────────────────
const MULTILAB_DIR   = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-multilab/output/multilab_v1'
const MANIFEST_PATH  = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-multilab/output/cardiac_multilab_benchmark_v1.json'

const _case_id    = (args && args.case_id)    ? args.case_id    : 1
const _condition  = (args && args.condition)  ? args.condition  : 'full_ehr'

// ─── Conditions ──────────────────────────────────────────────────────────────
const CONDITION_CONFIGS = {
  full_ehr: {
    label: 'Full EHR (labs + dx + meds + procs + obs + visits)',
    include_labs: true,
    include_diagnoses: true,
    include_medications: true,
    include_procedures: true,
    include_observations: true,
    include_visits: true,
  },
  labs_only: {
    label: 'Labs only (500-row lab table, no other EHR)',
    include_labs: true,
    include_diagnoses: false,
    include_medications: false,
    include_procedures: false,
    include_observations: false,
    include_visits: false,
  },
  no_tools: {
    label: 'No data (question stem only, no lab table)',
    include_labs: false,
    include_diagnoses: false,
    include_medications: false,
    include_procedures: false,
    include_observations: false,
    include_visits: false,
  },
}

const config = CONDITION_CONFIGS[_condition] || CONDITION_CONFIGS.full_ehr

// ─── Schemas ─────────────────────────────────────────────────────────────────
const CASE_SCHEMA = { type: 'object' }

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

// ─── Phase 1: Load case ───────────────────────────────────────────────────────
phase('Load')
const paddedId = String(_case_id).padStart(3, '0')
const casePath = `${MULTILAB_DIR}/case_${paddedId}.json`

log(`Loading case ${_case_id} from ${casePath} ...`)

const caseData = await agent(
  `Read the JSON file at "${casePath}". Return the full parsed object (all fields).`,
  { label: `load-case-${_case_id}`, phase: 'Load', schema: CASE_SCHEMA }
)

if (!caseData) throw new Error(`Failed to load case ${_case_id}`)
log(`Loaded: patient=${caseData.patient_id} dir=${caseData.ground_truth.direction} gap=${caseData.gap_hours}h`)

// ─── Phase 2: Build prompt and predict ───────────────────────────────────────
phase('Predict')

// Format sections based on condition
function fmtLabTable(labs) {
  if (!labs || !labs.length) return '  None recorded'
  const rows = [
    '| Datetime | Lab | Value | Unit |',
    '|---|---|---|---|',
    ...labs.map(l => `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} |`)
  ]
  return rows.join('\n')
}
function fmtList(items, fn) {
  return items && items.length ? items.map(fn).join('\n') : '  None recorded'
}

const labTableMd = config.include_labs
  ? fmtLabTable(caseData.lab_timeline)
  : '  [Hidden in this condition]'

const diagMd = config.include_diagnoses
  ? fmtList(caseData.diagnoses, d => `  ${d.date}  ${d.description || d.code}`)
  : '  [Hidden in this condition]'

const medsMd = config.include_medications
  ? fmtList(caseData.medications, m => `  ${m.date}  ${m.name}`)
  : '  [Hidden in this condition]'

const procsMd = config.include_procedures
  ? fmtList(caseData.procedures, p => `  ${p.date}  ${p.description || p.code}`)
  : '  [Hidden in this condition]'

const obsMd = config.include_observations
  ? fmtList(caseData.observations, o => `  ${o.date}  ${o.observation}${o.value ? ': ' + o.value : ''}`)
  : '  [Hidden in this condition]'

const visitsMd = config.include_visits
  ? fmtList(caseData.visit_history, v => `  ${v.date}  ${v.type}`)
  : '  [Hidden in this condition]'

const tropCtxMd = caseData.trop_context
  ? caseData.trop_context.map(t => `  ${t.datetime}  ${t.label}  ${t.value} ng/mL`).join('\n')
  : '  None'

const prompt = `You are an expert cardiologist and intensivist. You have a patient's complete EHR record
up to a cutoff time. Your task: predict the NEXT Troponin I measurement.

IMPORTANT: Troponin data is MASKED after the cutoff time shown below.
All other labs (creatinine, BNP, hemoglobin, vitals, etc.) are visible right up to the prediction time.
Use ALL available data — the troponin trajectory, organ function labs, hemodynamics, medications,
and diagnoses — to estimate where troponin will be.

═══════════════════════════════════════════════════════════════
PREDICTION TASK
═══════════════════════════════════════════════════════════════
${caseData.question.stem}

═══════════════════════════════════════════════════════════════
TROPONIN I HISTORY (visible up to cutoff only)
═══════════════════════════════════════════════════════════════
${tropCtxMd}

═══════════════════════════════════════════════════════════════
FULL LAB TIMELINE (all labs including gap labs up to target time)
═══════════════════════════════════════════════════════════════
${labTableMd}

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
OBSERVATIONS
═══════════════════════════════════════════════════════════════
${obsMd}

═══════════════════════════════════════════════════════════════
VISIT HISTORY
═══════════════════════════════════════════════════════════════
${visitsMd}

═══════════════════════════════════════════════════════════════
REASONING GUIDANCE
═══════════════════════════════════════════════════════════════
• Troponin kinetics: after ACS, troponin peaks at 12–24h then clears over 4–10 days.
  Serial readings showing consistent rise or fall predict continued trajectory.
• Renal function (creatinine, BUN): impaired clearance slows troponin fall; AKI causes spurious elevation.
• Hemodynamics (HR, BP in lab table): hemodynamic instability suggests ongoing myocardial stress.
• BNP/NT-proBNP: elevated = ventricular stretch; may indicate worsening or improving heart failure.
• Medications: anticoagulants + antiplatelets indicate active ACS management (trending down after peak).
  Diuretics indicate HF management. New vasopressors indicate deterioration.
• Direction: rising = >20% increase, falling = >20% decrease, stable = within ±20%.

Call StructuredOutput with your prediction.`

const prediction = await agent(prompt, {
  label:  `predictor-case${_case_id}-${_condition}`,
  phase:  'Predict',
  schema: PREDICTION_SCHEMA,
})

// ─── Score ────────────────────────────────────────────────────────────────────
const actual    = caseData.ground_truth.value
const predicted = prediction ? prediction.predicted_value : null
const actualDir = caseData.ground_truth.direction

let score = null, relError = null, within50 = false, within20 = false, dirMatch = false
if (prediction) {
  dirMatch  = prediction.direction === actualDir
  score     = dirMatch ? 0.40 : 0.0
  relError  = actual > 0 ? Math.abs(predicted - actual) / actual : 1.0
  within50  = relError <= 0.50
  within20  = relError <= 0.20
  if (within50) score += 0.35
  if (within20) score += 0.25
  score = Math.round(score * 100) / 100
}

log(`Case ${_case_id} [${_condition}]: predicted=${predicted} actual=${actual} dir=${prediction?.direction}/${actualDir} score=${score}`)

return {
  case_id:            _case_id,
  patient_id:         caseData.patient_id,
  condition:          _condition,
  condition_label:    config.label,
  gap_hours:          caseData.gap_hours,
  difficulty:         caseData.difficulty,
  prediction,
  ground_truth:       caseData.ground_truth,
  scoring: {
    score,
    direction_correct: dirMatch,
    relative_error_pct: relError !== null ? Math.round(relError * 100) : null,
    within_50pct: within50,
    within_20pct: within20,
    last_value_heuristic_error_pct: caseData.last_value_heuristic_error_pct,
  },
}
