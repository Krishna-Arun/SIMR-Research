export const meta = {
  name: 'cardiac-nextlab-agent-fullehr',
  description: 'Predict next Troponin I value given complete EHR context (labs, meds, diagnoses, procedures, observations, visits)',
  phases: [
    { title: 'Load',    detail: 'Read case from cardiac_nextlab_fullehr_benchmark_v1.json' },
    { title: 'Predict', detail: 'Agent predicts next Troponin I over full EHR context' },
  ],
}

// args: { case_id }
const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/output/cardiac_nextlab_fullehr_benchmark_v1.json'
const _case_id = (args && args.case_id) ? Number(args.case_id) : 1

// ─── Schemas ──────────────────────────────────────────────────────────────────
const CASE_SCHEMA = {
  type: 'object',
  required: ['case_id', 'patient_id', 'demographics', 'diagnoses', 'medications',
             'procedures', 'observations', 'visit_history', 'lab_timeline',
             'question', 'ground_truth'],
  properties: {
    case_id:       { type: 'number' },
    patient_id:    { type: 'string' },
    difficulty:    { type: 'string' },
    demographics:  { type: 'object' },
    diagnoses:     { type: 'array' },
    medications:   { type: 'array' },
    procedures:    { type: 'array' },
    observations:  { type: 'array' },
    visit_history: { type: 'array' },
    lab_timeline:  { type: 'array' },
    question:      { type: 'object' },
    ground_truth:  { type: 'object' },
    data_summary:  { type: 'object' },
  },
}

const PREDICTION_SCHEMA = {
  type: 'object',
  required: ['predicted_value', 'predicted_unit', 'direction', 'confidence', 'reasoning'],
  properties: {
    predicted_value: {
      type: 'number',
      description: 'Numeric Troponin I value in ng/mL',
    },
    predicted_unit: {
      type: 'string',
      description: 'Unit of the predicted value (should be ng/mL)',
    },
    direction: {
      type: 'string',
      enum: ['rising', 'falling', 'stable'],
      description: 'rising = >20% increase, falling = >20% decrease, stable = within ±20%.',
    },
    confidence: {
      type: 'string',
      enum: ['high', 'medium', 'low'],
    },
    reasoning: {
      type: 'string',
      description: '3-5 sentences. Reference specific values, medications, procedures, or diagnoses that informed your prediction.',
    },
  },
}

// ─── Phase 0: Load ────────────────────────────────────────────────────────────
phase('Load')
log(`Loading full-EHR case ${_case_id} ...`)

const caseData = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Find the object in the "cases" array where case_id equals ${_case_id}.
Return the ENTIRE object exactly as it appears in the file — do not summarize or truncate.`,
  { label: `case-loader-${_case_id}`, phase: 'Load', schema: CASE_SCHEMA }
)

if (!caseData) throw new Error(`Failed to load case ${_case_id}`)

const ds = caseData.data_summary
log(`Loaded case ${_case_id}: patient ${caseData.patient_id}, difficulty=${caseData.difficulty}`)
log(`Context: ${ds.n_diagnoses} dx, ${ds.n_medications} meds, ${ds.n_procedures} procs, ${ds.n_observations} obs, ${ds.n_visits} visits, ${ds.n_lab_rows} labs`)

// ─── Phase 1: Predict ─────────────────────────────────────────────────────────
phase('Predict')

// Format each section as a readable table/list
const troponins = caseData.lab_timeline.filter(l => l.label === 'Troponin I')

const labTableMd = [
  '| Datetime | Lab | Value | Unit | Flag |',
  '|---|---|---|---|---|',
  ...caseData.lab_timeline.map(l =>
    `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} | ${l.flag || ''} |`
  ),
].join('\n')

const diagMd = caseData.diagnoses.length > 0
  ? caseData.diagnoses.map(d => `  ${d.date}  ${d.code}  ${d.description}`).join('\n')
  : '  None recorded'

const medsMd = caseData.medications.length > 0
  ? caseData.medications.map(m => `  ${m.date}  ${m.name}`).join('\n')
  : '  None recorded'

const procsMd = caseData.procedures.length > 0
  ? caseData.procedures.map(p => `  ${p.date}  ${p.code}  ${p.description}`).join('\n')
  : '  None recorded'

const obsMd = caseData.observations.length > 0
  ? caseData.observations.map(o => `  ${o.date}  ${o.observation}${o.value ? ': ' + o.value : ''}`).join('\n')
  : '  None recorded'

const visitsMd = caseData.visit_history.length > 0
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

const prediction = await agent(prompt, {
  label:  `troponin-predictor-fullehr-${_case_id}`,
  phase:  'Predict',
  schema: PREDICTION_SCHEMA,
})

if (!prediction) throw new Error(`Prediction agent returned null for case ${_case_id}`)

log(`Case ${_case_id}: ${prediction.predicted_value} ng/mL (${prediction.direction}, ${prediction.confidence})`)

return {
  case_id:      _case_id,
  patient_id:   caseData.patient_id,
  condition:    'full_ehr',
  prediction,
  ground_truth: caseData.ground_truth,
}
