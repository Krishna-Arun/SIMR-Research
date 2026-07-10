export const meta = {
  name: 'cardiac-dirchange-v2-agent',
  description: 'Predict the next Troponin I value in a direction-change case (visible trend reverses)',
  phases: [
    { title: 'Load',    detail: 'Read case from cardiac_dirchange_v2_benchmark_v1.json' },
    { title: 'Predict', detail: 'Agent reasons over full lab timeline (incl. gap-window cross-lab signals) and predicts next Troponin I' },
  ],
}

// ─── Input ────────────────────────────────────────────────────────────────────
// Workflow({scriptPath: 'benchmarks/cardiac-dirchange-v2/nextlab_answer_agent.js'}, {case_id: 1})
// case_id defaults to 1

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/output/cardiac_dirchange_v2_benchmark_v1.json'

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

const gapLabs = caseData.lab_timeline.filter(l => l.in_gap)
const gapLabsMd = gapLabs.length > 0
  ? [
      '| Datetime | Lab | Value | Unit | Flag |',
      '|---|---|---|---|---|',
      ...gapLabs.map(l => `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} | ${l.flag || ''} |`),
    ].join('\n')
  : '  (no cross-lab readings in the gap window)'

// Build a clean patient header from case fields — do NOT use question.stem, which
// contains the visible_trend label baked in by the prep script.
const dx  = (caseData.clinical_context.diagnoses  || []).slice(0, 6).join('; ') || 'not recorded'
const meds = (caseData.clinical_context.medications || []).slice(0, 6).join(', ') || 'not recorded'
const patientHeader = [
  `Patient subject_id: ${caseData.patient_id}`,
  `A ${caseData.demographics.age}-year-old ${caseData.demographics.gender} presents with chest symptoms.`,
  `Current diagnoses: ${dx}.`,
  `Current medications: ${meds}.`,
  `Troponin I measurements are available up to ${caseData.context_cutoff}.`,
  `Additional labs are available up to ${caseData.question.target_datetime}.`,
  `The next Troponin I is scheduled for ${caseData.question.target_datetime} (${caseData.question.hours_ahead} hours after the last known reading).`,
].join('\n')

const prompt = `You are an expert cardiologist and intensivist. A cardiac patient's lab timeline is shown below.
Predict the next Troponin I value using all available clinical information.

═══════════════════════════════════════════════════════════════
PATIENT
═══════════════════════════════════════════════════════════════
${patientHeader}

═══════════════════════════════════════════════════════════════
FULL LAB TIMELINE (troponin up to cutoff; other labs up to prediction time)
═══════════════════════════════════════════════════════════════
${labTableMd}

═══════════════════════════════════════════════════════════════
TROPONIN I HISTORY (visible readings only — cutoff: ${caseData.context_cutoff})
═══════════════════════════════════════════════════════════════
${troponins.length > 0
  ? troponins.map(t => `  ${t.datetime}: ${t.value} ${t.unit} (${t.flag || 'normal'})`).join('\n')
  : '  No prior Troponin I values in context.'}

═══════════════════════════════════════════════════════════════
ADDITIONAL LAB DATA (after troponin cutoff, up to prediction time)
═══════════════════════════════════════════════════════════════
${gapLabsMd}

═══════════════════════════════════════════════════════════════
PREDICTION TASK
═══════════════════════════════════════════════════════════════
Predict the Troponin I value at: ${caseData.question.target_datetime}
(${caseData.question.hours_ahead} hours after the last known troponin)

Consider:
• Troponin kinetics: STEMI peak at 12–24h then falls; NSTEMI rises more slowly.
• Cross-lab signals: BNP, creatinine, and other labs available after the troponin cutoff
  may indicate changes in cardiac injury or clearance.
• Serial delta troponin: ≥20% relative change = clinically significant.
• Clinical context: diagnoses, medications, and prior trajectory all matter.

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
