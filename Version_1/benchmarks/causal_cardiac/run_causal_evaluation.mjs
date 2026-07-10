#!/usr/bin/env node
/**
 * Causal Cardiac Benchmark Evaluation Runner
 *
 * Runs Benchmark A (Intervention→Physiological Effect)
 * across 100 cases with Qwen 3.6 via Ollama.
 *
 * Two conditions:
 * 1. WITH PubMed MCP (optional external knowledge)
 * 2. WITHOUT PubMed MCP (reasoning from case context only)
 *
 * Output: results/a_{condition}_results.json per combination
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { callAgentStructured, callAgentText } from './ollama_qwen_agent.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// ─── Config ───────────────────────────────────────────────────────────────────

const SCRIPT_DIR = __dirname
const QUESTIONS_DIR = join(SCRIPT_DIR, 'questions')
const RESULTS_DIR = join(SCRIPT_DIR, 'results')
mkdirSync(RESULTS_DIR, { recursive: true })

const BENCHMARKS = [
  { id: 'a', name: 'intervention_physiological_effect', description: 'Intervention → Physiological Effect' },
]

const CONDITIONS = [
  { id: 'with_pubmed', label: 'WITH PubMed', usePubMed: true },
  { id: 'without_pubmed', label: 'WITHOUT PubMed', usePubMed: false },
]

const MODEL = process.env.OLLAMA_MODEL || 'qwen3.6:latest'
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'
const CONCURRENCY = 5

// ─── Logging ──────────────────────────────────────────────────────────────────

function log(msg) {
  console.log(`[EVAL] ${msg}`)
}

// ─── Load cases ───────────────────────────────────────────────────────────────

function loadCases(benchmarkId) {
  const caseFiles = []

  for (let i = 1; i <= 100; i++) {
    const caseId = `${benchmarkId}_${String(i).padStart(3, '0')}`
    const casePath = join(QUESTIONS_DIR, `${caseId}.json`)

    try {
      const content = readFileSync(casePath, 'utf8')
      caseFiles.push({ caseId, path: casePath, data: JSON.parse(content) })
    } catch (err) {
      log(`Warning: Case ${caseId} not found at ${casePath}`)
    }
  }

  return caseFiles
}

// ─── Answer agents ────────────────────────────────────────────────────────────

async function answerBenchmarkA(caseData, usePubMed) {
  /**
   * Benchmark A: Intervention → Physiological Effect
   * Given pre-intervention state and procedure, predict post-intervention lab changes.
   * Output: expected direction + magnitude for key biomarkers
   */
  const systemPrompt = `You are an expert cardiologist with deep knowledge of cardiac physiology and intervention outcomes.

Your task: Given a patient's pre-intervention clinical state and a specific procedure, predict what physiological changes (lab value direction/magnitude) you would expect in the post-intervention period.

Focus on:
1. Direction of change (rising/falling/stable) for key cardiac biomarkers
2. Expected magnitude (% change) based on mechanism of intervention
3. Timeline of expected changes
4. Pathophysiological rationale

Provide structured output with predicted changes for Troponin T, CK, Creatinine.`

  const schema = {
    type: 'object',
    required: ['troponin_direction', 'troponin_magnitude_pct', 'ck_direction', 'ck_magnitude_pct', 'creatinine_direction', 'creatinine_magnitude_pct', 'causal_justification', 'confidence'],
    properties: {
      troponin_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      troponin_magnitude_pct: { type: 'number', description: 'Expected % change in Troponin T' },
      ck_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      ck_magnitude_pct: { type: 'number', description: 'Expected % change in CK' },
      creatinine_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
      creatinine_magnitude_pct: { type: 'number', description: 'Expected % change in Creatinine' },
      causal_justification: { type: 'string', description: 'Detailed explanation of the physiological mechanism and predicted changes for each lab' },
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
    log(`Error answering benchmark A: ${err.message}`)
    return null
  }
}


// ─── Confidence Statistics ────────────────────────────────────────────────────

function computeConfidenceStats(results) {
  /**
   * Compute aggregate statistics about model confidence and calibration.
   */
  const confidenceScores = results
    .filter(r => r.confidence && r.confidence.score !== null)
    .map(r => r.confidence.score)

  if (confidenceScores.length === 0) {
    return { warning: 'No confidence scores available (logprobs not supported by model)' }
  }

  // Summary stats
  const mean = confidenceScores.reduce((a, b) => a + b, 0) / confidenceScores.length
  const sorted = [...confidenceScores].sort((a, b) => a - b)
  const median = sorted.length % 2 === 0
    ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
    : sorted[Math.floor(sorted.length / 2)]

  const variance = confidenceScores.reduce((sum, x) => sum + Math.pow(x - mean, 2), 0) / confidenceScores.length
  const stddev = Math.sqrt(variance)

  // Confidence distribution
  const distribution = {
    high: results.filter(r => r.confidence?.categorical === 'high').length,
    medium: results.filter(r => r.confidence?.categorical === 'medium').length,
    low: results.filter(r => r.confidence?.categorical === 'low').length,
  }

  return {
    n_scored: confidenceScores.length,
    mean_confidence: Math.round(mean * 1000) / 1000,
    median_confidence: Math.round(median * 1000) / 1000,
    std_confidence: Math.round(stddev * 1000) / 1000,
    min_confidence: Math.round(Math.min(...confidenceScores) * 1000) / 1000,
    max_confidence: Math.round(Math.max(...confidenceScores) * 1000) / 1000,
    distribution,
    note: 'Confidence scores extracted from token logits/probabilities. Higher = more confident.',
  }
}

// ─── Run single case ──────────────────────────────────────────────────────────

async function runCase(caseData, usePubMed) {
  try {
    const result = await answerBenchmarkA(caseData, usePubMed)

    if (!result) throw new Error('No result from agent')

    // Extract confidence metadata from result
    const metadata = result._metadata || {}
    const confidence = result._confidence || {}

    // Remove internal metadata fields before returning
    const prediction = { ...result }
    delete prediction._metadata
    delete prediction._confidence

    return {
      case_id: caseData.case_id,
      hadm_id: caseData.hadm_id,
      prediction: prediction,
      confidence: {
        categorical: confidence.confidence_level || 'unknown',
        score: confidence.confidence_score || null,
        logprob_avg: confidence.average_logprob || null,
        entropy: confidence.average_entropy || null,
        n_tokens: confidence.n_tokens || null,
      },
      metadata: {
        model: metadata.model,
        finish_reason: metadata.finish_reason,
        usage: metadata.usage,
      },
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

// ─── Parallel executor ────────────────────────────────────────────────────────

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

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  log(`Starting causal cardiac evaluation`)
  log(`Model: ${MODEL}`)
  log(`Ollama endpoint: ${OLLAMA_BASE_URL}`)
  log(`Concurrency: ${CONCURRENCY}`)

  for (const benchmark of BENCHMARKS) {
    log(`\n=== Loading Benchmark ${benchmark.id.toUpperCase()}: ${benchmark.description} ===`)

    const cases = loadCases(benchmark.id)
    log(`Loaded ${cases.length} cases`)

    for (const condition of CONDITIONS) {
      log(`\n--- Running condition: ${condition.label} ---`)

      const tasks = cases.map(c => () => runCase(c.data, condition.usePubMed))
      const results = await poolRun(tasks, CONCURRENCY)

      // Summarize results
      const successful = results.filter(r => r && r.success).length
      const failed = results.filter(r => r && !r.success).length

      log(`Completed ${benchmark.id} + ${condition.id}: ${successful} successful, ${failed} failed`)

      // Compute confidence statistics
      const validResults = results.filter(r => r && r.success)
      const confidenceStats = computeConfidenceStats(validResults)

      // Write results
      const resultsFile = join(RESULTS_DIR, `${benchmark.id}_${condition.id}_results.json`)
      const output = {
        benchmark: benchmark.name,
        condition: condition.label,
        model: MODEL,
        n_cases: cases.length,
        successful,
        failed,
        timestamp: new Date().toISOString(),
        confidence_statistics: confidenceStats,
        results: results.filter(r => r), // Remove nulls
      }

      writeFileSync(resultsFile, JSON.stringify(output, null, 2))
      log(`Wrote results to ${resultsFile}`)
    }
  }

  log(`\n=== Evaluation complete ===`)
  log(`Results saved to ${RESULTS_DIR}`)
}

main().catch(err => {
  console.error('Fatal error:', err)
  process.exit(1)
})
