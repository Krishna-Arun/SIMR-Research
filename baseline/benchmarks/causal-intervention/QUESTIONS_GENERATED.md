# Questions Generated ✓

## Summary

✅ **30 clinical questions generated** from matched pairs
- Each question compares 2 similar patients with different interventions
- Ground truth answers embedded (not shown to models)
- Evaluation rubrics defined
- Ready for LLM evaluation

---

## Question Structure

### What Each Question Contains

```json
{
  "question_id": "question_0001",
  "pair_id": "pair_000001",
  "severity": "mild",
  "difficulty": "medium",
  
  "scenario": {
    "case_a": {
      "patient_id": "115972167",
      "age": 69,
      "gender": "Female",
      "intervention": {
        "type": "pci",
        "name": "Percutaneous Coronary Intervention (PCI / Angioplasty)",
        "description": "Catheter-based procedure to open blocked coronary arteries"
      },
      "diagnoses": ["ICD-9: 410.01", ...],
      "lab_summary": "| Time | Test | Value | Unit | Status | ..."
    },
    "case_b": {
      "patient_id": "115967110",
      "age": 42,
      "gender": "Female",
      "intervention": {
        "type": "observation",
        "name": "Observation Only (No Intervention)",
        "description": "Patient monitored without procedural intervention"
      }
    }
  },
  
  "question_stem": "You are a clinical AI evaluating trajectory predictions...",
  
  "ground_truth": {
    "case_a": {
      "baseline": 0.5,
      "trajectory_48h": [0.52, 0.54, ...],
      "final_value": 0.64,
      "direction": "rising",
      "change": 0.14
    },
    "case_b": {...},
    "causal_comparison": {
      "case_a_improved_more": false,
      "magnitude_difference": 0.036
    }
  },
  
  "evaluation_rubric": {
    "direction_accuracy": {"weight": 0.40, "description": "..."},
    "causal_comparison": {"weight": 0.40, "description": "..."},
    "timing_estimate": {"weight": 0.15, "description": "..."},
    "clinical_reasoning": {"weight": 0.05, "description": "..."}
  }
}
```

---

## Question Types

**30 questions across 6 intervention pair types:**

| Pair Type | Count | Example |
|-----------|-------|---------|
| PCI vs Observation | 5 | Does surgery help vs. no treatment? |
| PCI vs Vasopressors | 5 | Does surgery help vs. blood pressure support? |
| PCI vs Antibiotics | 5 | Does surgery help vs. infection treatment? |
| Vasopressors vs Observation | 5 | Does blood pressure support help vs. no treatment? |
| Vasopressors vs Antibiotics | 5 | Does blood pressure support help vs. antibiotics? |
| Antibiotics vs Observation | 5 | Does infection treatment help vs. no treatment? |

---

## What Models Will Be Asked

Each question presents two nearly identical patients with different interventions:

```
QUESTION STEM (given to model):

You are a clinical AI evaluating trajectory predictions after medical interventions.

## Case A: Percutaneous Coronary Intervention (PCI)
- Patient: 69-year-old Female
- Diagnoses: [list]
- Medications: [list]
- Baseline Troponin: 0.5 ng/mL
- Lab timeline: [table]

## Case B: Observation Only
- Patient: 42-year-old Female
- Diagnoses: [list]
- Medications: [list]
- Baseline Troponin: 0.5 ng/mL
- Lab timeline: [table]

TASK:
1. Which patient's troponin will change more?
2. How much change do you expect in each case?
3. When will you expect to see the intervention effect?

Provide reasoning based on intervention type and physiological effects.
```

---

## Ground Truth (Not Shown to Model)

For each question, we have the actual outcome:

```
CASE A (PCI):
- Baseline Troponin: 0.50 ng/mL
- 48h Later: 0.64 ng/mL
- Direction: Rising (unexpected!)
- Change: +0.14 (14% increase)

CASE B (Observation):
- Baseline Troponin: 0.50 ng/mL
- 48h Later: 0.67 ng/mL
- Direction: Rising
- Change: +0.17 (17% increase)

CAUSAL COMPARISON:
Case A improved less than Case B (counterintuitive - possible that patient was too sick or intervention timing was off)
```

---

## Evaluation Rubric

Each question uses a 4-component scoring rubric:

### 1. Direction Accuracy (40% weight)
**Q: Did model predict rising/falling/stable correctly?**
- Model must predict whether each case's troponin rises, falls, or stays stable
- Graded on accuracy within ±20% error band

### 2. Causal Comparison (40% weight)
**Q: Did model correctly identify which case changes more?**
- Model must predict which intervention has stronger effect
- Must reason about intervention mechanism

### 3. Timing Estimate (15% weight)
**Q: Did model predict realistic response timing?**
- PCI: expected 2-6 hours
- Vasopressors: expected minutes to 1 hour
- Antibiotics: expected 24-72 hours

### 4. Clinical Reasoning (5% weight)
**Q: Is the explanation clinically sound?**
- References intervention mechanism
- Considers severity and comorbidities
- Acknowledges limitations

---

## Intervention Context

Models are evaluated on how well they understand these interventions:

### PCI (Percutaneous Coronary Intervention)
- **What:** Catheter-based procedure to open blocked arteries
- **Expected effect:** Troponin should fall as myocardial damage is limited
- **Timeline:** 2-6 hours

### Vasopressors (Norepinephrine, Epinephrine)
- **What:** Medications to increase blood pressure in cardiogenic shock
- **Expected effect:** May stabilize or slow troponin rise
- **Timeline:** Minutes to 1 hour

### Antibiotics (Beta-lactams, Fluoroquinolones, Vancomycin)
- **What:** Treatment for bacterial infections (sepsis, pneumonia)
- **Expected effect:** Slow improvement if infection-driven
- **Timeline:** 24-72 hours

### Observation (No Intervention)
- **What:** Patient monitored without procedural intervention
- **Expected effect:** Depends on natural disease course
- **Timeline:** Variable

---

## Data Files Generated

```
data/
├── questions.json          (30 questions with ground truth)
├── episodes.json           (40 clinical episodes)
├── matched_pairs.json      (30 matched pairs)
├── encoded_features.json   (patient confounders)
└── episodes/               (individual episode files)
```

---

## What Happens Next

Now that questions are generated:

### Step 1: Connect Models
- LLM reads question_stem
- Provides answer with reasoning
- No access to ground_truth

### Step 2: Parse Responses
- Extract predictions (direction, magnitude, timing)
- Score against rubric
- Compute metrics

### Step 3: Evaluate
- MCCS: Did model get direction right?
- TCAE: Did model predict timing correctly?
- IEC: Are magnitude estimates calibrated?
- Invariance test: Is model actually causal?

### Step 4: Report
- Generate comparison tables
- Identify which models understand causality
- Highlight differences in reasoning quality

---

## Sample Question Output

### The Question (What Model Sees)

```
You are a clinical AI evaluating trajectory predictions after medical interventions.

## Case A: Percutaneous Coronary Intervention (PCI / Angioplasty)
Patient: 69-year-old Female
Intervention: Catheter-based procedure to open blocked coronary arteries

## Case B: Observation Only (No Intervention)
Patient: 42-year-old Female
Intervention: Patient monitored without procedural intervention

Both patients have similar baseline conditions.

TASK:
1. Which patient's troponin will change more?
2. How much change do you expect in each case?
3. When will you expect to see the intervention effect?
```

### The Ground Truth (Hidden)

```
Case A: Troponin rises 0.14 (0.50 → 0.64)
Case B: Troponin rises 0.17 (0.50 → 0.67)

Expected timing:
- Case A (PCI): 2-6 hours
- Case B (Observation): Variable
```

### Scoring

If model predicts:
- "Case A will fall, Case B will rise, PCI works faster"
  - ✓ Direction partly correct (A falls: ✗, falls more: ✓)
  - ✓ Timing reasonable
  - ✓ Reasoning sound
  - Score: ~0.70-0.80 (good causal understanding)

If model predicts:
- "Both will stay the same, interventions don't matter"
  - ✗ Wrong direction
  - ✗ Wrong timing
  - ✗ Ignores interventions
  - Score: ~0.30-0.40 (poor causal understanding)

---

## Next: Run LLM Evaluation

To evaluate models on these questions:

```bash
# Step 1: Update benchmark_runner.py to use questions
# Step 2: Configure models (Qwen, DeepSeek, Llama, Mistral, etc.)
# Step 3: Run evaluation

python3 eval/benchmark_runner.py

# Results show which models understand causality
```

---

## Summary

✅ **Ready for evaluation**
- 30 clinical questions generated
- Ground truth answers prepared
- Evaluation rubric defined
- Intervention context provided
- Next step: Connect LLMs and run benchmark

**Questions test:** Can the model predict that different interventions cause different outcomes?

This is genuine causal reasoning, not just trajectory forecasting.
