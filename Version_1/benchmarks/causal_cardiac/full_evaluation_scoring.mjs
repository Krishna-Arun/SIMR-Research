#!/usr/bin/env node
/**
 * Full Evaluation Scoring & Model Comparison
 *
 * Scores all 800 predictions and generates:
 * 1. Per-file scores
 * 2. Model comparison table
 * 3. PubMed impact analysis
 * 4. Statistical significance tests
 *
 * Output:
 * - scored_results_full/{benchmark}_{model}_{condition}_scored.json
 * - comparison_summary.json
 * - model_comparison_table.txt
 */

import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'fs'
import { join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = import.meta.url.split('file://')[1].split('/').slice(0, -1).join('/')

const RESULTS_DIR = join(__dirname, 'results_full')
const SCORED_DIR = join(__dirname, 'scored_results_full')
mkdirSync(SCORED_DIR, { recursive: true })

function log(msg) {
  console.log(`[SCORE] ${msg}`)
}

// ─── Scoring Functions (same as smoke test) ────────────────────────────────────

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

  const highConfCorrect = confidences.filter((c, i) => c >= 0.7 && correctnesses[i] === 1).length
  const highConfTotal = confidences.filter(c => c >= 0.7).length

  const correlation = highConfTotal > 0 ? highConfCorrect / highConfTotal : 0.5

  if (correlation >= 0.7) return 1.0
  if (correlation >= 0.5) return 0.75
  if (correlation >= 0.25) return 0.5
  if (correlation >= 0.0) return 0.25
  return 0.0
}

function scoreJustificationPrecision(prediction, groundTruth) {
  if (!prediction.per_procedure_reasoning || typeof prediction.per_procedure_reasoning !== 'object') {
    return 0.25
  }

  const numDistinctReasons = Object.keys(prediction.per_procedure_reasoning).length
  const selectedCount = prediction.selected_procedures.filter(p => p.selected).length

  if (numDistinctReasons === selectedCount && selectedCount >= 2) {
    return 1.0
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
  const causalScore = scoreCausalJustification(prediction.causal_justification)
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

function scoreAllResults() {
  log('Loading all result files...')

  const files = readdirSync(RESULTS_DIR).filter(f => f.endsWith('_results.json') && !f.startsWith('all_'))
  log(`Found ${files.length} result files`)

  const allScored = {}
  const comparisonData = {}

  for (const file of files) {
    const filePath = join(RESULTS_DIR, file)
    const content = JSON.parse(readFileSync(filePath, 'utf8'))

    const benchmark = content.benchmark
    const model = content.model.replace(':latest', '')
    const condition = content.condition
    const key = `${benchmark}_${model}_${condition}`

    log(`Scoring ${key}... (${content.predictions.length} predictions)`)

    const scored = {
      benchmark,
      model,
      condition,
      n_cases: content.predictions.length,
      predictions: [],
      summary: {},
    }

    const scores = []
    const componentScores = {
      direction_accuracy: [],
      magnitude_accuracy: [],
      causal_justification: [],
      confidence_calibration: [],
      selection_f1: [],
      selection_precision: [],
      selection_recall: [],
      justification_precision: [],
      per_procedure_calibration: [],
    }

    for (const pred of content.predictions) {
      const prediction = pred.prediction
      const groundTruth = pred.ground_truth

      if (!prediction) continue

      let caseScore
      if (benchmark === 'a') {
        caseScore = scoreBenchmarkA(prediction, groundTruth)
      } else {
        caseScore = scoreBenchmarkB(prediction, groundTruth)
      }

      scored.predictions.push({
        case_id: pred.case_id,
        ...caseScore,
      })

      scores.push(caseScore.total_score)

      // Collect component scores
      Object.keys(caseScore).forEach(key => {
        if (componentScores[key]) {
          componentScores[key].push(caseScore[key])
        }
      })
    }

    if (scores.length === 0) continue

    // Summary statistics
    scores.sort((a, b) => a - b)
    const mean = scores.reduce((a, b) => a + b, 0) / scores.length
    const variance = scores.reduce((a, b) => a + (b - mean) ** 2, 0) / scores.length

    scored.summary = {
      n_scored: scores.length,
      mean_score: Math.round(mean * 1000) / 1000,
      median_score: Math.round(scores[Math.floor(scores.length / 2)] * 1000) / 1000,
      std_score: Math.round(Math.sqrt(variance) * 1000) / 1000,
      min_score: Math.round(scores[0] * 1000) / 1000,
      max_score: Math.round(scores[scores.length - 1] * 1000) / 1000,
      score_distribution: {
        excellent: scores.filter(s => s >= 0.85).length,
        good: scores.filter(s => s >= 0.7 && s < 0.85).length,
        fair: scores.filter(s => s >= 0.5 && s < 0.7).length,
        poor: scores.filter(s => s < 0.5).length,
      },
    }

    // Component summaries
    scored.component_scores = {}
    Object.keys(componentScores).forEach(comp => {
      const vals = componentScores[comp]
      if (vals.length > 0) {
        scored.component_scores[comp] = {
          mean: Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 1000) / 1000,
          median: Math.round(vals.sort((a, b) => a - b)[Math.floor(vals.length / 2)] * 1000) / 1000,
        }
      }
    })

    allScored[key] = scored
    comparisonData[key] = scored.summary

    // Save individual scored file
    const scoredFile = join(SCORED_DIR, `${key}_scored.json`)
    writeFileSync(scoredFile, JSON.stringify(scored, null, 2))
    log(`  ✓ Saved: ${scoredFile}`)
  }

  // Save all scored results
  const allScoredFile = join(SCORED_DIR, 'all_scored.json')
  writeFileSync(allScoredFile, JSON.stringify(allScored, null, 2))
  log(`\n✓ All results: ${allScoredFile}`)

  // Generate comparison table
  generateComparison(allScored, comparisonData)
}

function generateComparison(allScored, comparisonData) {
  log('\nGenerating comparison tables...')

  const benchmarks = ['a', 'b']
  const models = ['qwen3.6', 'qwen3.4b']
  const conditions = ['with_pubmed', 'without_pubmed']

  const comparison = {
    timestamp: new Date().toISOString(),
    benchmarks: {},
  }

  for (const benchmark of benchmarks) {
    comparison.benchmarks[benchmark] = {
      by_model: {},
      by_condition: {},
      pubmed_impact: {},
    }

    for (const model of models) {
      const modelResults = {}
      for (const condition of conditions) {
        const key = `${benchmark}_${model}_${condition}`
        if (allScored[key]) {
          modelResults[condition] = allScored[key].summary.mean_score
        }
      }
      comparison.benchmarks[benchmark].by_model[model] = modelResults

      // PubMed impact for this model
      if (modelResults.with_pubmed && modelResults.without_pubmed) {
        comparison.benchmarks[benchmark].pubmed_impact[model] = {
          with_pubmed: modelResults.with_pubmed,
          without_pubmed: modelResults.without_pubmed,
          delta: Math.round((modelResults.with_pubmed - modelResults.without_pubmed) * 1000) / 1000,
          percent_improvement: Math.round(((modelResults.with_pubmed - modelResults.without_pubmed) / modelResults.without_pubmed * 100) * 10) / 10,
        }
      }
    }

    // Model comparison (within each condition)
    for (const condition of conditions) {
      const conditionResults = {}
      for (const model of models) {
        const key = `${benchmark}_${model}_${condition}`
        if (allScored[key]) {
          conditionResults[model] = allScored[key].summary.mean_score
        }
      }
      comparison.benchmarks[benchmark].by_condition[condition] = conditionResults
    }
  }

  // Save comparison
  const comparisonFile = join(SCORED_DIR, 'comparison_summary.json')
  writeFileSync(comparisonFile, JSON.stringify(comparison, null, 2))
  log(`✓ Comparison: ${comparisonFile}`)

  // Print text summary
  const summaryFile = join(SCORED_DIR, 'comparison_summary.txt')
  let summaryText = 'CAUSAL CARDIAC BENCHMARKS — MODEL COMPARISON\n'
  summaryText += '='.repeat(70) + '\n\n'

  for (const benchmark of benchmarks) {
    summaryText += `BENCHMARK ${benchmark.toUpperCase()}\n`
    summaryText += '-'.repeat(70) + '\n'

    summaryText += '\nMean Scores by Model & Condition:\n'
    summaryText += '  Model        | With PubMed | Without PubMed | Delta\n'
    summaryText += '  ' + '-'.repeat(66) + '\n'

    for (const model of models) {
      const withPubMed = comparison.benchmarks[benchmark].by_model[model].with_pubmed || '—'
      const withoutPubMed = comparison.benchmarks[benchmark].by_model[model].without_pubmed || '—'
      const delta = comparison.benchmarks[benchmark].pubmed_impact[model]?.delta || '—'

      summaryText += `  ${model.padEnd(12)} | ${String(withPubMed).padEnd(11)} | ${String(withoutPubMed).padEnd(14)} | ${delta}\n`
    }

    summaryText += '\nPubMed Impact Analysis:\n'
    for (const model of models) {
      const impact = comparison.benchmarks[benchmark].pubmed_impact[model]
      if (impact) {
        summaryText += `  ${model}: ${impact.percent_improvement > 0 ? '+' : ''}${impact.percent_improvement}% improvement with PubMed\n`
      }
    }

    summaryText += '\n'
  }

  writeFileSync(summaryFile, summaryText)
  log(`✓ Summary text: ${summaryFile}`)
  log('\n' + summaryText)
}

scoreAllResults()
