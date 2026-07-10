/**
 * Ollama-based experiment runner for cardiac-dirchange-v2.
 * Runs answer agents in parallel (up to 5 concurrent) via direct Ollama calls.
 */

import { readFileSync, writeFileSync } from 'fs'
import { callAgentStructured, callAgentText, DEFAULT_MODEL } from './ollama_agent.js'

// ─── Config ───────────────────────────────────────────────────────────────────

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v2/output/cardiac_dirchange_v2_benchmark_v1.json'
const MODEL = process.env.OLLAMA_MODEL || DEFAULT_MODEL
const CONCURRENCY = 5 // cases running at once

// ─── Parse args ───────────────────────────────────────────────────────────────

const rawArgs = process.argv.slice(2)
let caseIds = []

for (let i = 0; i < rawArgs.length; i++) {
  if (rawArgs[i] === '--case_id' && i + 1 < rawArgs.length) {
    caseIds = [Number(rawArgs[i + 1])]
  }
  if (rawArgs[i] === '--case_ids' && i + 1 < rawArgs.length) {
    caseIds = rawArgs[i + 1].split(',').map(Number)
  }
}

if (caseIds.length === 0) {
  const argsFile = process.env.ARGS_FILE
  if (argsFile) {
    try { caseIds = JSON.parse(readFileSync(argsFile, 'utf8')).case_ids || [] } catch {}
  }
}

const benchmarkData = JSON.parse(readFileSync(BENCHMARK_PATH, 'utf8'))
if (caseIds.length === 0) caseIds = benchmarkData.cases.map(c => c.case_id)

const reversalTypeMap = {}
for (const c of benchmarkData.cases) reversalTypeMap[c.case_id] = c.reversal_type

log(`Running ${caseIds.length} direction-change cases via Ollama (${MODEL}) ...`)

function log(msg) {
  console.log(`[EXP] ${msg}`)
}

// ─── Prediction schema ──────────────────────────────────────────────────────

const PREDICTION_SCHEMA = {
  type: 'object',
  required: ['predicted_value', 'predicted_unit', 'direction', 'confidence', 'reasoning'],
  properties: {
    predicted_value: { type: 'number', description: 'Numeric Troponin I value in ng/mL' },
    predicted_unit: { type: 'string', description: 'Unit of the predicted value (should be ng/mL)' },
    direction: { type: 'string', enum: ['rising', 'falling', 'stable'], description: 'rising=+20%, falling=-20%, stable=±20%' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    reasoning: { type: 'string', description: '3-5 sentences referencing specific values.' },
  },
}

// ─── Run a single case ─────────────────────────────────────────────────────

function runCase(caseId) {
  const caseData = benchmarkData.cases.find(c => c.case_id === caseId)
  if (!caseData) return Promise.resolve({ case_id: caseId, error: 'case not found', reversal_type: reversalTypeMap[caseId] })

  const troponins = caseData.lab_timeline.filter(l => l.label === 'Troponin I' && !l.in_gap)
  const labTableMd = [
    '| Datetime | Lab | Value | Unit | Flag |', '|---|---|---|---|---|',
    ...caseData.lab_timeline.map(l => `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} | ${l.flag || ''} |`),
  ].join('\n')

  const gapLabs = caseData.lab_timeline.filter(l => l.in_gap)
  const gapLabsMd = gapLabs.length > 0
    ? ['| Datetime | Lab | Value | Unit | Flag |', '|---|---|---|---|---|',
        ...gapLabs.map(l => `| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} | ${l.flag || ''} |`)].join('\n')
    : '  (no gap-window cross-lab signals)'

  const prompt = `You are an expert cardiologist. This is a DIRECTION-CHANGE prediction task — the visible troponin trend REVERSES at the target time. Use cross-lab gap signals to detect this.

PATIENT: ${caseData.question.stem}

FULL LAB TIMELINE:
${labTableMd}

TROPONIN I (visible up to: ${caseData.context_cutoff}):
${troponins.length > 0 ? troponins.map(t => `  ${t.datetime}: ${t.value} ${t.unit}`).join('\n') : '  No prior Troponin I.'}
Visible trend: ${caseData.question.visible_trend}

GAP-WINDOW CROSS-LAB (between cutoff and target):
${gapLabsMd}

PREDICT Troponin I at: ${caseData.question.target_datetime} (${caseData.question.hours_ahead}h after last known)

Return ONLY a JSON object: {"predicted_value": <number>, "predicted_unit": "<string>", "direction": "<rising|falling|stable>", "confidence": "<high|medium|low>", "reasoning": "<3-5 sentences>"}
Do NOT include markdown fences. Return raw JSON only.`

  return callAgentStructured(prompt, '', PREDICTION_SCHEMA, MODEL)
    .then(pred => {
      if (!pred || typeof pred.predicted_value !== 'number') throw new Error('Invalid prediction: ' + JSON.stringify(pred).slice(0, 200))
      log(`✓ Case ${caseId} (${reversalTypeMap[caseId]}): predicted ${pred.predicted_value} [${pred.direction}] conf=${pred.confidence}`)
      return { case_id: caseId, patient_id: caseData.patient_id, reversal_type: reversalTypeMap[caseId], prediction: pred, ground_truth: caseData.ground_truth, scoring_guide: caseData.scoring_guide }
    })
    .catch(err => {
      log(`✗ Case ${caseId}: ${err.message}`)
      return { case_id: caseId, error: err.message, reversal_type: reversalTypeMap[caseId] }
    })
}

// ─── Parallel run with concurrency limit ──────────────────────────────────

function poolRun(tasks, concurrency) {
  const results = []
  let nextIdx = 0

  async function worker() {
    while (nextIdx < tasks.length) {
      const idx = nextIdx++
      results[idx] = await tasks[idx]()
    }
  }

  return Promise.all(Array.from({ length: Math.min(concurrency, tasks.length) }, () => worker())).then(() => results)
}

// ─── Phase 1: Predict ──────────────────────────────────────────────────────

console.log('\n=== Phase 1: Predict via Ollama ===')

const allTasks = caseIds.map(cid => () => runCase(cid))

let lastTotal = 0
function progress() {
  const done = results.filter(r => r).length + failed
  if (done > lastTotal) {
    log(`Progress: ${done}/${caseIds.length} done (${failed} failed, ${done - failed} valid)`)
    lastTotal = done
  }
}

let failed = 0
const results = await poolRun(allTasks, CONCURRENCY)
results.forEach(r => { if (r && r.error) failed++ })

// Also check for null/invalid from the catch
for (let i = 0; i < results.length; i++) {
  if (!results[i]) { failed++; log(`✗ Case ${caseIds[i]}: null result`) }
}

log(`Phase 1 complete: ${results.filter(r => r && !r.error).length}/${caseIds.length} valid, ${failed} failed`)

// ─── Phase 2: Score ──────────────────────────────────────────────────────

console.log('\n=== Phase 2: Score ===')

function scoreCase(r) {
  if (!r || r.error || !r.prediction || !r.ground_truth) return null
  const p = r.prediction, t = r.ground_truth, actual = t.value, predicted = p.predicted_value
  let sc = 0, b = {}

  const dm = p.direction === t.direction; b.dir_correct = dm; b.dir_score = dm ? 0.40 : 0; sc += b.dir_score
  const re = actual > 0 ? Math.abs(predicted - actual) / actual : 1.0; b.err_pct = Math.round(re * 100)
  const w50 = re <= 0.50; b.within_50pct = w50; b.w50_score = w50 ? 0.35 : 0; sc += b.w50_score
  const w20 = re <= 0.20; b.within_20pct = w20; b.w20_score = w20 ? 0.25 : 0; sc += b.w20_score
  b.total = Math.round(sc * 100) / 100

  return { case_id: r.case_id, patient_id: r.patient_id, reversal_type: r.reversal_type, visible_trend: t.visible_trend || '', predicted_value: predicted, predicted_dir: p.direction, actual_value: actual, actual_dir: t.direction, confidence: p.confidence, score: b.total, breakdown: b }
}

const scored = results.filter(Boolean).map(scoreCase).filter(Boolean)

// ─── Phase 3: Summarize ────────────────────────────────────────────────

console.log('\n=== Phase 3: Summary (via Ollama) ===')

const tableMd = [
  '| Case | Patient | Reversal Type | Vis Trend | Pred Dir | True Dir | ✓ | Err% | Score |',
  '|---|---|---|---|---|---|---|---|---|',
  ...scored.map(s => `| ${s.case_id} | ${s.patient_id} | ${s.reversal_type} | ${s.visible_trend} | ${s.predicted_dir} | ${s.actual_dir} | ${s.breakdown.dir_correct ? '✓' : '✗'} | ${s.breakdown.err_pct}% | ${s.score} |`),
].join('\n')

const summaryText = await callAgentText(
  'Return valid JSON only. No markdown fences.',
  `Compute stats for these ${scored.length} cardiac direction-change prediction results (max score 1.0).\n\n${JSON.stringify(scored, null, 2)}\n\nReturn ONLY: {"mean_score": <num>, "direction_accuracy": <0-1>, "within_50pct_rate": <0-1>, "within_20pct_rate": <0-1>, "analysis": "<4-6 sentences>"}`,
  MODEL)

let summary
try {
  summary = JSON.parse(summaryText.replace(/^```[a-zA-Z]*\n?/, '').replace(/\n?```$/, '').trim())
} catch {
  log('Warning: Ollama summary parse failed')
  summary = {}
}

const n = scored.length || 1
summary.mean_score = (summary.mean_score || scored.reduce((s, r) => s + r.score, 0) / n)
summary.direction_accuracy = (summary.direction_accuracy || scored.filter(r => r.breakdown.dir_correct).length / n)
summary.within_50pct_rate = (summary.within_50pct_rate || scored.filter(r => r.breakdown.within_50pct).length / n)
summary.within_20pct_rate = (summary.within_20pct_rate || scored.filter(r => r.breakdown.within_20pct).length / n)

// ─── Output ──────────────────────────────────────────────────────

console.log('\n' + '='.repeat(60))
log('RESULTS')
console.log('='.repeat(60))
if (tableMd) console.log(tableMd)
console.log(`\nMean score: ${summary.mean_score.toFixed(3)} / 1.0`)
console.log(`Direction accuracy: ${(summary.direction_accuracy * 100).toFixed(1)}% (random baseline ~33%)`)
console.log(`Within 50%: ${(summary.within_50pct_rate * 100).toFixed(1)}%`)
console.log(`Within 20%: ${(summary.within_20pct_rate * 100).toFixed(1)}%`)

const outputPath = BENCHMARK_PATH.replace('.json', '_ollama_results.json')
writeFileSync(outputPath, JSON.stringify({ benchmark: 'cardiac_dirchange_v2_ollama', model: MODEL, n_cases: n, ...summary, per_case: scored }, null, 2))
console.log(`\nResults saved to ${outputPath}`)
