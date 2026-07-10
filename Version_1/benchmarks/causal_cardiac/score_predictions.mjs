#!/usr/bin/env node
/**
 * Causal Cardiac Benchmarks — Scoring Script
 *
 * Takes prediction results and grades them against the rubric.
 *
 * Input:  results/{a,b}_{with,without}_pubmed_results.json
 * Output: scored_results/{a,b}_{with,without}_pubmed_scored.json
 *         + aggregate_summary.json
 *
 * Scoring dimensions per rubric:
 * - Benchmark A: direction (40%) + magnitude (30%) + causal_justification (20%) + confidence_calibration (10%)
 * - Benchmark B: ranking_accuracy (40%) + top_3_quality (20%) + causal_justification (30%) + confidence_correlation (10%)
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const RESULTS_DIR = join(__dirname, 'results')
const SCORED_DIR = join(__dirname, 'scored_results')
const QUESTIONS_DIR = join(__dirname, 'questions')

mkdirSync(SCORED_DIR, { recursive: true })

function log(msg) {
  console.log(`[SCORE] ${msg}`)
}

// ─── Benchmark A: Scoring ─────────────────────────────────────────────────────

function scoreDirectionAccuracy(prediction, groundTruth) {
  /**
   * 1.0: predicted troponin direction exactly matches ground truth
   * 0.5: direction matches for secondary markers (CK, Creatinine) but not primary
   * 0.0: wrong direction or no prediction
   */
  if (!prediction.troponin_direction || !groundTruth.expected_troponin_direction) {
    return 0.0
  }

  if (prediction.troponin_direction === groundTruth.expected_troponin_direction) {
    return 1.0
  }

  // Check secondary markers if available
  if (prediction.ck_direction && groundTruth.expected_ck_direction) {
    if (prediction.ck_direction === groundTruth.expected_ck_direction) {
      return 0.5
    }
  }

  return 0.0
}

function scoreMagnitudeAccuracy(prediction, groundTruth) {
  /**
   * 1.0: within ±10%
   * 0.75: within ±20%
   * 0.5: within ±50%
   * 0.25: within ±100%
   * 0.0: >100% error or wrong direction
   */
  if (!prediction.troponin_magnitude_pct || !groundTruth.expected_troponin_magnitude_pct) {
    return 0.0
  }

  const predicted = prediction.troponin_magnitude_pct
  const actual = groundTruth.expected_troponin_magnitude_pct

  // Check direction first
  if ((predicted > 0) !== (actual > 0)) {
    return 0.0 // Wrong direction
  }

  const absError = Math.abs(predicted - actual)
  const pctError = absError / Math.abs(actual)

  if (pctError <= 0.10) return 1.0
  if (pctError <= 0.20) return 0.75
  if (pctError <= 0.50) return 0.5
  if (pctError <= 1.00) return 0.25
  return 0.0
}

function scoreCausalJustification(justification) {
  /**
   * 1.0: names mechanism + explains biomarker change + cites specifics + addresses timeline
   * 0.75: names mechanism + explains change + generic physiology OR timeline
   * 0.5: names mechanism OR explains change (but not both)
   * 0.25: vague reference to mechanism, no clear link
   * 0.0: no justification or nonsensical
   */
  if (!justification || typeof justification !== 'string') {
    return 0.0
  }

  const text = justification.toLowerCase()
  const length = justification.length

  if (length < 50) {
    return 0.0 // Too short
  }

  // Heuristic scoring based on content signals
  let score = 0.25 // baseline for any attempt

  // Check for mechanism language
  const hasMechanism = /reperfusion|intervention|procedure|artery|blood flow|perfusion|stent|catheter/i.test(text)
  if (hasMechanism) score = 0.5

  // Check for biomarker-specific explanation
  const hasBiomarkerLink = /troponin.*(?:increase|decrease|rise|fall|change|wash|clear|washout)/i.test(text) ||
                            /ck.*(?:increase|decrease|rise|fall|change)/i.test(text)
  if (hasBiomarkerLink) score = 0.75

  // Check for specific physiology or references
  const hasSpecifics = /coronary|myocardial|ischemia|perfusion pressure|time|hour|day|minute/i.test(text)
  const hasTimeline = /hour|day|minute|timeline|within|after/i.test(text)

  if (hasMechanism && hasBiomarkerLink && (hasSpecifics || hasTimeline)) {
    score = 1.0
  }

  return Math.min(1.0, score)
}

function scoreConfidenceCalibrationA(prediction, confidence, directionScore, magnitudeScore) {
  /**
   * 1.0: said "high" AND direction correct AND magnitude within ±20%
   * 0.75: said "high" AND direction correct (magnitude off)
   * 0.5: said "medium" AND prediction correct
   * 0.25: said "high" BUT prediction wrong
   * 0.0: said "high" AND completely wrong
   */
  const confLevel = confidence.categorical || 'unknown'
  const directionCorrect = directionScore >= 1.0
  const magnitudeGood = magnitudeScore >= 0.75

  if (confLevel === 'high') {
    if (directionCorrect && magnitudeGood) return 1.0
    if (directionCorrect) return 0.75
    if (!directionCorrect && magnitudeScore === 0.0) return 0.0
    return 0.25
  }

  if (confLevel === 'medium') {
    return directionCorrect && magnitudeScore >= 0.5 ? 0.5 : 0.25
  }

  return 0.0
}

function scoreBenchmarkA(prediction, groundTruth, confidence) {
  const directionScore = scoreDirectionAccuracy(prediction, groundTruth)
  const magnitudeScore = scoreMagnitudeAccuracy(prediction, groundTruth)
  const causalScore = scoreCausalJustification(prediction.causal_justification)
  const confidenceScore = scoreConfidenceCalibrationA(prediction, confidence, directionScore, magnitudeScore)

  const totalScore = (
    directionScore * 0.40 +
    magnitudeScore * 0.30 +
    causalScore * 0.20 +
    confidenceScore * 0.10
  )

  return {
    direction_accuracy: Math.round(directionScore * 1000) / 1000,
    magnitude_accuracy: Math.round(magnitudeScore * 1000) / 1000,
    causal_justification: Math.round(causalScore * 1000) / 1000,
    confidence_calibration: Math.round(confidenceScore * 1000) / 1000,
    total_score: Math.round(totalScore * 1000) / 1000,
  }
}

// ─── Benchmark B: Scoring ─────────────────────────────────────────────────────

function scoreRankingAccuracy(prediction, groundTruth) {
  /**
   * Count how many actual procedures appear in model's top-7 ranked list
   * Score = n_correct / 7.0
   */
  if (!prediction.ranked_procedures || !groundTruth.actual_procedures) {
    return 0.0
  }

  const topProcedures = prediction.ranked_procedures.slice(0, 7).map(p => p.procedure_name.toLowerCase())
  const actualProcedures = groundTruth.actual_procedures.map(p => p.toLowerCase())

  let correct = 0
  for (const proc of topProcedures) {
    for (const actual of actualProcedures) {
      if (proc.includes(actual) || actual.includes(proc)) {
        correct++
        break
      }
    }
  }

  return Math.min(1.0, correct / 7.0)
}

function scoreTop3Quality(prediction, groundTruth) {
  /**
   * Score: n_correct_in_top_3 / 3.0
   */
  if (!prediction.ranked_procedures || !groundTruth.actual_procedures) {
    return 0.0
  }

  const topProcedures = prediction.ranked_procedures.slice(0, 3).map(p => p.procedure_name.toLowerCase())
  const actualProcedures = groundTruth.actual_procedures.map(p => p.toLowerCase())

  let correct = 0
  for (const proc of topProcedures) {
    for (const actual of actualProcedures) {
      if (proc.includes(actual) || actual.includes(proc)) {
        correct++
        break
      }
    }
  }

  return Math.min(1.0, correct / 3.0)
}

function scoreConfidenceCorrelationB(prediction, confidence, rankingScore, top3Score) {
  /**
   * Post-hoc: Heuristic check if confidence aligns with ranking quality
   * Simple version: if confident and ranking is good, calibrated
   */
  const confScore = confidence.score || 0.5
  const actualAccuracy = (rankingScore + top3Score) / 2

  // Spearman correlation approximation: check if they move together
  const correlation = Math.abs(confScore - actualAccuracy) < 0.3 ? 1.0 : Math.max(0.0, 1.0 - Math.abs(confScore - actualAccuracy))

  if (correlation >= 0.70) return 1.0
  if (correlation >= 0.50) return 0.75
  if (correlation >= 0.25) return 0.5
  if (correlation >= 0.0) return 0.25
  return 0.0
}

function scoreBenchmarkB(prediction, groundTruth, confidence) {
  const rankingScore = scoreRankingAccuracy(prediction, groundTruth)
  const top3Score = scoreTop3Quality(prediction, groundTruth)
  const causalScore = scoreCausalJustification(prediction.causal_justification)
  const confidenceScore = scoreConfidenceCorrelationB(prediction, confidence, rankingScore, top3Score)

  const totalScore = (
    rankingScore * 0.40 +
    top3Score * 0.20 +
    causalScore * 0.30 +
    confidenceScore * 0.10
  )

  return {
    ranking_accuracy: Math.round(rankingScore * 1000) / 1000,
    top_3_quality: Math.round(top3Score * 1000) / 1000,
    causal_justification: Math.round(causalScore * 1000) / 1000,
    confidence_correlation: Math.round(confidenceScore * 1000) / 1000,
    total_score: Math.round(totalScore * 1000) / 1000,
  }
}

// ─── Load case ground truth ────────────────────────────────────────────────────

function loadCaseGroundTruth(caseId) {
  try {
    const casePath = join(QUESTIONS_DIR, `${caseId}.json`)
    const content = readFileSync(casePath, 'utf8')
    const caseData = JSON.parse(content)
    return caseData.ground_truth || null
  } catch (err) {
    return null
  }
}

// ─── Main scoring orchestrator ─────────────────────────────────────────────────

function scoreResults(benchmarkId, condition) {
  const resultsFile = join(RESULTS_DIR, `${benchmarkId}_${condition}_results.json`)

  let results
  try {
    results = JSON.parse(readFileSync(resultsFile, 'utf8'))
  } catch (err) {
    log(`Error reading ${resultsFile}: ${err.message}`)
    return null
  }

  const isBenchmarkA = benchmarkId === 'a'
  const scoredResults = []

  for (const result of results.results) {
    if (!result.success) {
      scoredResults.push({
        case_id: result.case_id,
        success: false,
        error: result.error,
      })
      continue
    }

    const groundTruth = loadCaseGroundTruth(result.case_id)
    if (!groundTruth) {
      log(`Warning: No ground truth for ${result.case_id}`)
      continue
    }

    const scoring = isBenchmarkA
      ? scoreBenchmarkA(result.prediction, groundTruth, result.confidence)
      : scoreBenchmarkB(result.prediction, groundTruth, result.confidence)

    scoredResults.push({
      case_id: result.case_id,
      hadm_id: result.hadm_id,
      prediction: result.prediction,
      confidence: result.confidence,
      scoring,
      success: true,
    })
  }

  // Aggregate statistics
  const successful = scoredResults.filter(r => r.success)
  const scores = successful.map(r => r.scoring.total_score)

  const stats = {
    n_scored: successful.length,
    n_failed: scoredResults.filter(r => !r.success).length,
    mean_score: scores.length > 0 ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 1000) / 1000 : 0,
    median_score: scores.length > 0 ? scores.sort((a, b) => a - b)[Math.floor(scores.length / 2)] : 0,
    std_score: scores.length > 0 ? Math.round(Math.sqrt(scores.reduce((sum, x) => sum + Math.pow(x - (scores.reduce((a, b) => a + b, 0) / scores.length), 2), 0) / scores.length) * 1000) / 1000 : 0,
    min_score: scores.length > 0 ? Math.min(...scores) : 0,
    max_score: scores.length > 0 ? Math.max(...scores) : 0,
    score_distribution: {
      excellent: successful.filter(r => r.scoring.total_score >= 0.85).length,
      good: successful.filter(r => r.scoring.total_score >= 0.70 && r.scoring.total_score < 0.85).length,
      fair: successful.filter(r => r.scoring.total_score >= 0.50 && r.scoring.total_score < 0.70).length,
      poor: successful.filter(r => r.scoring.total_score < 0.50).length,
    },
  }

  // Component-level aggregate
  const componentAggregates = isBenchmarkA
    ? {
        direction_accuracy: Math.round((successful.reduce((sum, r) => sum + r.scoring.direction_accuracy, 0) / successful.length) * 1000) / 1000,
        magnitude_accuracy: Math.round((successful.reduce((sum, r) => sum + r.scoring.magnitude_accuracy, 0) / successful.length) * 1000) / 1000,
        causal_justification: Math.round((successful.reduce((sum, r) => sum + r.scoring.causal_justification, 0) / successful.length) * 1000) / 1000,
        confidence_calibration: Math.round((successful.reduce((sum, r) => sum + r.scoring.confidence_calibration, 0) / successful.length) * 1000) / 1000,
      }
    : {
        ranking_accuracy: Math.round((successful.reduce((sum, r) => sum + r.scoring.ranking_accuracy, 0) / successful.length) * 1000) / 1000,
        top_3_quality: Math.round((successful.reduce((sum, r) => sum + r.scoring.top_3_quality, 0) / successful.length) * 1000) / 1000,
        causal_justification: Math.round((successful.reduce((sum, r) => sum + r.scoring.causal_justification, 0) / successful.length) * 1000) / 1000,
        confidence_correlation: Math.round((successful.reduce((sum, r) => sum + r.scoring.confidence_correlation, 0) / successful.length) * 1000) / 1000,
      }

  // Confidence calibration analysis
  const highConfResults = successful.filter(r => r.confidence.categorical === 'high')
  const mediumConfResults = successful.filter(r => r.confidence.categorical === 'medium')
  const lowConfResults = successful.filter(r => r.confidence.categorical === 'low')

  const confidenceAnalysis = {
    high_confidence_accuracy: highConfResults.length > 0 ? Math.round((highConfResults.filter(r => r.scoring.total_score >= 0.70).length / highConfResults.length) * 1000) / 1000 : null,
    medium_confidence_accuracy: mediumConfResults.length > 0 ? Math.round((mediumConfResults.filter(r => r.scoring.total_score >= 0.50).length / mediumConfResults.length) * 1000) / 1000 : null,
    low_confidence_accuracy: lowConfResults.length > 0 ? Math.round((lowConfResults.filter(r => r.scoring.total_score >= 0.30).length / lowConfResults.length) * 1000) / 1000 : null,
  }

  const output = {
    benchmark: results.benchmark,
    condition: results.condition,
    model: results.model,
    summary: stats,
    component_scores: componentAggregates,
    confidence_analysis: confidenceAnalysis,
    scored_cases: scoredResults,
  }

  return output
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  log('Starting scoring phase')

  const benchmarks = ['a', 'b']
  const conditions = ['with_pubmed', 'without_pubmed']
  const allResults = {}

  for (const benchmark of benchmarks) {
    for (const condition of conditions) {
      log(`Scoring ${benchmark}_${condition}...`)

      const scored = scoreResults(benchmark, condition)
      if (!scored) {
        log(`Failed to score ${benchmark}_${condition}`)
        continue
      }

      const outputFile = join(SCORED_DIR, `${benchmark}_${condition}_scored.json`)
      writeFileSync(outputFile, JSON.stringify(scored, null, 2))
      log(`Wrote ${outputFile}`)

      allResults[`${benchmark}_${condition}`] = scored.summary
    }
  }

  // Write aggregate summary
  const summaryFile = join(SCORED_DIR, 'aggregate_summary.json')
  writeFileSync(summaryFile, JSON.stringify(allResults, null, 2))
  log(`Wrote aggregate summary to ${summaryFile}`)

  log('Scoring complete!')
}

main().catch(err => {
  console.error('Fatal error:', err)
  process.exit(1)
})
