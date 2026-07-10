export const meta = {
  name: 'cardiac-nextlab-agent',
  description: 'Predict the next serial Troponin I value given a patient full lab timeline',
  phases: [
    { title: 'Load',    detail: 'Read case from cardiac_nextlab_benchmark_v1.json' },
    { title: 'Predict', detail: 'Agent reasons over full lab timeline and predicts next Troponin I' },
  ],
}

// ─── Input ────────────────────────────────────────────────────────────────────
// Workflow({scriptPath: 'benchmarks/cardiac-nextlab/nextlab_answer_agent.js'}, {case_id: 1})
// case_id defaults to 1

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-nextlab/output/cardiac_nextlab_benchmark_v1.json'

const _case_id = (args && args.case_id) ? Number(args.case_id) : 1

// ─── Case schema ──────────────────────────────────────────────────────────────
const CASE_SCHEMA = {
  type: 'object',
  required: ['case_id', 'patient_id', 'demographics', 'clinical_context',
             'lab_timeline', 'question', 'ground_truth', 'scoring_guide'],
  properties: {
    case_id:    { type: 'number' },
    patient_id: { type: 'string' },
    demographics: {
      type: 'object',
      properties: {
        age:    { type: 'number' },
        gender: { type: 'string' },
      },
    },
    clinical_context: { type: 'object' },
    lab_timeline:     { type: 'array' },
    question:         { type: 'object' },
    ground_truth:     { type: 'object' },
    scoring_guide:    { type: 'object' },
  },
}

// ─── Prediction schema ────────────────────────────────────────────────────────
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
      description: (
        'Direction of Troponin I change relative to the last measurement. ' +
        'rising = >20% increase, falling = >20% decrease, stable = within ±20%.'
      ),
    },
    confidence: {
      type: 'string',
      enum: ['high', 'medium', 'low'],
    },
    reasoning: {
      type: 'string',
      description: '3-5 sentences. Reference specific prior values and clinical trajectory.',
    },
  },
}

// ─── Phase 0: Load ────────────────────────────────────────────────────────────

phase('Load')
log(`Loading case ${_case_id} from benchmark ...`)

const caseData = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Find the object in the "cases" array where case_id equals ${_case_id}.
Return the ENTIRE object exactly as it appears in the file — do not summarize or truncate.`,
  { label: 'case-loader', phase: 'Load', schema: CASE_SCHEMA }
)

if (!caseData) throw new Error(`Failed to load case ${_case_id}`)
log(`Loaded case ${_case_id}: patient ${caseData.patient_id}, ${caseData.lab_timeline.length} labs in context`)
log(`Target: predict Troponin I at ${caseData.question.target_datetime}`)

// ─── Phase 1: Predict ─────────────────────────────────────────────────────────

phase('Predict')

const troponins = caseData.lab_timeline.filter(l => l.label === 'Troponin I')
const labTableMd = [
  '| Datetime | Lab | Value | Unit | Flag |',
  '|---|---|---|---|---|',
  ...caseData.lab_timeline.map(l =>
    `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} | ${l.flag || ''} |`
  ),
].join('\n')

const prompt = `You are an expert cardiologist and intensivist. A patient has been admitted and
their complete lab timeline is shown below. Your task is to predict the NEXT Troponin I value.

═══════════════════════════════════════════════════════════════
PATIENT
═══════════════════════════════════════════════════════════════
${caseData.question.stem}

═══════════════════════════════════════════════════════════════
COMPLETE LAB TIMELINE (all measurements up to the cutoff)
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
• Context clues: prior troponin values, trend (rising/falling/stable), time gaps, other labs
  (creatinine elevation can cause chronic troponin elevation), and clinical diagnoses.

Call StructuredOutput with your prediction.`

const prediction = await agent(prompt, {
  label:  'troponin-predictor',
  phase:  'Predict',
  schema: PREDICTION_SCHEMA,
})

if (!prediction) throw new Error('Prediction agent returned null')

log(`Predicted: ${prediction.predicted_value} ${prediction.predicted_unit} (${prediction.direction}, confidence: ${prediction.confidence})`)

// ─── Return result ────────────────────────────────────────────────────────────

return {
  case_id:    _case_id,
  patient_id: caseData.patient_id,
  prediction,
  ground_truth: caseData.ground_truth,
  scoring_guide: caseData.scoring_guide,
}
