#!/usr/bin/env node

/**
 * MIMIC Multi-Lab Reversal Benchmark — SMOKE TEST
 *
 * Runs 20 representative test cases to validate:
 * 1. Ollama connection and Qwen inference
 * 2. Confidence extraction from token logits
 * 3. JSON parsing and schema validation
 * 4. Scoring module
 * 5. Results aggregation and reporting
 *
 * MUST PASS before moving to full 500-case evaluation.
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { callQwenStructured } from './models/ollama_qwen_agent.mjs'
import { scoreCase, aggregateScores } from './scoring/score.mjs'

// Paths
const SCRIPT_DIR = import.meta.url.replace('file://', '').split('/').slice(0, -1).join('/')
const CASES_DIR = join(SCRIPT_DIR, 'cases')
const RESULTS_DIR = join(SCRIPT_DIR, 'results')
const SMOKE_RESULTS_FILE = join(RESULTS_DIR, 'smoke_test_results.json')

// Ensure results dir exists
mkdirSync(RESULTS_DIR, { recursive: true })

// Prediction schema
const PREDICTION_SCHEMA = {
  type: 'object',
  required: [
    'troponin_direction', 'troponin_reasoning',
    'ck_direction', 'ck_reasoning',
    'creatinine_direction', 'creatinine_reasoning',
    'overall_reasoning',
  ],
  properties: {
    troponin_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
    troponin_reasoning: { type: 'string', description: 'Patient-specific explanation' },
    ck_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
    ck_reasoning: { type: 'string' },
    creatinine_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
    creatinine_reasoning: { type: 'string' },
    overall_reasoning: { type: 'string', description: 'How these labs together reflect this patient\'s post-intervention state' },
  },
}

/**
 * System prompt for cardiologist reasoning.
 */
function buildSystemPrompt() {
  return `You are an expert cardiologist with deep knowledge of cardiac physiology and post-intervention recovery.

Your task: Given a patient's pre-intervention state, procedure details, and visible lab trends, predict what will happen to key cardiac biomarkers at the target time.

For EACH lab (Troponin, CK, Creatinine), you must:
1. Predict direction: rising, falling, or stable
2. Explain the mechanism using THIS PATIENT's specific factors:
   - Age and baseline kidney function (CKD?)
   - Prior medical history (prior MI? diabetes?)
   - Procedure type and contrast exposure
   - Timeline expectations (when do peaks occur?)

Focus on PATIENT-SPECIFIC reasoning, not generic patterns. A prediction saying "PTCA causes troponin to fall" is too generic. A good prediction explains WHY it falls for THIS particular patient given their age, kidney function, and prior history.

Respond in JSON format with troponin_direction, troponin_reasoning, ck_direction, ck_reasoning, creatinine_direction, creatinine_reasoning, and overall_reasoning.`
}

/**
 * Load smoke test cases.
 */
function loadSmokeTestCases() {
  try {
    const casesPath = join(CASES_DIR, 'smoke_test_cases.json')
    const content = readFileSync(casesPath, 'utf8')
    return JSON.parse(content)
  } catch (err) {
    console.error('Failed to load smoke test cases:', err.message)
    process.exit(1)
  }
}

/**
 * Run prediction on a single case.
 */
async function runCase(caseData) {
  console.log(`\nRunning: ${caseData.case_id} (${caseData.phase})`)

  try {
    const result = await callQwenStructured(
      buildSystemPrompt(),
      caseData.case_question,
      PREDICTION_SCHEMA,
      { model: 'qwen3.6:latest', temperature: 0 }
    )

    const { prediction, _confidence, _metadata } = result

    // Score the prediction
    const scoring = scoreCase(prediction, caseData.ground_truth, _confidence)

    console.log(`  ✓ Direction accuracy: ${scoring.direction_accuracy}`)
    console.log(`  ✓ Reversal detection: ${scoring.reversal_detection}`)
    console.log(`  ✓ Justification: ${scoring.causal_justification}`)
    console.log(`  ✓ Total score: ${scoring.total_score}`)

    if (_confidence) {
      console.log(`  ✓ Confidence: ${_confidence.confidence_level} (score: ${_confidence.confidence_score})`)
    }

    return {
      case_id: caseData.case_id,
      phase: caseData.phase,
      prediction,
      confidence: _confidence,
      metadata: _metadata,
      scoring,
      success: true,
    }
  } catch (err) {
    console.error(`  ✗ Error: ${err.message}`)
    return {
      case_id: caseData.case_id,
      phase: caseData.phase,
      error: err.message,
      success: false,
    }
  }
}

/**
 * Main smoke test runner.
 */
async function main() {
  console.log('═══════════════════════════════════════════════════════')
  console.log('MIMIC MULTI-LAB REVERSAL BENCHMARK — SMOKE TEST')
  console.log('═══════════════════════════════════════════════════════')

  const cases = loadSmokeTestCases()
  console.log(`\nLoaded ${cases.length} smoke test cases`)
  console.log(`Ollama endpoint: ${process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'}`)
  console.log(`Model: ${process.env.OLLAMA_MODEL || 'qwen:latest'}\n`)

  // Run all cases sequentially to track progress
  const results = []
  let caseNum = 0
  for (const caseData of cases) {
    caseNum++
    console.log(`[${caseNum}/${cases.length}]`, '')
    const result = await runCase(caseData)
    results.push(result)
  }

  // Aggregate results
  const successfulResults = results.filter(r => r.success)
  console.log(`\n\nResults: ${successfulResults.length}/${results.length} successful`)

  if (successfulResults.length > 0) {
    const scoreArray = successfulResults.map(r => r.scoring)
    const aggregated = aggregateScores(scoreArray)

    console.log('\n═══════════════════════════════════════════════════════')
    console.log('AGGREGATE SCORES')
    console.log('═══════════════════════════════════════════════════════')
    console.log(`Cases evaluated: ${aggregated.n_cases}`)
    console.log(`Mean direction accuracy: ${aggregated.mean_direction_accuracy}`)
    console.log(`Mean reversal detection: ${aggregated.mean_reversal_detection}`)
    console.log(`Mean causal justification: ${aggregated.mean_justification}`)
    console.log(`Mean total score: ${aggregated.mean_total_score}`)
    console.log(`\nScore distribution:`)
    console.log(`  Excellent (≥0.85): ${aggregated.score_distribution.excellent}`)
    console.log(`  Good (0.70-0.85): ${aggregated.score_distribution.good}`)
    console.log(`  Fair (0.50-0.70): ${aggregated.score_distribution.fair}`)
    console.log(`  Poor (<0.50): ${aggregated.score_distribution.poor}`)

    // Confidence analysis
    const confidences = successfulResults
      .filter(r => r.confidence)
      .map(r => r.confidence.confidence_score)

    if (confidences.length > 0) {
      const meanConfidence = confidences.reduce((a, b) => a + b, 0) / confidences.length
      console.log(`\nConfidence metrics:`)
      console.log(`  Mean confidence score: ${Math.round(meanConfidence * 1000) / 1000}`)
      console.log(`  High confidence cases: ${successfulResults.filter(r => r.confidence?.confidence_level === 'high').length}`)
      console.log(`  Medium confidence cases: ${successfulResults.filter(r => r.confidence?.confidence_level === 'medium').length}`)
      console.log(`  Low confidence cases: ${successfulResults.filter(r => r.confidence?.confidence_level === 'low').length}`)
    }
  }

  // Save results
  const output = {
    timestamp: new Date().toISOString(),
    test_type: 'smoke_test',
    n_cases: cases.length,
    n_successful: successfulResults.length,
    results: results,
    aggregated_scores: successfulResults.length > 0 ? aggregateScores(successfulResults.map(r => r.scoring)) : null,
  }

  writeFileSync(SMOKE_RESULTS_FILE, JSON.stringify(output, null, 2))
  console.log(`\n\nResults saved to: ${SMOKE_RESULTS_FILE}`)

  // Report pass/fail
  const passed = successfulResults.length === cases.length
  console.log(`\n${passed ? '✓ SMOKE TEST PASSED' : '✗ SMOKE TEST FAILED'}`)

  process.exit(passed ? 0 : 1)
}

main().catch(err => {
  console.error('Fatal error:', err)
  process.exit(1)
})
