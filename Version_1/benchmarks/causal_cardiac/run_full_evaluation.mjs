#!/usr/bin/env node
/**
 * Causal Cardiac Benchmark Evaluation
 *
 * Runs 100 cases for Benchmark A × 2 models × 2 conditions
 *
 * Matrix:
 * - Benchmark: A (Intervention→Effect)
 * - Models: qwen3.6, qwen3.4b
 * - Conditions: with_pubmed, without_pubmed
 *
 * Total predictions: 1 benchmark × 2 models × 2 conditions × 100 cases = 400 predictions
 *
 * Output:
 * - results/{benchmark}_{model}_{condition}_results.json
 * - scored_results/{benchmark}_{model}_{condition}_scored.json
 * - final_summary.json (comparison across models/conditions)
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
const RESULTS_DIR = join(SCRIPT_DIR, 'results_full')
const SCORED_DIR = join(SCRIPT_DIR, 'scored_results_full')

mkdirSync(RESULTS_DIR, { recursive: true })
mkdirSync(SCORED_DIR, { recursive: true })

const BENCHMARKS = [
  { id: 'a', name: 'intervention_physiological_effect' },
]

const MODELS = [
  'qwen3.6:latest',
  'qwen3.4b:latest',
]

const CONDITIONS = [
  { id: 'with_pubmed', label: 'WITH PubMed', usePubMed: true },
  { id: 'without_pubmed', label: 'WITHOUT PubMed', usePubMed: false },
]

const CASES_PER_BENCHMARK = 100
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'
const CONCURRENCY = parseInt(process.env.CONCURRENCY || '2')

// ─── Logging ──────────────────────────────────────────────────────────────────

function log(msg) {
  console.log(`[EVAL] ${new Date().toISOString().split('T')[1]} ${msg}`)
}

// ─── Load cases ───────────────────────────────────────────────────────────────

function loadCases(benchmarkId) {
  const cases = []
  for (let i = 1; i <= CASES_PER_BENCHMARK; i++) {
    const caseId = `${benchmarkId}_${String(i).padStart(3, '0')}`
    const casePath = join(QUESTIONS_DIR, `${caseId}.json`)

    try {
      const content = readFileSync(casePath, 'utf8')
      cases.push({ caseId, path: casePath, data: JSON.parse(content) })
    } catch (err) {
      // Silently skip missing cases
    }
  }
  return cases
}

// ─── Answer agents ────────────────────────────────────────────────────────────

async function answerBenchmarkA(caseData, usePubMed, model) {
  const systemPrompt = `You are an expert cardiologist with deep knowledge of cardiac physiology.

Given a patient's pre-intervention state and procedure, predict post-intervention lab changes.
Provide direction (rising/falling/stable) and approximate magnitude (% change).
Explain the mechanistic reasoning.`

  const preState = caseData.pre_intervention_state
  const procedure = caseData.procedure

  const userPrompt = `
Pre-intervention labs:
- Troponin I: ${preState.troponin} ng/mL
- CK: ${preState.ck} U/L
- BP: ${preState.systolic_bp}/${preState.diastolic_bp} mmHg
${preState.bnp ? `- BNP: ${preState.bnp} pg/mL` : ''}
${preState.creatinine ? `- Creatinine: ${preState.creatinine} mg/dL` : ''}

Procedure performed: ${procedure.name}
${procedure.details ? `Details: ${procedure.details}` : ''}

Predict the NEXT troponin I measurement (24-48h post-intervention):
1. Direction (rising/falling/stable)
2. Magnitude (% change from baseline)
3. Mechanistic explanation
${usePubMed ? '4. Reference to relevant physiology or clinical evidence' : ''}

Respond in JSON format with fields:
- troponin_direction: "rising" | "falling" | "stable"
- troponin_magnitude_pct: number (negative for falling)
- ck_direction: "rising" | "falling" | "stable"
- creatinine_direction: "rising" | "falling" | "stable"
- causal_justification: string
- confidence: number (0.0-1.0)
`

  const schema = {
    type: 'object',
    properties: {
      troponin_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      troponin_magnitude_pct: { type: 'number' },
      ck_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      creatinine_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      causal_justification: { type: 'string' },
      confidence: { type: 'number', minimum: 0, maximum: 1 },
    },
    required: ['troponin_direction', 'troponin_magnitude_pct', 'causal_justification', 'confidence'],
  }

  try {
    return await callAgentStructured(systemPrompt, userPrompt, schema, model, OLLAMA_BASE_URL, usePubMed)
  } catch (err) {
    return null
  }
}

async function answerBenchmarkB(caseData, usePubMed, model) {
  const systemPrompt = `You are an expert cardiologist.

Given pre and post-intervention lab changes (without knowing the procedure),
select which procedures were performed from the list of candidates.
For each procedure, provide your confidence level.`

  const preState = caseData.pre_intervention_state
  const postState = caseData.post_intervention_state
  const candidates = caseData.candidate_procedures || []

  const userPrompt = `
Pre-intervention labs:
- Troponin I: ${preState.troponin} ng/mL
- CK: ${preState.ck} U/L
- BP: ${preState.systolic_bp}/${preState.diastolic_bp} mmHg
${preState.bnp ? `- BNP: ${preState.bnp} pg/mL` : ''}

Post-intervention labs:
- Troponin I: ${postState.troponin} ng/mL
- CK: ${postState.ck} U/L
- BP: ${postState.systolic_bp}/${postState.diastolic_bp} mmHg
${postState.bnp ? `- BNP: ${postState.bnp} pg/mL` : ''}

Candidate procedures (select all that apply):
${candidates.map((p, i) => `${i + 1}. ${p}`).join('\n')}

Task: Which procedures were ACTUALLY performed?
For each, provide:
1. Whether it was done (true/false)
2. Your confidence (0.0-1.0)

Explain your reasoning: which lab changes point to which procedures?
${usePubMed ? 'Reference relevant cardiac physiology or clinical evidence.' : ''}

Respond in JSON format:
{
  "selected_procedures": [
    {"name": "string", "selected": boolean, "confidence": number}
  ],
  "causal_justification": "string",
  "per_procedure_reasoning": {
    "procedure_name": "explanation"
  }
}
`

  const schema = {
    type: 'object',
    properties: {
      selected_procedures: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            selected: { type: 'boolean' },
            confidence: { type: 'number', minimum: 0, maximum: 1 },
          },
          required: ['name', 'selected', 'confidence'],
        },
      },
      causal_justification: { type: 'string' },
      per_procedure_reasoning: { type: 'object' },
    },
    required: ['selected_procedures', 'causal_justification'],
  }

  try {
    return await callAgentStructured(systemPrompt, userPrompt, schema, model, OLLAMA_BASE_URL, usePubMed)
  } catch (err) {
    return null
  }
}

// ─── Batch processing with concurrency control ────────────────────────────────

async function processBatch(cases, benchmark, model, condition, usePubMed) {
  const predictions = []
  const batchSize = CONCURRENCY

  for (let i = 0; i < cases.length; i += batchSize) {
    const batch = cases.slice(i, i + batchSize)
    const batchPromises = batch.map(async caseFile => {
      let prediction = null

      if (benchmark === 'a') {
        prediction = await answerBenchmarkA(caseFile.data, usePubMed, model)
      } else {
        prediction = await answerBenchmarkB(caseFile.data, usePubMed, model)
      }

      return {
        case_id: caseFile.caseId,
        prediction,
        ground_truth: {
          expected_troponin_direction: caseFile.data.ground_truth?.expected_troponin_direction,
          expected_troponin_magnitude_pct: caseFile.data.ground_truth?.expected_troponin_magnitude_pct,
          actual_procedures: caseFile.data.ground_truth?.actual_procedures,
        },
      }
    })

    const results = await Promise.all(batchPromises)
    predictions.push(...results)

    const progress = Math.min(i + batchSize, cases.length)
    log(`  ${benchmark.toUpperCase()} ${model} ${condition}: ${progress}/${cases.length} cases`)
  }

  return predictions
}

// ─── Main evaluation ──────────────────────────────────────────────────────────

async function runFullEvaluation() {
  log('='​.repeat(70))
  log('FULL CAUSAL CARDIAC BENCHMARK EVALUATION')
  log('='​.repeat(70))
  log(`Models: ${MODELS.join(', ')}`)
  log(`Conditions: ${CONDITIONS.map(c => c.label).join(', ')}`)
  log(`Concurrency: ${CONCURRENCY}`)
  log('')

  const startTime = Date.now()
  const allResults = {}

  for (const benchmark of BENCHMARKS) {
    log(`\n[BENCHMARK ${benchmark.id.toUpperCase()}] Loading ${CASES_PER_BENCHMARK} cases...`)
    const cases = loadCases(benchmark.id)
    log(`  Loaded ${cases.length} cases`)

    for (const model of MODELS) {
      for (const condition of CONDITIONS) {
        const key = `${benchmark.id}_${model.replace(':latest', '')}_${condition.id}`
        log(`\n${key}:`)

        const predictions = await processBatch(cases, benchmark.id, model, condition.label, condition.usePubMed)

        allResults[key] = {
          benchmark: benchmark.id,
          model,
          condition: condition.id,
          n_predictions: predictions.length,
          predictions,
        }

        // Save result file
        const resultFile = join(RESULTS_DIR, `${key}_results.json`)
        writeFileSync(resultFile, JSON.stringify(allResults[key], null, 2))
        log(`  ✓ Saved: ${resultFile}`)
      }
    }
  }

  const endTime = Date.now()
  const duration = Math.round((endTime - startTime) / 1000)

  // Save all results
  const allResultsFile = join(RESULTS_DIR, 'all_results.json')
  writeFileSync(allResultsFile, JSON.stringify(allResults, null, 2))
  log(`\n✓ All results: ${allResultsFile}`)

  log('\n' + '='.repeat(70))
  log(`EVALUATION COMPLETE`)
  log(`Duration: ${duration}s`)
  log(`Total predictions: ${Object.values(allResults).reduce((sum, r) => sum + r.n_predictions, 0)}`)
  log('='.repeat(70))
  log('\nNext: node full_evaluation_scoring.mjs')
}

runFullEvaluation().catch(err => {
  log(`✗ Evaluation failed: ${err.message}`)
  process.exit(1)
})
