# How the Causal Intervention Benchmark Works

## The Core Problem

**Question:** Can an AI model predict what happens to a patient's lab values after a medical intervention?

**The Catch:** We can't know what *would have* happened if we didn't do the intervention (the counterfactual). So how do we evaluate if the model is actually understanding causality?

**Our Solution:** Use matched pairs of real patients with the same condition but different interventions, and check if the model's predictions match the real outcomes.

---

## Simple Analogy

Imagine two patients with identical conditions:
- **Patient A:** Got intervention (PCI surgery)
- **Patient B:** No intervention (observation only)

**Real outcome:**
- Patient A's troponin: fell from 0.8 → 0.3 (improved)
- Patient B's troponin: stayed at 0.8 → 0.8 (no improvement)

**Model prediction:**
- If the model predicts A's troponin will fall and B's will stay stable, it's correct!
- If the model predicts both will improve equally, it's wrong!

That's the core of the benchmark.

---

## Step-by-Step Pipeline

### Step 1: Extract Episodes

**What:** Take patient data and create "episodes" around interventions.

**Example:**
```
Patient 123 gets PCI surgery on May 15, 2 PM

PRE-WINDOW (48 hours before):
├─ May 13 2 PM: Troponin = 0.80 (high, abnormal)
├─ May 13 6 PM: Creatinine = 1.2 (normal)
├─ May 14 10 AM: BNP = 500 (elevated)
├─ May 15 10 AM: Potassium = 4.2 (normal)
└─ May 15 1 PM: Last lab before intervention

INTERVENTION: PCI at May 15 2 PM ← This is time 0

POST-WINDOW (48 hours after):
├─ May 15 6 PM: Troponin = 0.75
├─ May 16 10 AM: Troponin = 0.65
├─ May 16 6 PM: Troponin = 0.50
├─ May 17 10 AM: Troponin = 0.35
└─ May 17 2 PM: Troponin = 0.25
```

**Purpose:** Create input-output pairs:
- **Input:** Pre-window labs (what the model sees)
- **Intervention:** Type of procedure (PCI, vasopressors, antibiotics, etc.)
- **Output:** Post-window trajectory (what the model predicts)

---

### Step 2: Encode Confounders

**Problem:** Some patients naturally improve or worsen regardless of intervention.
- Sicker patients might get more aggressive interventions AND worse outcomes
- Model might learn: "sicker → intervention → worse" (confounding!)

**Solution:** Explicitly capture confounders:

```json
{
  "severity_score": 8,         // SOFA score (0-24)
  "severity_bin": "moderate",  // For matching
  "comorbidities": {
    "diabetes": 1,
    "hypertension": 0,
    "heart_failure": 1,
    ...
  },
  "pre_trend": {
    "troponin": {
      "slope": 0.05,           // Rising 0.05 per hour
      "direction": "rising",   // Key: Was it already rising?
      "volatility": 0.01
    },
    "creatinine": {...},
    ...
  }
}
```

**Why:** If two patients have identical severity + pre-trend but get different interventions, any difference in outcomes is likely due to the intervention, not confounders!

---

### Step 3: Construct Matched Pairs

**Goal:** Find pairs of patients who are nearly identical except for the intervention.

**Matching criteria:**
```
Must match:
✓ Same severity bin (both "moderate")
✓ Same pre-trend direction (both troponin rising)
✓ Similar pre-trend magnitude (±20%)
✓ Similar comorbidities

Can differ:
✗ Intervention type (one gets PCI, other gets observation)
✗ Patient ID (different people is ok!)
```

**Example pair:**
```
PAIR #1
├─ Episode A: Patient 123, PCI intervention, Troponin rising slowly
└─ Episode B: Patient 456, No intervention, Troponin rising slowly
   (Same age, same severity, same pre-trend, but different intervention)

PAIR #2
├─ Episode A: Patient 789, Vasopressors, Troponin stable
└─ Episode B: Patient 234, Observation, Troponin stable
   (Both stable, both moderate severity, different treatments)
```

**Result:** 30 matched pairs with perfect covariate balance (SMD < 0.1).

---

## Step 4: Get Model Predictions

**Input to model:**
```
Patient 123 medical history:
- Age: 60, Gender: Male
- Diagnoses: ACS, Hypertension, Type 2 Diabetes
- Medications: Aspirin, Metoprolol, Atorvastatin
- Lab history (last 48h):
  * Troponin: rising from 0.50 → 0.80
  * BNP: 450 (elevated)
  * Creatinine: 1.2 (normal)
  * etc.

INTERVENTION: PCI

PREDICT: What will Troponin I be in the next 48 hours?
Return: 4 values [12h, 24h, 36h, 48h]
```

**Model output:**
```
Predicted trajectory: [0.75, 0.60, 0.45, 0.30]
(Troponin falling after PCI - makes sense!)
```

---

## Step 5: Compute Metrics

### Metric 1: MCCS (Matched Counterfactual Consistency Score)

**What it measures:** Did the model get the direction right for matched pairs?

**Example:**

```
PAIR #1: PCI vs No intervention
├─ Real outcome:
│  ├─ With PCI (Episode A): Troponin 0.80 → 0.25 (fell)
│  └─ Without intervention (Episode B): Troponin 0.80 → 0.75 (stayed)
│
└─ Model prediction:
   ├─ For Episode A: Predicted 0.80 → 0.30 (fell) ✓ CORRECT
   └─ For Episode B: Predicted 0.80 → 0.78 (stayed) ✓ CORRECT

→ This pair: CORRECT

PAIR #2: Vasopressors vs No intervention
├─ Real outcome:
│  ├─ With vasopressors: Troponin 0.50 → 0.60 (rose)
│  └─ Without intervention: Troponin 0.50 → 0.50 (stayed)
│
└─ Model prediction:
   ├─ For vasopressors: Predicted 0.50 → 0.40 (fell) ✗ WRONG
   └─ For no intervention: Predicted 0.50 → 0.50 (stayed) ✓ CORRECT

→ This pair: INCORRECT
```

**Formula:**
```
MCCS = (# correct pairs) / (total pairs)
     = 1/2 = 0.50 (50% accuracy in this example)
```

**Interpretation:**
- Random guess = 0.5 (coin flip)
- Good causal model = 0.65-0.75
- Excellent = 0.75+

---

### Metric 2: TCAE (Temporal Causal Alignment Error)

**What it measures:** Did the model predict the right *timing* of the effect?

**Example:**

```
PCI intervention - we expect fast response (2-6 hours)

Real data:
├─ 6 hours: Troponin starts falling noticeably
└─ 24 hours: Troponin fell significantly

Model prediction:
├─ 6 hours: Still high (no response yet)
└─ 28 hours: Now falling (too slow!)

→ Error: Model predicted response 22 hours too late!
   TCAE = 22 hours (WORSE)
```

**Interpretation:**
- <2h: Perfect (models understand fast physiology)
- <6h: Good
- >12h: Poor (model doesn't understand intervention timing)

---

### Metric 3: IEC (Intervention Effect Calibration)

**What it measures:** Are the predicted *magnitudes* correct?

**Example:**

```
Real outcome range: Troponin drops 0.10-0.30 (average 0.20)

Model predictions:
├─ Sometimes predicts 0.05 drop (too small)
├─ Sometimes predicts 0.50 drop (too big)
└─ Average: 0.18 (close but spread is too wide)

→ IEC measures this mismatch
```

**Interpretation:**
- Low IEC (<0.05): Model is well-calibrated
- Medium IEC (0.05-0.20): Acceptable
- High IEC (>0.20): Poor calibration

---

### Metric 4: Pre-Trend Invariance Test

**What it measures:** Is the model actually causal or just memorizing confounders?

**How it works:**

```
Step 1: Compute real MCCS = 0.70 (good!)

Step 2: Shuffle interventions within same severity bin
├─ Take all "moderate severity" patients
├─ Randomly swap which ones got which intervention
└─ Re-evaluate model (with correct real outcomes)

Step 3: Compute shuffled MCCS
├─ If MCCS drops to 0.55 → Good! Model uses interventions
├─ If MCCS stays at 0.70 → BAD! Model ignores interventions
```

**Why it matters:**

A model could memorize: "Moderate severity patients worsen" regardless of intervention.
- Real MCCS: 0.70 (looks good)
- Shuffled MCCS: 0.70 (same - doesn't use intervention info!)
- **Test FAILS** → Not actually causal

---

### Metric 5: Shape Similarity (Auxiliary)

**What it measures:** How well do predicted trajectories match actual ones?

Just trajectory closeness - we weight this less because correlation ≠ causation.

---

## The Output Report

When you run the benchmark, you get:

### Benchmark Results Table

```
| Model | Prompt | MCCS | TCAE | IEC | Invariance | Status |
|-------|--------|------|------|-----|-----------|--------|
| Qwen 7B | CoT | 0.68 | 4.2h | 0.012 | ✓ | Good |
| Llama 7B | CoT | 0.62 | 6.3h | 0.016 | ~ | Medium |
| Mistral 7B | Zero | 0.58 | 8.5h | 0.020 | ✗ | Poor |
```

**What this means:**
- Qwen 7B gets intervention effects right 68% of the time ✓
- Response timing is only 4.2 hours off (good)
- Pre-trend invariance passed ✓ (it's actually causal)
- Llama is reasonable but slower to respond
- Mistral with zero-shot doesn't understand causality well

---

## JSON Output

Full results include per-pair details:

```json
{
  "pair_0001": {
    "correct": true,
    "pred_diff": 0.52,        // Model predicted A-B difference
    "actual_diff": 0.55,      // Real A-B difference
    "pred_sign": 1,           // Predicted: A > B
    "actual_sign": 1          // Real: A > B ✓ MATCH
  },
  "pair_0002": {
    "correct": false,
    "pred_diff": -0.10,
    "actual_diff": 0.15,
    "pred_sign": -1,          // Predicted: A < B
    "actual_sign": 1          // Real: A > B ✗ WRONG
  }
}
```

---

## Why This Is Better Than Standard Benchmarks

| Standard Benchmark | This Benchmark |
|---|---|
| Predicts: "Troponin will be 0.5" | Predicts: "PCI will reduce troponin more than observation" |
| Ground truth: "Actual value is 0.48" ✓ | Ground truth: "Real data shows PCI effect > obs" ✓ |
| Problem: Accuracy ≠ Causality | Advantage: Tests causal reasoning explicitly |
| Model could memorize patterns | Model must understand interventions |

---

## Real-World Example

### Scenario
We want to know: Does Qwen understand that PCI helps cardiac patients?

### The Test
1. Find 10 cardiac patients with PCI
2. Find 10 similar patients with no intervention
3. Ask Qwen to predict troponin trajectory for all 20
4. Check: Did Qwen predict better outcomes for PCI group?

### Results
- **MCCS = 0.75**: Yes! Qwen got 75% of pairs right
- **TCAE = 3.8h**: Qwen understood response happens within hours (correct)
- **IEC = 0.008**: Magnitude predictions are well-calibrated
- **Invariance ✓**: Qwen uses intervention type, not just severity

**Conclusion:** Qwen demonstrates genuine causal reasoning about PCI effects.

---

## Configuration Example

To test with a different model:

```python
# Edit eval/benchmark_runner.py
MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),  # ← Add your model
]

# Run:
python3 eval/benchmark_runner.py

# Wait for results
# Check output/RESULTS.md for summary
# Check output/benchmark_results.json for details
```

---

## Summary

**The Benchmark Tests:**
1. ✓ Can the model predict intervention effects?
2. ✓ Does it get the timing right?
3. ✓ Are its magnitude estimates calibrated?
4. ✓ Is it actually causal or just memorizing confounders?

**Without:** Fake counterfactuals, simulation, or assumptions
**With:** Real patient data, rigorous matching, and defensible metrics

**Result:** NeurIPS-grade evaluation of LLM causal reasoning
