#!/usr/bin/env node
/**
 * Ollama-based answer agent for cardiac-dirchange-v3 benchmark.
 * Runs ALL 20 cases under both conditions (same cases, different PubMed access).
 *
 * Usage:
 *   node answer_agent_ollama.js --condition control     (full EHR + PubMed)
 *   node answer_agent_ollama.js --condition independent (full EHR only)
 *   Defaults to 'independent'.
 *
 * Both conditions receive the SAME 20 cases — only the PubMed tools line differs.
 */

import { readFileSync } from 'fs'
import { callAgentStructured, DEFAULT_MODEL } from './ollama_agent.mjs'

// ─── Input ────────────────────────────────────────────────────────────────────

const rawArgs = process.argv.slice(2)
let _condition = 'independent'
for (let i = 0; i < rawArgs.length; i++) {
  if (rawArgs[i] === '--condition' && i + 1 < rawArgs.length) {
    _condition = rawArgs[i + 1]
  }
}

const MODEL     = process.env.OLLAMA_MODEL || DEFAULT_MODEL
const BASE_URL  = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'
const BENCHMARK_PATH = process.env.BENCHMARK_PATH
  || '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v3/output/cardiac_dirchange_v3_benchmark_v1.json'
const OUTPUT_PATH    = process.env.OUTPUT_PATH
  || `/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v3/output/v3_${_condition}_results.json`

const CONDITION_LABEL = _condition === 'control'
  ? 'Full EHR + PubMed MCP Server'
  : 'Full EHR only (no PubMed)'

console.log(`\n=== cardiac-dirchange-v3: ${CONDITION_LABEL} ===`)
console.log(`Model: ${MODEL}  |  Base URL: ${BASE_URL}`)
console.log(`Benchmark: ${BENCHMARK_PATH}`)

// ─── Load benchmark ────────────────────────────────────────────────────────────

const benchmarkData = JSON.parse(readFileSync(BENCHMARK_PATH, 'utf8'))
const cases = benchmarkData.cases
console.log(`Loaded ${cases.length} cases from benchmark\n`)

if (_condition === 'control' && cases.length !== 20) {
  console.warn(`WARNING: Expected 20 cases for control group, got ${cases.length}`)
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
        'rising = >20% increase, falling = >20% decrease, stable = within +/-20%.'
      ),
    },
    confidence: {
      type: 'string',
      enum: ['high', 'medium', 'low'],
    },
    reasoning: {
      type: 'string',
      description: '3-5 sentences. Reference specific prior values and cross-lab clinical signals.',
    },
  },
}

// ─── Run all cases ──────────────────────────────────────────────────────────────

const allResults = []

for (const caseData of cases) {
  const cid = caseData.case_id

  // ── Build FULL EHR context section ──
  const ehr = caseData.full_ehr_context || {}

  const ehrLines = [
    `Patient subject_id: ${caseData.patient_id}`,
    `A ${caseData.demographics.age}-year-old ${caseData.demographics.gender}`,
  ]

  if (ehr.ethnicity) ehrLines.push(`Ethnicity: ${ehr.ethnicity}`)
  if (ehr.race)      ehrLines.push(`Race: ${ehr.race}`)

  if (ehr.diagnoses_enhanced?.length > 0) {
    const dxList = ehr.diagnoses_enhanced.slice(0, 12).map(d => `${d.code} — ${d.description}`).join(', ')
    ehrLines.push(`Diagnoses: ${dxList}`)
  }

  if (ehr.medications_enhanced?.length > 0) {
    const medList = ehr.medications_enhanced.slice(0, 12).map(m => m.name).join('; ')
    ehrLines.push(`Medications: ${medList}`)
  }

  if (ehr.procedures?.length > 0) {
    const procList = ehr.procedures.slice(0, 6).map(p => `${p.code} — ${p.description}`).join('; ')
    ehrLines.push(`Procedures: ${procList}`)
  }

  if (ehr.observations?.length > 0) {
    const obsLines = ehr.observations.map(o => `  - ${o.name}: ${o.value} ${o.unit}`).join('\n')
    ehrLines.push(`Recent observations:\n${obsLines}`)
  }

  if (ehr.visit_history?.length > 0) {
    const visitTypes = [...new Set(ehr.visit_history.map(v => v.type))].join(', ')
    ehrLines.push(`Visit types: ${visitTypes}`)
  }

  ehrLines.push(
    `Troponin I measurements are available up to ${caseData.context_cutoff}.`,
    `Additional labs are available up to ${caseData.question.target_datetime}.`,
    `The next Troponin I is scheduled for ${caseData.question.target_datetime} (${caseData.question.hours_ahead} hours after the last known reading).`
  )

  // ── Build lab tables ──
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

  // ── PubMed toggle (the ONLY difference between conditions) ──
  const toolsLine = _condition === 'control'
    ? `You have access to PubMed MCP tools (mcp__pubmed-server__search_articles, mcp__pubmed-server__get_abstract). You may search for relevant clinical literature before making your prediction.\n\n`
    : ''

  // ── Build prompt ──
  const prompt = `${toolsLine}You are an expert cardiologist and intensivist. You have access to a patient's full EHR record. Predict the next Troponin I value using all available clinical information.

═══════════════════════════════════════════════════════════════
PATIENT — FULL EHR CONTEXT
═══════════════════════════════════════════════════════════════
${ehrLines.join('\n')}

═══════════════════════════════════════════════════════════════
FULL LAB TIMELINE (troponin up to cutoff; other labs up to prediction time)
═══════════════════════════════════════════════════════════════
${labTableMd}

═══════════════════════════════════════════════════════════════
VISIBLE TROPONIN I HISTORY (readings available before the cutoff: ${caseData.context_cutoff})
═══════════════════════════════════════════════════════════════
${troponins.length > 0
  ? troponins.map(t => `  ${t.datetime}: ${t.value} ${t.unit} (${t.flag || 'normal'})`).join('\n')
  : '  No prior Troponin I values in context.'}

═══════════════════════════════════════════════════════════════
GAP-WINDOW LABS (collected after last troponin, up to prediction time)
═══════════════════════════════════════════════════════════════
${gapLabsMd}

═══════════════════════════════════════════════════════════════
PREDICTION TASK
═══════════════════════════════════════════════════════════════
Predict the Troponin I value at: ${caseData.question.target_datetime}
(${caseData.question.hours_ahead} hours after the last known troponin)

Consider:
- Troponin kinetics: STEMI peaks at 12-24h then falls; NSTEMI rises more slowly.
- Cross-lab signals: BNP, creatinine, and other labs in the gap window may indicate
  changes in cardiac injury, clearance, or hemodynamic status.
- Serial delta troponin: >=20% relative change = clinically significant.
- Clinical context: diagnoses, medications, procedures, vitals all inform trajectory.

IMPORTANT: The visible troponin trend may NOT predict the next value.
Cross-lab signals and clinical context are critical for detecting direction changes.

Return your prediction as a JSON object with fields: predicted_value, predicted_unit, direction (rising, falling, stable), confidence, reasoning.`

  // ── Call Ollama ──
  console.log(`--- Case ${cid} [${_condition}] (${caseData.patient_id}) ---`)

  const prediction = await callAgentStructured(
    '',           // no system prompt needed
    prompt,
    PREDICTION_SCHEMA,
    MODEL,
    BASE_URL
  )

  if (!prediction) {
    console.log(`  ERROR: null prediction for case ${cid}`)
    allResults.push({ case_id: cid, error: 'null_prediction', condition: _condition })
    continue
  }

  const score = computeScore(prediction, caseData.ground_truth)

  console.log(`  predicted: ${prediction.predicted_value} ng/mL (${prediction.direction}, conf: ${prediction.confidence}) | score: ${score.score}`)

  allResults.push({
    case_id:        cid,
    patient_id:     caseData.patient_id,
    condition:      _condition,
    prediction,
    ground_truth:   caseData.ground_truth,
    scoring_guide:  caseData.scoring_guide,
    score_result:   score,
  })
}

// ─── Score function ─────────────────────────────────────────────────────────────

function computeScore(pred, gt) {
  let sc = 0
  const dirMatch = pred.direction === gt.direction
  sc += dirMatch ? 0.40 : 0

  const re = gt.value > 0 ? Math.abs(pred.predicted_value - gt.value) / gt.value : 1.0
  const within50 = re <= 0.50
  const within20 = re <= 0.20
  sc += (within50 ? 0.35 : 0) + (within20 ? 0.25 : 0)

  return {
    score:           Math.round(sc * 100) / 100,
    direction_correct: dirMatch,
    relative_error_pct: Math.round(re * 100),
    within_50pct:    within50,
    within_20pct:    within20,
    predicted_value: pred.predicted_value,
    predicted_dir:   pred.direction,
    actual_value:    gt.value,
    actual_dir:      gt.direction,
  }
}

// ─── Aggregate results ──────────────────────────────────────────────────────────

const n = allResults.filter(r => !r.error).length
const scored = allResults.filter(r => r.score_result)
const mean = (arr, key) => arr.length ? arr.reduce((s, x) => s + x[key], 0) / arr.length : 0
const rate = (arr, key) => arr.length ? arr.filter(x => x[key]).length / arr.length : 0

const summary = {
  condition:        CONDITION_LABEL,
  model:            MODEL,
  base_url:         BASE_URL,
  n_cases:          n,
  mean_score:       +mean(scored, 'score').toFixed(3),
  direction_accuracy: +rate(scored, 'direction_correct').toFixed(3),
  within_50pct_rate:  +rate(scored, 'within_50pct').toFixed(3),
  within_20pct_rate:  +rate(scored, 'within_20pct').toFixed(3),
}

console.log(`\n=== ${CONDITION_LABEL} Summary ===`)
console.log(`Model: ${MODEL}`)
console.log(`Cases: ${n}/20`)
console.log(`Mean score:   ${summary.mean_score}`)
console.log(`Dir accuracy: ${(summary.direction_accuracy * 100).toFixed(1)}%`)
console.log(`Within 50%:   ${(summary.within_50pct_rate * 100).toFixed(1)}%`)
console.log(`Within 20%:   ${(summary.within_20pct_rate * 100).toFixed(1)}%`)

// ─── Save results ───────────────────────────────────────────────────────────────

import { writeFileSync } from 'fs'
const output = {
  benchmark:    'cardiac-dirchange-v3',
  condition:    _condition,
  definition:   CONDITION_LABEL,
  model:        MODEL,
  base_url:     BASE_URL,
  n_cases:      n,
  summary,
  per_case: scored,
}

writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2))
console.log(`\nResults saved to ${OUTPUT_PATH}`)

// Also print a compact line for easy comparison
console.log(`\n=== COPY-PASTE LINE ===`)
console.log(`${_condition.padEnd(14)} | model=${MODEL} | mean_score=${summary.mean_score} | dir_acc=${(summary.direction_accuracy*100).toFixed(1)}% | within50=${(summary.within_50pct_rate*100).toFixed(1)}% | within20=${(summary.within_20pct_rate*100).toFixed(1)}%`)
