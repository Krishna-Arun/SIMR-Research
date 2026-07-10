/**
 * Scoring module for MIMIC multi-lab reversal benchmark.
 *
 * Scores:
 * - Direction accuracy (per lab): 1.0 if direction matches
 * - Reversal detection: 1.0 if reversal correctly identified
 * - Causal justification: 0.0-1.0 based on patient specificity
 * - Confidence calibration: correlation between confidence and accuracy
 * - Total: weighted combination
 */

/**
 * Score a single case.
 *
 * @param {object} prediction - Model's prediction
 * @param {object} groundTruth - Actual values from MIMIC
 * @param {object} confidence - Confidence metrics from model
 * @returns {object} - Detailed scores
 */
export function scoreCase(prediction, groundTruth, confidence = null) {
  // Validate inputs
  if (!prediction || !groundTruth) {
    throw new Error('Missing prediction or ground truth')
  }

  const labs = ['Troponin', 'CK', 'Creatinine']

  // Direction accuracy per lab
  const directionScores = {}
  for (const lab of labs) {
    const pred_dir = prediction[`${lab.toLowerCase()}_direction`]
    const truth_dir = groundTruth[`${lab.toLowerCase()}_direction`]

    directionScores[lab] = {
      predicted: pred_dir,
      actual: truth_dir,
      score: pred_dir === truth_dir ? 1.0 : 0.0,
    }
  }

  // Mean direction accuracy
  const meanDirectionAccuracy = Object.values(directionScores)
    .reduce((sum, s) => sum + s.score, 0) / labs.length

  // Reversal detection per lab
  const reversalScores = {}
  for (const lab of labs) {
    const pred_dir = prediction[`${lab.toLowerCase()}_direction`]
    const prev_dir = groundTruth[`${lab.toLowerCase()}_visible_trend`]
    const truth_dir = groundTruth[`${lab.toLowerCase()}_direction`]

    const pred_reversal = pred_dir !== prev_dir && prev_dir !== 'stable'
    const actual_reversal = truth_dir !== prev_dir && prev_dir !== 'stable'

    reversalScores[lab] = {
      predicted_reversal: pred_reversal,
      actual_reversal: actual_reversal,
      score: pred_reversal === actual_reversal ? 1.0 : 0.0,
    }
  }

  // Mean reversal detection
  const meanReversalDetection = Object.values(reversalScores)
    .reduce((sum, s) => sum + s.score, 0) / labs.length

  // Causal justification quality
  const justificationScore = scoreJustification(
    prediction.causal_justification,
    groundTruth.patient_context,
    reversalScores
  )

  // Confidence calibration (if available)
  let confidenceCalibration = null
  if (confidence) {
    // Check if high/medium confidence was appropriate
    const overallAccuracy = (meanDirectionAccuracy + meanReversalDetection) / 2
    const confidenceLevel = confidence.confidence_level

    if (confidenceLevel === 'high' && overallAccuracy >= 0.75) {
      confidenceCalibration = 1.0
    } else if (confidenceLevel === 'high' && overallAccuracy >= 0.5) {
      confidenceCalibration = 0.75
    } else if (confidenceLevel === 'medium' && overallAccuracy >= 0.5) {
      confidenceCalibration = 0.5
    } else if (confidenceLevel === 'high') {
      confidenceCalibration = 0.25
    } else {
      confidenceCalibration = 0.5
    }
  }

  // Total score: 40% direction + 30% reversal + 20% justification + 10% calibration
  const totalScore =
    meanDirectionAccuracy * 0.40 +
    meanReversalDetection * 0.30 +
    justificationScore * 0.20 +
    (confidenceCalibration ? confidenceCalibration * 0.10 : 0)

  return {
    direction_accuracy: round3(meanDirectionAccuracy),
    reversal_detection: round3(meanReversalDetection),
    causal_justification: round3(justificationScore),
    confidence_calibration: confidenceCalibration ? round3(confidenceCalibration) : null,
    total_score: round3(totalScore),
    per_lab_scores: directionScores,
    per_lab_reversals: reversalScores,
    grading_details: {
      direction_weight: 0.40,
      reversal_weight: 0.30,
      justification_weight: 0.20,
      confidence_weight: 0.10,
    },
  }
}

/**
 * Score causal justification (0.0-1.0).
 *
 * Criteria:
 * 1.0 - Explains mechanism + baseline + complications + timeline + patient-specific
 * 0.75 - Clear mechanism + baseline; timeline/complications mentioned
 * 0.5 - Mechanism + baseline without patient context
 * 0.25 - Vague; barely addresses mechanism
 * 0.0 - No justification
 */
function scoreJustification(justification, patientContext, reversalScores) {
  if (!justification || justification.trim().length === 0) {
    return 0.0
  }

  const text = justification.toLowerCase()

  // Check for key elements
  const hasPatientContext = checkPatientContext(text, patientContext)
  const hasMechanism = checkMechanism(text)
  const hasTimeline = checkTimeline(text)
  const hasComplications = checkComplications(text)
  const addressesReversal = checkReversalAwareness(text, reversalScores)

  let score = 0.5 // base: addresses mechanism

  if (hasMechanism && hasPatientContext) {
    score += 0.25 // mechanism + baseline
  }

  if (hasTimeline) {
    score += 0.15 // timeline awareness
  }

  if (hasComplications) {
    score += 0.10 // complication awareness
  }

  if (addressesReversal) {
    score += 0.05 // reversal-specific reasoning
  }

  return Math.min(1.0, score)
}

/**
 * Check if justification mentions patient-specific factors.
 */
function checkPatientContext(text, context) {
  if (!context) return false

  const factors = []
  if (context.has_ckd) factors.push('ckd', 'kidney', 'renal', 'creatinine', 'clearance')
  if (context.has_prior_mi) factors.push('prior', 'mi', 'previous', 'scar', 'infarct')
  if (context.has_diabetes) factors.push('diabetes', 'glucose', 'inflammatory')
  if (context.age > 65) factors.push('age', 'elderly', 'older')

  const matches = factors.filter(f => text.includes(f))
  return matches.length >= 2 // at least 2 factors mentioned
}

/**
 * Check if justification explains the mechanism.
 */
function checkMechanism(text) {
  const mechanismKeywords = [
    'reperfusion', 'washout', 'perfusion', 'obstruct',
    'trauma', 'stress', 'inflammation', 'injury',
    'contrast', 'nephropathy', 'enzyme', 'damage',
    'procedure', 'intervention', 'stent', 'ptca', 'cabg',
  ]

  const matches = mechanismKeywords.filter(k => text.includes(k))
  return matches.length >= 2
}

/**
 * Check if justification mentions timeline.
 */
function checkTimeline(text) {
  const timelineKeywords = [
    'hour', 'h ', 'day', 'minute', 'peak', 'resolution',
    'immediately', 'gradually', 'delayed', 'soon', 'later',
    'acute', 'chronic', 'immediate',
  ]

  return timelineKeywords.some(k => text.includes(k))
}

/**
 * Check if justification mentions complications.
 */
function checkComplications(text) {
  const complicationKeywords = [
    'complication', 'failure', 'injury', 'toxicity',
    'nephropathy', 'thrombosis', 'infarction', 'rupture',
    'risk', 'adverse', 'dangerous',
  ]

  return complicationKeywords.some(k => text.includes(k))
}

/**
 * Check if justification shows awareness of reversal.
 */
function checkReversalAwareness(text, reversalScores) {
  const reversalKeywords = [
    'reversal', 'reverses', 'reversed', 'opposite',
    'contradicts', 'unexpected', 'surprising', 'flip',
    'changes from', 'shifts from',
  ]

  // Check if any reversals were predicted
  const hasReversals = Object.values(reversalScores)
    .some(s => s.actual_reversal)

  if (!hasReversals) return false

  return reversalKeywords.some(k => text.includes(k))
}

/**
 * Aggregate scores across multiple cases.
 */
export function aggregateScores(caseScores) {
  if (!caseScores || caseScores.length === 0) {
    return {}
  }

  const results = {
    n_cases: caseScores.length,
    mean_direction_accuracy: round3(
      caseScores.reduce((sum, s) => sum + s.direction_accuracy, 0) / caseScores.length
    ),
    mean_reversal_detection: round3(
      caseScores.reduce((sum, s) => sum + s.reversal_detection, 0) / caseScores.length
    ),
    mean_justification: round3(
      caseScores.reduce((sum, s) => sum + s.causal_justification, 0) / caseScores.length
    ),
    mean_total_score: round3(
      caseScores.reduce((sum, s) => sum + s.total_score, 0) / caseScores.length
    ),
  }

  // Distribution
  results.score_distribution = {
    excellent: caseScores.filter(s => s.total_score >= 0.85).length,
    good: caseScores.filter(s => s.total_score >= 0.70 && s.total_score < 0.85).length,
    fair: caseScores.filter(s => s.total_score >= 0.50 && s.total_score < 0.70).length,
    poor: caseScores.filter(s => s.total_score < 0.50).length,
  }

  return results
}

/**
 * Round to 3 decimal places.
 */
function round3(num) {
  return Math.round(num * 1000) / 1000
}
