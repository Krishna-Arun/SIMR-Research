#!/usr/bin/env node
/**
 * Smoke Test: 5 Benchmark A cases × 2 models × 2 conditions
 *
 * Tests:
 * - Benchmark A: Intervention → Physiological Effect (5 cases)
 *   Task: Given pre-intervention labs + procedure, predict post-intervention changes
 *   Evaluates: Direction (↑/↓/→) + Magnitude (% change) for 4 labs
 *   Labs: Troponin T, CK, Creatinine, Potassium
 *
 * Models: qwen3:4b
 * Conditions: with_pubmed, without_pubmed
 *
 * Outputs:
 * - smoke_test_results/a_{model}_{condition}_smoke.json
 * - smoke_test_summary.json (aggregated)
 *
 * After running, review results for:
 * 1. Data leakage (ground truth visible in prompts)
 * 2. Multi-lab predictions (all 4 labs predicted?)
 * 3. Causal justification quality (explains each lab's direction/magnitude)
 * 4. Score sanity (are scores between 0-1?)
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { callAgentStructured } from './ollama_qwen_agent.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// ─── Config ───────────────────────────────────────────────────────────────────

const SCRIPT_DIR = __dirname
const QUESTIONS_DIR = join(SCRIPT_DIR, 'questions')
const SMOKE_RESULTS_DIR = join(SCRIPT_DIR, 'smoke_test_results')
mkdirSync(SMOKE_RESULTS_DIR, { recursive: true })

const BENCHMARKS = [
  { id: 'a', name: 'intervention_physiological_effect', description: 'Intervention → Physiological Effect' },
]

const MODELS = [
  { id: 'qwen3:4b', label: 'Qwen 3 (4B)' },
]

const CONDITIONS = [
  { id: 'with_pubmed', label: 'WITH PubMed', usePubMed: true },
  { id: 'without_pubmed', label: 'WITHOUT PubMed', usePubMed: false },
]

const SMOKE_TEST_SIZE = 5  // 5 cases per benchmark
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'

// ─── Logging ──────────────────────────────────────────────────────────────────

function log(msg) {
  console.log(`[SMOKE] ${msg}`)
}

function logTest(benchmark, model, condition, caseId) {
  console.log(`  → [${benchmark.toUpperCase()}] ${model} ${condition}: case ${caseId}`)
}

// ─── Load cases ───────────────────────────────────────────────────────────────

function loadSmokeTestCases(benchmarkId) {
  const cases = []
  for (let i = 1; i <= SMOKE_TEST_SIZE; i++) {
    const caseId = `${benchmarkId}_${String(i).padStart(3, '0')}`
    const casePath = join(QUESTIONS_DIR, `${caseId}.json`)

    try {
      const content = readFileSync(casePath, 'utf8')
      cases.push({ caseId, path: casePath, data: JSON.parse(content) })
    } catch (err) {
      log(`Warning: Case ${caseId} not found at ${casePath}`)
    }
  }
  return cases
}

// ─── Answer agents (Benchmark A & B) ───────────────────────────────────────────

async function answerBenchmarkA(caseData, usePubMed, model) {
  const systemPrompt = `You are an expert cardiologist with deep knowledge of cardiac physiology.

Given a patient's pre-intervention state and procedure, predict post-intervention lab changes.
Provide direction (rising/falling/stable) and approximate magnitude (% change).
Explain the mechanistic reasoning.`

  const procedure = caseData.procedure
  const question = caseData.question.stem  // Contains the full pre-lab table

  const userPrompt = `
CLINICAL CASE:

${question}

Procedure Performed: ${procedure.title}
Date: ${procedure.date}

Based on the pre-intervention lab trajectory, clinical context, and the procedure performed:

1. Predict the direction of change (rising/falling/stable) for Troponin, CK, Creatinine
2. Estimate the magnitude (% change) for each lab
3. Explain the mechanistic reasoning for EACH lab
${usePubMed ? '4. Reference relevant cardiac physiology or clinical evidence' : ''}

Respond in JSON format with fields:
- troponin_direction: "rising" | "falling" | "stable"
- troponin_magnitude_pct: number (negative for falling)
- ck_direction: "rising" | "falling" | "stable"
- ck_magnitude_pct: number (negative for falling)
- creatinine_direction: "rising" | "falling" | "stable"
- creatinine_magnitude_pct: number (negative for falling)
- causal_justification: string (detailed mechanistic explanation for each lab)
- confidence: "high" | "medium" | "low"
`

  const schema = {
    type: 'object',
    properties: {
      troponin_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      troponin_magnitude_pct: { type: 'number' },
      ck_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      ck_magnitude_pct: { type: 'number' },
      creatinine_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      creatinine_magnitude_pct: { type: 'number' },
      causal_justification: { type: 'string' },
      confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    },
    required: ['troponin_direction', 'troponin_magnitude_pct', 'ck_direction', 'ck_magnitude_pct', 'creatinine_direction', 'creatinine_magnitude_pct', 'causal_justification', 'confidence'],
  }

  try {
    const result = await callAgentStructured(
      systemPrompt,
      userPrompt,
      schema,
      model,
      OLLAMA_BASE_URL,
      usePubMed
    )
    return result
  } catch (err) {
    log(`Error in Benchmark A: ${err.message}`)
    return null
  }
}


// ─── Smoke test runner ────────────────────────────────────────────────────────

async function runSmokeTest() {
  log('Starting smoke test: 5 Benchmark A cases × 2 models × 2 conditions')
  log(`Models: ${MODELS.map(m => m.label).join(', ')}`)
  log(`Conditions: ${CONDITIONS.map(c => c.label).join(', ')}`)
  log('')

  const results = {
    timestamp: new Date().toISOString(),
    config: { smoke_test_size: SMOKE_TEST_SIZE, models: MODELS, conditions: CONDITIONS },
    results: {},
  }

  for (const benchmark of BENCHMARKS) {
    log(`\n[${benchmark.id.toUpperCase()}] ${benchmark.description}`)
    log(`Loading ${SMOKE_TEST_SIZE} cases...`)
    const cases = loadSmokeTestCases(benchmark.id)
    log(`✓ Loaded ${cases.length} cases`)

    for (const model of MODELS) {
      for (const condition of CONDITIONS) {
        const key = `${benchmark.id}_${model.id}_${condition.id}`
        log(`\nRunning: ${model.label} ${condition.label}`)

        const predictions = []

        for (const caseFile of cases) {
          logTest(benchmark.id, model.label, condition.label, caseFile.caseId)

          const prediction = await answerBenchmarkA(caseFile.data, condition.usePubMed, model.id)

          if (prediction) {
            predictions.push({
              case_id: caseFile.caseId,
              hadm_id: caseFile.data.hadm_id,
              procedure: caseFile.data.procedure,
              prediction,
              ground_truth: {
                troponin_direction: caseFile.data.ground_truth?.troponin_direction,
                troponin_magnitude_pct: caseFile.data.ground_truth?.troponin_magnitude_pct,
                ck_direction: caseFile.data.ground_truth?.ck_direction,
                ck_magnitude_pct: caseFile.data.ground_truth?.ck_magnitude_pct,
                creatinine_direction: caseFile.data.ground_truth?.creatinine_direction,
                creatinine_magnitude_pct: caseFile.data.ground_truth?.creatinine_magnitude_pct,
              },
            })
          }
        }

        results.results[key] = {
          benchmark: benchmark.id,
          benchmark_name: benchmark.name,
          model: model.id,
          condition: condition.id,
          n_predictions: predictions.length,
          predictions,
        }

        // Save individual result file
        const resultFile = join(SMOKE_RESULTS_DIR, `${key}_smoke.json`)
        writeFileSync(resultFile, JSON.stringify(results.results[key], null, 2))
        log(`  ✓ Saved: ${resultFile}`)
      }
    }
  }

  // Save summary
  const summaryFile = join(SMOKE_RESULTS_DIR, 'smoke_test_summary.json')
  writeFileSync(summaryFile, JSON.stringify(results, null, 2))
  log(`\n✓ All results saved to ${SMOKE_RESULTS_DIR}`)

  return results
}

// ─── Main ─────────────────────────────────────────────────────────────────────

log('═══════════════════════════════════════════════════════')
log('Causal Cardiac Benchmark A - Smoke Test')
log('═══════════════════════════════════════════════════════')
log(`Models: ${MODELS.map(m => m.id).join(', ')}`)
log(`Base URL: ${OLLAMA_BASE_URL}`)
log('')

runSmokeTest()
  .then(() => {
    log('\n✓ Smoke test complete!')
    log('Next steps:')
    log('1. Check smoke_test_results/ for prediction files')
    log('2. Review for data leakage (ground truth in prompts)')
    log('3. Run: node smoke_test_scoring.mjs')
    log('4. If OK, run: node run_full_evaluation.mjs')
  })
  .catch(err => {
    log(`✗ Smoke test failed: ${err.message}`)
    process.exit(1)
  })
