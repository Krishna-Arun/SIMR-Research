# Causal Cardiac Benchmark — Scoring Rubric

## Overview

**Benchmark A: Intervention → Physiological Effect** (Forward causal prediction)

The model receives **pre-procedure labs** and predicts how each biomarker will **change (Δ)** post-procedure.

**The 3 Key Biomarkers (with before→after focus):**
1. **Troponin T** (cardiac injury) — 50% weight
   - Pre: baseline troponin level
   - Post: expected level 24-48h later
   - Change: will it rise (new injury), fall (washout), or stay stable?

2. **CK** (cardiac/muscle enzyme) — 35% weight
   - Pre: baseline enzyme level
   - Post: expected level after procedure
   - Change: enzyme release from surgical trauma or cardiac damage?

3. **Creatinine** (renal function) — 15% weight
   - Pre: baseline renal function
   - Post: expected level (contrast-induced nephropathy?)
   - Change: kidney damage from contrast dye?

*Note: Potassium excluded — too many confounding factors (medications, renal function, underlying disease) make it unreliable for predicting from procedure type alone.*

Each prediction is scored across multiple dimensions:
- **Direction Accuracy**: Predicting correct directional change (↑ rise / ↓ fall / → stable) for each lab
- **Magnitude Accuracy**: How close the predicted % change matches actual observed change
- **Multi-Lab Justification**: Quality of mechanistic reasoning explaining WHY each lab changes pre→post
- **Confidence Calibration**: Does stated confidence match prediction accuracy?

---

## Benchmark A: Intervention → Physiological Effect

**Task:** Given **pre-procedure lab values** + procedure type, predict how labs will **change** in the post-intervention period (24-48 hours to 7 days).

**Timeline:**
```
PRE-PROCEDURE                 PROCEDURE              POST-PROCEDURE (24h-7d)
All labs before procedure → PTCA/stent/intervention → Measure changes in labs
(baseline state)             (occurs)               (new steady state)
```

Model predicts the **direction and magnitude of change** for each lab from pre→post.

### Scoring Components

#### 1. Direction Accuracy (40% weight)

Compare **predicted direction of change** (pre→post) against **actual observed change** for each lab.

**Timeline Clarity:**
```
Model predicts:  Pre value → [procedure happens] → Post value
                 (given)     (intervention)        (predicted)
                 
Ground truth:    Pre value → [procedure happens] → Post value (observed)
                 (given)     (actual result)       (measured from MIMIC)

Score: Does predicted direction match observed direction?
```

**Lab Weighting (by clinical relevance and procedural causality):**
- **Troponin T**: 50% (primary cardiac injury marker, directly caused by procedure)
- **CK**: 35% (enzyme damage from surgical trauma, directly caused by procedure)
- **Creatinine**: 15% (renal function impact from contrast dye exposure, directly caused by procedure)

**Per-Lab Scoring:**

| Score | Criteria |
|---|---|
| **1.0** | Predicted direction (↑/↓/→) matches observed direction from pre→post |
| **0.0** | Predicted direction does NOT match observed direction |

**How to compute:**
```
troponin_dir_score = 1.0 if pred_troponin_dir == truth_troponin_dir else 0.0
ck_dir_score = 1.0 if pred_ck_dir == truth_ck_dir else 0.0
creatinine_dir_score = 1.0 if pred_creatinine_dir == truth_creatinine_dir else 0.0
potassium_dir_score = 1.0 if pred_potassium_dir == truth_potassium_dir else 0.0

direction_accuracy = (
  troponin_dir_score * 0.40 +
  ck_dir_score * 0.25 +
  creatinine_dir_score * 0.20 +
  potassium_dir_score * 0.15
)
# Range: 0.0 to 1.0
```

**Example:**
```
Ground truth:  Troponin↓, CK↓, Creatinine→
Model predicts: Troponin↓, CK↑, Creatinine→

Scores: T=1.0, CK=0.0, Cr=1.0
direction_accuracy = (1.0×0.50) + (0.0×0.35) + (1.0×0.15) = 0.65
```

#### 2. Magnitude Accuracy (30% weight)

Score the **% change predictions** for all 3 labs (Troponin, CK, Creatinine).

**Magnitude = Percentage Change from Pre → Post:**
```
% change = (Post_value - Pre_value) / Pre_value × 100

Example:
  Pre troponin:  0.15 ng/mL
  Post troponin: 0.13 ng/mL
  % change = (0.13 - 0.15) / 0.15 × 100 = -13.3%
  
Model predicts -15% → Ground truth -13.3%
Prediction error = |-15 - (-13.3)| / 13.3 = 12.8% error
Score: 0.75 (within ±20%)
```

**Per-Lab Magnitude Scoring:**

| Score | Criteria |
|---|---|
| **1.0** | Predicted % change within ±10% of actual % change |
| **0.75** | Predicted % change within ±20% of actual % change |
| **0.5** | Predicted % change within ±50% of actual % change |
| **0.25** | Predicted % change within ±100% of actual % change |
| **0.0** | Differs by >100% OR wrong direction |

**Labs Scored for Magnitude:**
- Troponin T (% change from pre→post) — 50% weight
- CK (% change from pre→post) — 35% weight
- Creatinine (% change from pre→post) — 15% weight

**How to compute per lab:**
```
pct_error = abs(predicted_mag - ground_truth_mag) / abs(ground_truth_mag)

# Guard against zero denominator
if ground_truth_mag == 0:
  if predicted_mag == 0:
    per_lab_score = 1.0  # Both zero = no change
  else:
    per_lab_score = 0.0  # Predicted change but ground truth was stable

per_lab_score = (
  1.0 if pct_error <= 0.10
  else 0.75 if pct_error <= 0.20
  else 0.5 if pct_error <= 0.50
  else 0.25 if pct_error <= 1.00
  else 0.0
)

# CRITICAL: If direction is wrong, score 0.0 regardless of magnitude
if pred_direction != truth_direction:
  per_lab_score = 0.0
```

**Weighted average across labs:**
```
magnitude_accuracy = (
  troponin_mag_score * 0.50 +
  ck_mag_score * 0.35 +
  creatinine_mag_score * 0.15
)
# Range: 0.0 to 1.0
```

**Example:**
```
Ground truth:     Troponin -12.5%, CK -8.3%, Creatinine -2.1%
Model predicts:   Troponin -15.2%, CK +5.0%, Creatinine -1.8%

Troponin: error = 2.7/12.5 = 21.6% → score 0.75 (within ±20%)
CK: direction wrong (↓ vs ↑) → score 0.0
Creatinine: error = 0.3/2.1 = 14.3% → score 0.75 (within ±20%)

magnitude_accuracy = (0.75×0.50) + (0.0×0.35) + (0.75×0.15) = 0.4625 ≈ 0.46
```

#### 3. Multi-Lab Causal Justification (20% weight)

Evaluate reasoning quality across **all 3 predicted labs**. The model must explain the mechanistic link for each lab direction/magnitude prediction.

**Scoring Rubric:**

| Score | Criteria |
|---|---|
| **1.0** | ✓ Names specific procedure mechanism ✓ Explains how mechanism drives changes in EACH lab (Troponin, CK, Creatinine) ✓ Cites specific physiology (e.g., reperfusion, hemodynamic effects, contrast toxicity) ✓ Addresses relevant timeline ✓ Explains consistency/divergence between labs |
| **0.75** | ✓ Names mechanism ✓ Explains all 3 labs clearly ✓ Specific physiology cited ✓ Timeline mentioned; minor gaps in multi-lab consistency |
| **0.5** | ✓ Names mechanism ✓ Explains 2 labs clearly OR ✓ Generic explanation covering all labs without specifics |
| **0.25** | ✓ Vague mechanism description; explains 1-2 labs only; weak mechanistic links |
| **0.0** | No justification, completely nonsensical, or fails to address predicted labs |

**Examples:**

**1.0 (Full multi-lab explanation):**
> "PTCA + stent on LAD reopens the LAD, restoring coronary perfusion. 
> 
> **Troponin T:** Myocardial reperfusion enables rapid troponin washout (increased clearance from restored coronary perfusion), explaining ~12% decline over 48h. Peak occurs at 24-36h post-MI, then declines.
> 
> **CK:** Muscle enzyme release peaks 24-36h; as perfusion restores, further damage halts. Expect ~8% decline post-intervention as surgical stress resolves.
> 
> **Creatinine:** Minor decline expected from improved renal perfusion post-intervention (−2%), though contrast dye exposure could transiently elevate it 24-48h post-procedure before declining."

**0.75 (Clear mechanism, all 3 labs explained):**
> "Stent placement on LAD restores coronary blood flow. Troponin drops (washout from restored perfusion, ~15% decline). CK falls as cardiac enzyme release stops (8% drop). Creatinine may be slightly elevated from contrast exposure but should stabilize within 48h."

**0.5 (Generic or incomplete):**
> "The stent improves blood flow. This reduces troponin and CK. Creatinine should stay relatively stable."

**0.25 (Vague, incomplete):**
> "Stents help cardiac patients. The labs should improve."

**0.0 (No justification):**
> Empty or unrelated explanation.

**Evaluation Notes:**
- Model must address ALL 3 predicted labs (Troponin, CK, Creatinine)
- If a prediction is "stable," the justification must explain WHY (e.g., "Creatinine stable despite contrast because patient has good renal function")
- Bonus clarity if model explains divergence (e.g., "Troponin down but CK initially elevated from surgical trauma")
- Generic explanations that lump all labs together score 0.5 max

#### 4. Confidence Calibration (10% weight)

Post-hoc assessment: Does the model's confidence level match overall prediction accuracy across all 3 labs?

**Calibration Scoring:**

| Score | Criteria |
|---|---|
| **1.0** | Model said "high" confidence AND all 3 labs correct direction AND ≥2/3 magnitude labs within ±20% |
| **0.75** | Model said "high" confidence AND ≥2/3 labs correct direction OR ≥2/3 magnitude labs within ±20% |
| **0.5** | Model said "medium" confidence AND ≥2/3 labs correct overall |
| **0.25** | Model said "high" confidence BUT only 1/3 labs direction correct |
| **0.0** | Model said "high" confidence AND all 3 labs direction incorrect |

**How to compute:**
```
# Count correct predictions across all 3 labs
direction_correct_count = sum([
  1 if pred_troponin_dir == truth else 0,
  1 if pred_ck_dir == truth else 0,
  1 if pred_creatinine_dir == truth else 0,
])

magnitude_correct_count = sum([
  1 if error(troponin) <= 0.20 else 0,
  1 if error(ck) <= 0.20 else 0,
  1 if error(creatinine) <= 0.20 else 0,
])

# Assign score based on confidence + accuracy
if confidence_categorical == "high":
  if direction_correct_count == 3 and magnitude_correct_count >= 2:
    calibration_score = 1.0
  elif direction_correct_count >= 2 or magnitude_correct_count >= 2:
    calibration_score = 0.75
  elif direction_correct_count >= 1:
    calibration_score = 0.25
  else:
    calibration_score = 0.0
elif confidence_categorical == "medium":
  if direction_correct_count >= 2:
    calibration_score = 0.5
  else:
    calibration_score = 0.25
else:  # low
  if direction_correct_count >= 2:
    calibration_score = 0.5
  else:
    calibration_score = 0.25
```

**Example:**
```
Model confidence: "high"
Direction correct: Troponin ✓, CK ✗, Creatinine ✓ (2/3)
Magnitude correct: Troponin (within ±20%) ✓, CK (wrong dir) ✗, Creatinine ✓ (2/3)

Calibration score = 0.75 (high confidence with 2/3 directions correct and 2/3 magnitude within ±20%)
```

### Total Score for Benchmark A

```
total_a = (
  direction_accuracy * 0.40 +
  magnitude_accuracy * 0.30 +
  causal_justification * 0.20 +
  confidence_calibration * 0.10
)
# Range: 0.0 to 1.0

# Interpretation:
# 0.85-1.0 = Excellent (correct directions, magnitudes within 20%, strong justification)
# 0.70-0.84 = Good (≥3/4 labs correct, magnitudes reasonable, clear reasoning)
# 0.50-0.69 = Fair (≥2/4 labs correct, some magnitude errors, weak justification)
# <0.50 = Poor (≤1/4 labs correct, major magnitude errors)
```

**Example Calculation:**
```
Prediction: Troponin↓ (-15%), CK↓ (-5%), Creatinine→ (-2%)
Ground truth: Troponin↓ (-12%), CK↓ (-8%), Creatinine→ (-2%)

Direction accuracy:
  = (1.0×0.50) + (1.0×0.35) + (1.0×0.15) = 1.0

Magnitude accuracy:
  Troponin: error 3/12 = 25% → 0.75
  CK: error 3/8 = 37.5% → 0.5
  Creatinine: error 0% → 1.0
  = (0.75×0.50) + (0.5×0.35) + (1.0×0.15) = 0.70

Causal justification: 0.85 (clear explanation of all 3 labs)

Confidence calibration: 0.75 (high confidence, all 3 correct directions)

Total = (1.0×0.40) + (0.70×0.30) + (0.85×0.20) + (0.75×0.10)
      = 0.40 + 0.21 + 0.17 + 0.075
      = 0.845 ≈ 0.85 (Excellent)
```

---

## Confidence Extraction from Logits

Each response includes confidence metrics computed from Ollama's token log probabilities:

```json
{
  "confidence": {
    "categorical": "high | medium | low",
    "score": 0.0 - 1.0,  // Extracted from logits
    "logprob_avg": -2.34,  // Average log probability per token
    "entropy": 0.45,       // Shannon entropy of token distributions
    "n_tokens": 312
  }
}
```

**How confidence_score is computed:**
```
confidence_score = 0.6 * normalize(average_logprob) + 0.4 * normalize(1 - entropy)

where:
  - normalize(logprob) maps typical range [-15, 0] to [0, 1]
  - normalize(entropy) maps typical range [0, 5] to [0, 1] (inverted for confidence)
  - high confidence (≥0.70), medium (0.40-0.70), low (<0.40)
```

These are **recorded but not directly scored** — instead, they're used to compute calibration metrics (sections 4 in each rubric).

---

## Recording Template

Each prediction result should have this structure, with **all 4 labs** represented:

```json
{
  "case_id": "a_001",
  "hadm_id": 26913865,
  "procedure": "PTCA + stent on LAD",
  "prediction": {
    "troponin_direction": "falling",
    "troponin_magnitude_pct": -15.2,
    "ck_direction": "falling",
    "ck_magnitude_pct": -5.3,
    "creatinine_direction": "stable",
    "creatinine_magnitude_pct": -2.1,
    "causal_justification": "PTCA restores LAD perfusion, enabling troponin washout (expected ~12-15% decline over 48h). CK falls as enzyme release halts (8% expected). Creatinine stable (no acute renal impact from coronary angioplasty alone, though contrast exposure could transiently elevate it)."
  },
  "ground_truth": {
    "troponin_direction": "falling",
    "troponin_magnitude_pct": -12.5,
    "ck_direction": "falling",
    "ck_magnitude_pct": -8.0,
    "creatinine_direction": "stable",
    "creatinine_magnitude_pct": -1.8
  },
  "confidence": {
    "categorical": "high",
    "score": 0.87,
    "logprob_avg": -1.23,
    "entropy": 0.34,
    "n_tokens": 312
  },
  "scoring": {
    "direction_accuracy": {
      "troponin": 1.0,
      "ck": 1.0,
      "creatinine": 1.0,
      "potassium": 0.0,
      "weighted_total": 0.85
    },
    "magnitude_accuracy": {
      "troponin": 0.75,
      "ck": 0.5,
      "creatinine": 1.0,
      "weighted_total": 0.70
    },
    "causal_justification": 0.85,
    "confidence_calibration": 0.75,
    "total_score": 0.80,
    "interpretation": "Good"
  }
}
```

**Key Notes:**
- All 3 labs (Troponin, CK, Creatinine) must be present in prediction
- Magnitude scoring applies to all 3 labs
- Causal justification must address WHY each lab changes (or stays stable)
- Ground truth includes actual observed directions and magnitudes from MIMIC data
- Potassium excluded: too many confounding factors (medications, renal function, underlying disease)

---

## Aggregation Across 100 Cases

After all 100 cases are scored for a condition:

```json
{
  "benchmark": "intervention_physiological_effect",
  "condition": "with_pubmed",
  "model": "qwen3.6",
  "summary": {
    "n_cases": 100,
    "mean_score": 0.68,
    "median_score": 0.71,
    "std_score": 0.18,
    "score_distribution": {
      "excellent": 25,    // [0.85, 1.0]
      "good": 35,         // [0.70, 0.85)
      "fair": 30,         // [0.50, 0.70)
      "poor": 10          // [0.0, 0.50)
    }
  },
  "confidence_statistics": {
    "mean_confidence": 0.64,
    "high_confidence_accuracy": 0.82,    // Of cases marked "high", % correct
    "medium_confidence_accuracy": 0.55,  // Of cases marked "medium", % correct
    "low_confidence_accuracy": 0.35      // Of cases marked "low", % correct
  },
  "component_scores": {
    "direction_accuracy": 0.78,
    "magnitude_accuracy": 0.65,
    "causal_justification": 0.62,
    "confidence_calibration": 0.58
  }
}
```

---

## Notes

- **All 3 labs required.** Missing direction or magnitude predictions for any lab scores 0.0 for that component.
- **Magnitude scoring for all 3 labs.** Troponin, CK, and Creatinine all scored on % change accuracy.
- **Potassium excluded.** Too many confounding factors (medications, renal function, underlying disease) make it unreliable for predicting from procedure type alone.
- **Causal justification must be multi-lab.** Generic explanations of "lab changes" without specific per-lab mechanism score ≤0.5.
- **Calibration is post-hoc.** Confidence doesn't affect primary accuracy scores; it's an independent dimension tracking whether the model's stated confidence matches actual accuracy.
- **Per-lab consistency.** If a model predicts Creatinine will "fall" but justifies it as "no renal impact," flag as contradiction (lowers justification score).
