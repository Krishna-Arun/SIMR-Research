#!/usr/bin/env node
/**
 * Smoke Test Scoring & Data Leakage Detection
 *
 * Scores predictions from smoke_test_results/ and checks for:
 * 1. Data leakage (ground truth values in model responses)
 * 2. Invalid predictions (missing required fields)
 * 3. Score sanity (distributions, calibration)
 *
 * Output: smoke_test_scored.json + data_leakage_report.json
 */

import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'fs'
import { join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = import.meta.url.split('file://')[1].split('/').slice(0, -1).join('/')

const SMOKE_RESULTS_DIR = join(__dirname, 'smoke_test_results')
const SCORED_DIR = join(__dirname, 'smoke_test_scored')
mkdirSync(SCORED_DIR, { recursive: true })

function log(msg) {
  console.log(`[SCORE] ${msg}`)
}

// ─── Data Leakage Detection ───────────────────────────────────────────────────

function checkDataLeakage(prediction, groundTruth, benchmark) {
  const leakage = {
    has_leakage: false,
    issues: [],
  }

  if (benchmark === 'a' && prediction.troponin_magnitude_pct) {
    const predicted = prediction.troponin_magnitude_pct
    const actual = groundTruth.expected_troponin_magnitude_pct

    // Check if predicted value is suspiciously close to ground truth
    if (actual && Math.abs(predicted - actual) < 0.5) {
      leakage.issues.push(
        `Troponin magnitude suspiciously close: predicted ${predicted}, actual ${actual}`
      )
      leakage.has_leakage = true
    }
  }

  if (benchmark === 'b' && prediction.selected_procedures) {
    const selected = new Set(prediction.selected_procedures.filter(p => p.selected).map(p => p.name.toLowerCase()))
    const actual = new Set((groundTruth.actual_procedures || []).map(p => p.toLowerCase()))

    // Perfect match could indicate leakage (though perfect predictions are possible)
    if (selected.size > 0 && selected.size === actual.size) {
      const allMatch = Array.from(selected).every(proc => Array.from(actual).some(a => a.includes(proc)))
      if (allMatch && selected.size >= 3) {
        leakage.issues.push(
          `Perfect procedure match (${selected.size}/${actual.size}): could indicate leakage`
        )
        leakage.has_leakage = true
      }
    }
  }

  return leakage
}

// ─── Benchmark A Scoring ──────────────────────────────────────────────────────

function scoreDirectionAccuracy(prediction, groundTruth) {
  if (!prediction.troponin_direction || !groundTruth.expected_troponin_direction) {
    return 0.0
  }

  if (prediction.troponin_direction === groundTruth.expected_troponin_direction) {
    return 1.0
  }

  if (prediction.ck_direction && groundTruth.expected_ck_direction) {
    if (prediction.ck_direction === groundTruth.expected_ck_direction) {
      return 0.5
    }
  }

  return 0.0
}

function scoreMagnitudeAccuracy(prediction, groundTruth) {
  if (!prediction.troponin_magnitude_pct || !groundTruth.expected_troponin_magnitude_pct) {
    return 0.0
  }

  const predicted = prediction.troponin_magnitude_pct
  const actual = groundTruth.expected_troponin_magnitude_pct

  if ((predicted > 0) !== (actual > 0)) {
    return 0.0
  }

  const absError = Math.abs(predicted - actual)
  const pctError = absError / Math.abs(actual)

  if (pctError <= 0.1) return 1.0
  if (pctError <= 0.2) return 0.75
  if (pctError <= 0.5) return 0.5
  if (pctError <= 1.0) return 0.25
  return 0.0
}

function scoreCausalJustification(justification) {
  if (!justification || typeof justification !== 'string') {
    return 0.0
  }

  const text = justification.toLowerCase()
  const length = justification.length

  if (length < 50) {
    return 0.0
  }

  let score = 0.25

  const hasMechanism = /reperfusion|intervention|procedure|artery|blood flow|perfusion|stent|catheter|restore|reopen/i.test(
    text
  )
  if (hasMechanism) score = 0.5

  const hasBiomarkerLink = /troponin.*(?:increase|decrease|rise|fall|change|wash|clear|washout|decline)/i.test(text)
  if (hasBiomarkerLink) score = 0.75

  const hasSpecifics = /coronary|myocardial|ischemia|perfusion|lad|time|hour|day|minute|48|24|36/i.test(text)
  const hasTimeline = /hour|day|minute|timeline|within|after|post|post-intervention/i.test(text)

  if (hasMechanism && hasBiomarkerLink && (hasSpecifics || hasTimeline)) {
    score = 1.0
  }

  return Math.min(1.0, score)
}

function scoreConfidenceCalibrationA(prediction, directionScore, magnitudeScore) {
  const conf = prediction.confidence || 0.5
  const directionCorrect = directionScore >= 1.0
  const magnitudeGood = magnitudeScore >= 0.75

  if (conf >= 0.7) {
    if (directionCorrect && magnitudeGood) return 1.0
    if (directionCorrect) return 0.75
    if (!directionCorrect && magnitudeScore === 0.0) return 0.0
    return 0.25
  }

  if (conf >= 0.4) {
    return directionCorrect && magnitudeScore >= 0.5 ? 0.5 : 0.25
  }

  return 0.0
}

function scoreBenchmarkA(prediction, groundTruth) {
  const directionScore = scoreDirectionAccuracy(prediction, groundTruth)
  const magnitudeScore = scoreMagnitudeAccuracy(prediction, groundTruth)
  const causalScore = scoreCausalJustification(prediction.causal_justification)
  const confidenceScore = scoreConfidenceCalibrationA(prediction, directionScore, magnitudeScore)

  const totalScore =
    directionScore * 0.4 + magnitudeScore * 0.3 + causalScore * 0.2 + confidenceScore * 0.1

  return {
    direction_accuracy: Math.round(directionScore * 1000) / 1000,
    magnitude_accuracy: Math.round(magnitudeScore * 1000) / 1000,
    causal_justification: Math.round(causalScore * 1000) / 1000,
    confidence_calibration: Math.round(confidenceScore * 1000) / 1000,
    total_score: Math.round(totalScore * 1000) / 1000,
  }
}

// ─── Benchmark B Scoring ──────────────────────────────────────────────────────

function scoreSelectionAccuracy(prediction, groundTruth) {
  if (!prediction.selected_procedures || !groundTruth.actual_procedures) {
    return { precision: 0, recall: 0, f1: 0 }
  }

  const selected = new Set(
    prediction.selected_procedures.filter(p => p.selected).map(p => p.name.toLowerCase())
  )
  const actual = new Set((groundTruth.actual_procedures || []).map(p => p.toLowerCase()))

  let tp = 0
  for (const proc of selected) {
    for (const actualProc of actual) {
      if (proc.includes(actualProc) || actualProc.includes(proc)) {
        tp++
        break
      }
    }
  }

  const fp = selected.size - tp
  const fn = actual.size - tp

  const precision = selected.size > 0 ? tp / selected.size : 0
  const recall = actual.size > 0 ? tp / actual.size : 0
  const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0

  return {
    tp,
    fp,
    fn,
    precision: Math.round(precision * 1000) / 1000,
    recall: Math.round(recall * 1000) / 1000,
    f1: Math.round(f1 * 1000) / 1000,
  }
}

function scorePerProcedureCalibration(prediction, groundTruth) {
  if (!prediction.selected_procedures || !groundTruth.actual_procedures) {
    return 0
  }

  const confidences = []
  const correctnesses = []

  for (const proc of prediction.selected_procedures) {
    const isActual = groundTruth.actual_procedures.some(
      ap => ap.toLowerCase().includes(proc.name.toLowerCase()) ||
      proc.name.toLowerCase().includes(ap.toLowerCase())
    )
    const isCorrect = (proc.selected && isActual) || (!proc.selected && !isActual)

    confidences.push(proc.confidence || 0.5)
    correctnesses.push(isCorrect ? 1.0 : 0.0)
  }

  if (confidences.length < 2) return 0.5

  // Simple correlation: count how many high-confidence items were correct
  const highConfCorrect = confidences.filter((c, i) => c >= 0.7 && correctnesses[i] === 1).length
  const highConfTotal = confidences.filter(c => c >= 0.7).length

  const correlation = highConfTotal > 0 ? highConfCorrect / highConfTotal : 0.5

  if (correlation >= 0.7) return 1.0
  if (correlation >= 0.5) return 0.75
  if (correlation >= 0.25) return 0.5
  if (correlation >= 0.0) return 0.25
  return 0.0
}

function scoreCausalJustificationB(justification) {
  // Same as Benchmark A
  return scoreCausalJustification(justification)
}

function scoreJustificationPrecision(prediction, groundTruth) {
  if (!prediction.per_procedure_reasoning || typeof prediction.per_procedure_reasoning !== 'object') {
    return 0.25 // Generic explanation
  }

  const perProcText = JSON.stringify(prediction.per_procedure_reasoning).toLowerCase()

  const numDistinctReasons = Object.keys(prediction.per_procedure_reasoning).length
  const selectedCount = prediction.selected_procedures.filter(p => p.selected).length

  if (numDistinctReasons === selectedCount && selectedCount >= 2) {
    return 1.0 // Each procedure has its own explanation
  }

  if (numDistinctReasons >= Math.ceil(selectedCount * 0.7)) {
    return 0.75
  }

  if (numDistinctReasons > 0) {
    return 0.5
  }

  return 0.25
}

function scoreBenchmarkB(prediction, groundTruth) {
  const selectionScores = scoreSelectionAccuracy(prediction, groundTruth)
  const causalScore = scoreCausalJustificationB(prediction.causal_justification)
  const precisionScore = scoreJustificationPrecision(prediction, groundTruth)
  const calibrationScore = scorePerProcedureCalibration(prediction, groundTruth)

  const totalScore =
    selectionScores.f1 * 0.4 + causalScore * 0.3 + precisionScore * 0.2 + calibrationScore * 0.1

  return {
    selection_f1: selectionScores.f1,
    selection_precision: selectionScores.precision,
    selection_recall: selectionScores.recall,
    selection_tp_fp_fn: { tp: selectionScores.tp, fp: selectionScores.fp, fn: selectionScores.fn },
    causal_justification: Math.round(causalScore * 1000) / 1000,
    justification_precision: Math.round(precisionScore * 1000) / 1000,
    per_procedure_calibration: Math.round(calibrationScore * 1000) / 1000,
    total_score: Math.round(totalScore * 1000) / 1000,
  }
}

// ─── Main scoring logic ────────────────────────────────────────────────────────

function scoreSmokes() {
  log('Loading smoke test results...')

  const files = readdirSync(SMOKE_RESULTS_DIR).filter(f => f.endsWith('_smoke.json'))
  log(`Found ${files.length} result files`)

  const allScored = {}
  const leakageReport = {
    timestamp: new Date().toISOString(),
    files_checked: [],
  }

  for (const file of files) {
    const filePath = join(SMOKE_RESULTS_DIR, file)
    const content = JSON.parse(readFileSync(filePath, 'utf8'))

    const benchmark = content.benchmark
    const model = content.model
    const condition = content.condition
    const key = `${benchmark}_${model}_${condition}`

    log(`\nScoring ${key}...`)

    const scored = {
      benchmark,
      model,
      condition,
      n_cases: content.predictions.length,
      predictions: [],
      summary: {},
      data_leakage_check: { issues: [] },
    }

    const scores = []

    for (const pred of content.predictions) {
      const caseId = pred.case_id
      const prediction = pred.prediction
      const groundTruth = pred.ground_truth

      // Score based on benchmark
      let caseScore
      if (benchmark === 'a') {
        caseScore = scoreBenchmarkA(prediction, groundTruth)
      } else {
        caseScore = scoreBenchmarkB(prediction, groundTruth)
      }

      // Check for data leakage
      const leakageCheck = checkDataLeakage(prediction, groundTruth, benchmark)

      scored.predictions.push({
        case_id: caseId,
        ...caseScore,
        leakage_detected: leakageCheck.has_leakage,
        leakage_issues: leakageCheck.issues,
      })

      if (leakageCheck.has_leakage) {
        scored.data_leakage_check.issues.push({
          case_id: caseId,
          issues: leakageCheck.issues,
        })
      }

      scores.push(caseScore.total_score)
    }

    // Summary statistics
    scored.summary = {
      mean_score: Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 1000) / 1000,
      median_score: Math.round(scores.sort((a, b) => a - b)[Math.floor(scores.length / 2)] * 1000) / 1000,
      std_score: Math.round(Math.sqrt(scores.reduce((a, b) => a + (b - scored.summary.mean_score) ** 2, 0) / scores.length) * 1000) / 1000,
      min_score: Math.round(Math.min(...scores) * 1000) / 1000,
      max_score: Math.round(Math.max(...scores) * 1000) / 1000,
    }

    scored.data_leakage_check.has_issues = scored.data_leakage_check.issues.length > 0

    allScored[key] = scored

    leakageReport.files_checked.push({
      file,
      benchmark,
      model,
      condition,
      leakage_detected: scored.data_leakage_check.has_issues,
      issue_count: scored.data_leakage_check.issues.length,
    })

    // Save individual scored file
    const scoredFile = join(SCORED_DIR, file.replace('_smoke.json', '_scored.json'))
    writeFileSync(scoredFile, JSON.stringify(scored, null, 2))
    log(`  ✓ Saved: ${scoredFile}`)
  }

  // Save all scored results
  const allScoredFile = join(SCORED_DIR, 'all_smoke_scored.json')
  writeFileSync(allScoredFile, JSON.stringify(allScored, null, 2))
  log(`\n✓ All results: ${allScoredFile}`)

  // Save leakage report
  leakageReport.has_issues = leakageReport.files_checked.some(f => f.leakage_detected)
  const leakageFile = join(SCORED_DIR, 'data_leakage_report.json')
  writeFileSync(leakageFile, JSON.stringify(leakageReport, null, 2))
  log(`✓ Leakage report: ${leakageFile}`)

  // Print summary
  log('\n' + '='.repeat(60))
  log('SMOKE TEST SUMMARY')
  log('='.repeat(60))

  for (const [key, scored] of Object.entries(allScored)) {
    log(`\n${key}:`)
    log(`  Cases scored: ${scored.n_cases}`)
    log(`  Mean score: ${scored.summary.mean_score}`)
    log(`  Range: ${scored.summary.min_score} - ${scored.summary.max_score}`)
    if (scored.data_leakage_check.has_issues) {
      log(`  ⚠️  DATA LEAKAGE DETECTED (${scored.data_leakage_check.issues.length} issues)`)
    } else {
      log(`  ✓ No data leakage detected`)
    }
  }

  log('\n' + '='.repeat(60))
  log('NEXT STEPS:')
  log('1. Review smoke_test_scored/ for detailed scores')
  log('2. Check data_leakage_report.json for issues')
  log('3. If OK, run: node run_full_evaluation.mjs')
  log('='.repeat(60))
}

scoreSmokes()
