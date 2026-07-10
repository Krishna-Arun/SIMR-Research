#!/usr/bin/env node
/**
 * Smoke Test Evaluation for Causal Cardiac Benchmarks
 *
 * Runs first 5 cases of each benchmark × both conditions (total 20 cases)
 * to verify the pipeline works before running the full 400-case evaluation.
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
const RESULTS_DIR = join(SCRIPT_DIR, 'results')
mkdirSync(RESULTS_DIR, { recursive: true })

const BENCHMARKS = [
  { id: 'a', name: 'intervention_physiological_effect' },
  { id: 'b', name: 'physiological_intervention_attribution' },
]

const CONDITIONS = [
  { id: 'with_pubmed', label: 'WITH PubMed', usePubMed: true },
  { id: 'without_pubmed', label: 'WITHOUT PubMed', usePubMed: false },
]

const MODEL = process.env.OLLAMA_MODEL || 'qwen3.6:latest'
// Get correct Ollama endpoint from environment or detect from running process
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:55632/v1'
const CONCURRENCY = 2 // Smoke test uses lower concurrency

function log(msg) {
  console.log(`[SMOKE] ${msg}`)
}

function loadCases(benchmarkId, maxCases = 5) {
  const caseFiles = []

  for (let i = 1; i <= maxCases; i++) {
    const caseId = `${benchmarkId}_${String(i).padStart(3, '0')}`
    const casePath = join(QUESTIONS_DIR, `${caseId}.json`)

    try {
      const content = readFileSync(casePath, 'utf8')
      caseFiles.push({ caseId, path: casePath, data: JSON.parse(content) })
    } catch (err) {
      // Silently skip missing cases in smoke test
    }
  }

  return caseFiles
}

async function answerBenchmarkA(caseData, usePubMed) {
  const systemPrompt = `You are an expert cardiologist. Given a patient's pre-intervention state and procedure, predict post-intervention lab changes.`

  const schema = {
    type: 'object',
    required: ['troponin_direction', 'troponin_magnitude_pct', 'ck_direction', 'creatinine_direction', 'causal_justification'],
    properties: {
      troponin_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      troponin_magnitude_pct: { type: 'number' },
      ck_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      creatinine_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      potassium_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      causal_justification: { type: 'string' },
      confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    },
  }

  try {
    const result = await callAgentStructured(
      systemPrompt,
      caseData.question.stem,
      schema,
      MODEL,
      OLLAMA_BASE_URL,
      usePubMed
    )
    return result
  } catch (err) {
    log(`Error on case ${caseData.case_id}: ${err.message}`)
    return null
  }
}

async function answerBenchmarkB(caseData, usePubMed) {
  const systemPrompt = `You are an expert cardiologist. Given pre and post lab changes, infer which procedure was performed.`

  const schema = {
    type: 'object',
    required: ['top_3_procedures', 'causal_justification'],
    properties: {
      top_3_procedures: {
        type: 'array',
        maxItems: 3,
        items: {
          type: 'object',
          required: ['rank', 'procedure_name', 'confidence'],
          properties: {
            rank: { type: 'integer' },
            procedure_name: { type: 'string' },
            confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          },
        },
      },
      causal_justification: { type: 'string' },
    },
  }

  try {
    const result = await callAgentStructured(
      systemPrompt,
      caseData.question.stem,
      schema,
      MODEL,
      OLLAMA_BASE_URL,
      usePubMed
    )
    return result
  } catch (err) {
    log(`Error on case ${caseData.case_id}: ${err.message}`)
    return null
  }
}

async function runCase(caseData, benchmarkId, usePubMed) {
  const isA = benchmarkId === 'a'

  try {
    const result = isA
      ? await answerBenchmarkA(caseData, usePubMed)
      : await answerBenchmarkB(caseData, usePubMed)

    if (!result) return { case_id: caseData.case_id, success: false, error: 'No result' }

    return {
      case_id: caseData.case_id,
      hadm_id: caseData.hadm_id,
      prediction: result,
      success: true,
    }
  } catch (err) {
    return {
      case_id: caseData.case_id,
      hadm_id: caseData.hadm_id,
      error: err.message,
      success: false,
    }
  }
}

async function poolRun(tasks, concurrency) {
  const results = []
  let nextIdx = 0

  async function worker() {
    while (nextIdx < tasks.length) {
      const idx = nextIdx++
      results[idx] = await tasks[idx]()
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, tasks.length) }, () => worker()))
  return results
}

async function main() {
  log(`Starting smoke test evaluation`)
  log(`Model: ${MODEL}`)
  log(`Ollama endpoint: ${OLLAMA_BASE_URL}`)
  log(`Concurrency: ${CONCURRENCY}`)

  for (const benchmark of BENCHMARKS) {
    log(`\n=== Loading Benchmark ${benchmark.id.toUpperCase()} ===`)

    const cases = loadCases(benchmark.id, 5)
    log(`Loaded ${cases.length} cases`)

    if (cases.length === 0) {
      log(`No cases found for benchmark ${benchmark.id} — skipping`)
      continue
    }

    for (const condition of CONDITIONS) {
      log(`\n--- Running condition: ${condition.label} ---`)

      const tasks = cases.map(c => () => runCase(c.data, benchmark.id, condition.usePubMed))
      const results = await poolRun(tasks, CONCURRENCY)

      const successful = results.filter(r => r && r.success).length
      const failed = results.filter(r => r && !r.success).length

      log(`Completed: ${successful} successful, ${failed} failed`)

      // Write results
      const resultsFile = join(RESULTS_DIR, `smoke_${benchmark.id}_${condition.id}_results.json`)
      const output = {
        benchmark: benchmark.name,
        condition: condition.label,
        model: MODEL,
        is_smoke_test: true,
        n_cases: cases.length,
        successful,
        failed,
        timestamp: new Date().toISOString(),
        results: results.filter(r => r),
      }

      writeFileSync(resultsFile, JSON.stringify(output, null, 2))
      log(`Wrote results to ${resultsFile}`)
    }
  }

  log(`\n=== Smoke test evaluation complete ===`)
}

main().catch(err => {
  console.error('Fatal error:', err)
  process.exit(1)
})
