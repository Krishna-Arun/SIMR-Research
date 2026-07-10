export const meta = {
  name: 'cardiac-nextlab-agent-v2',
  description: 'Predict next Troponin I value — supports with_pubmed and without_pubmed conditions',
  phases: [
    { title: 'Load',    detail: 'Read case from cardiac_nextlab_benchmark_v1.json' },
    { title: 'Predict', detail: 'Agent predicts next Troponin I with or without PubMed MCP access' },
  ],
}

// ─── Input ────────────────────────────────────────────────────────────────────
// args: { case_id, condition }
//   condition: 'with_pubmed' | 'without_pubmed'

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-nextlab/output/cardiac_nextlab_benchmark_v1.json'

const _case_id   = (args && args.case_id)   ? Number(args.case_id) : 1
const _condition = (args && args.condition) ? args.condition       : 'without_pubmed'

// ─── Schemas ──────────────────────────────────────────────────────────────────
const CASE_SCHEMA = {
  type: 'object',
  required: ['case_id', 'patient_id', 'demographics', 'clinical_context',
             'lab_timeline', 'question', 'ground_truth', 'scoring_guide'],
  properties: {
    case_id:          { type: 'number' },
    patient_id:       { type: 'string' },
    demographics:     { type: 'object' },
    clinical_context: { type: 'object' },
    lab_timeline:     { type: 'array' },
    question:         { type: 'object' },
    ground_truth:     { type: 'object' },
    scoring_guide:    { type: 'object' },
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
log(`Loading case ${_case_id} [${_condition}] ...`)

const caseData = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Find the object in the "cases" array where case_id equals ${_case_id}.
Return the ENTIRE object exactly as it appears in the file — do not summarize or truncate.`,
  { label: `case-loader-${_case_id}`, phase: 'Load', schema: CASE_SCHEMA }
)

if (!caseData) throw new Error(`Failed to load case ${_case_id}`)
log(`Loaded: patient ${caseData.patient_id}, ${caseData.lab_timeline.length} labs, condition=${_condition}`)

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

// The only difference between conditions: one sentence about MCP access
const toolsLine = _condition === 'with_pubmed'
  ? `You have access to PubMed MCP tools (mcp__pubmed-server__search_articles, mcp__pubmed-server__get_abstract). You may search for relevant literature before making your prediction.\n`
  : ''

const prompt = `You are an expert cardiologist and intensivist. A patient has been admitted and
their complete lab timeline is shown below. Your task is to predict the NEXT Troponin I value.
${toolsLine}
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
  label:  `troponin-predictor-${_case_id}-${_condition}`,
  phase:  'Predict',
  schema: PREDICTION_SCHEMA,
})

if (!prediction) throw new Error(`Prediction agent returned null for case ${_case_id}`)

log(`Case ${_case_id} [${_condition}]: ${prediction.predicted_value} ng/mL (${prediction.direction}, ${prediction.confidence})`)

return {
  case_id:      _case_id,
  patient_id:   caseData.patient_id,
  condition:    _condition,
  prediction,
  ground_truth: caseData.ground_truth,
}
