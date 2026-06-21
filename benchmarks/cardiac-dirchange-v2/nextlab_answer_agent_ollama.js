/**
 * Ollama-based answer agent for cardiac-dirchange-v2.
 * Replaces Claude Code's `agent()` with direct Ollama API calls via ollama_agent.js.
 * Same logic as the original nextlab_answer_agent.js.
 */

import { readFileSync } from 'fs'
import { callAgentStructured, callAgentText, DEFAULT_MODEL } from './ollama_agent.js'

// ─── Input ────────────────────────────────────────────────────────────────────
// Run via: node nextlab_answer_agent_ollama.js --case_id 1
// case_id defaults to 1

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/output/cardiac_dirchange_v2_benchmark_v1.json'

const rawArgs = process.argv.slice(2)
let _case_id = 1
for (let i = 0; i < rawArgs.length; i++) {
  if (rawArgs[i] === '--case_id' && i + 1 < rawArgs.length) {
    _case_id = Number(rawArgs[i + 1])
  }
}

const MODEL = process.env.OLLAMA_MODEL || DEFAULT_MODEL

// ─── Case schema ──────────────────────────────────────────────────────────────
const CASE_SCHEMA = {
  type: 'object',
  required: ['case_id', 'patient_id', 'demographics', 'clinical_context',
             'lab_timeline', 'question', 'ground_truth', 'scoring_guide'],
  properties: {
    case_id:    { type: 'number' },
    patient_id: { type: 'string' },
    demographics: { type: 'object' },
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

// ─── Phase 0: Load case ───────────────────────────────────────────────────────

console.log(`\n=== Loading case ${_case_id} from benchmark (Ollama) ===`)

const benchmarkData = JSON.parse(readFileSync(BENCHMARK_PATH, 'utf8'))
const caseData = benchmarkData.cases.find(c => c.case_id === _case_id)

if (!caseData) throw new Error(`Failed to find case ${_case_id} in benchmark`)
console.log(`Loaded case ${_case_id}: patient ${caseData.patient_id}, ${caseData.lab_timeline.length} labs in context`)
console.log(`Target: predict Troponin I at ${caseData.question.target_datetime}`)

// ─── Phase 1: Predict ─────────────────────────────────────────────────────────

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

const prompt = `You are an expert cardiologist and intensivist. This is a DIRECTION-CHANGE prediction task.
The patient's visible troponin trend will REVERSE at the target time — your job is to detect this
using cross-lab signals available in the gap window (BNP, creatinine, vitals, etc.).

WARNING: Simply extrapolating the visible troponin trend will give the WRONG answer.
You must look at the cross-lab signals to determine whether the troponin will reverse direction.

═══════════════════════════════════════════════════════════════
PATIENT
═══════════════════════════════════════════════════════════════
${caseData.question.stem}

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
Visible trend: ${caseData.question.visible_trend}

═══════════════════════════════════════════════════════════════
GAP-WINDOW CROSS-LAB SIGNALS (between troponin cutoff and prediction time)
═══════════════════════════════════════════════════════════════
${gapLabsMd}

═══════════════════════════════════════════════════════════════
PREDICTION TASK
═══════════════════════════════════════════════════════════════
Predict the Troponin I value at: ${caseData.question.target_datetime}
(${caseData.question.hours_ahead} hours after the last known troponin)

Consider:
• DO NOT just extrapolate the visible troponin trend — it will reverse.
• Gap-window cross-lab signals are the key: rising BNP or creatinine may indicate
  worsening cardiac injury; falling BNP + improving creatinine may indicate clearance.
• Troponin kinetics: STEMI peak at 12–24h then falls; NSTEMI rises more slowly.
• Serial delta troponin: ≥20% relative change = clinically significant.
• Clinical context: diagnoses, medications, and prior trajectory all matter.

Return your prediction as a JSON object with fields: predicted_value, predicted_unit, direction, confidence, reasoning.`

console.log('\n=== Calling Ollama agent (model: ' + MODEL + ') ===')

const prediction = await callAgentStructured(prompt, '', PREDICTION_SCHEMA, MODEL)

if (!prediction) throw new Error('Ollama prediction returned null')

console.log(`Predicted: ${prediction.predicted_value} ${prediction.predicted_unit || 'ng/mL'} (${prediction.direction}, confidence: ${prediction.confidence})`)
if (prediction.reasoning) {
  console.log(`Reasoning: ${prediction.reasoning.slice(0, 200)}${prediction.reasoning.length > 200 ? '...' : ''}`)
}

// ─── Return result ────────────────────────────────────────────────────────────

const result = {
  case_id:    _case_id,
  patient_id: caseData.patient_id,
  prediction,
  ground_truth: caseData.ground_truth,
  scoring_guide: caseData.scoring_guide,
}

console.log('\n=== Result ===')
console.log(JSON.stringify(result, null, 2))
