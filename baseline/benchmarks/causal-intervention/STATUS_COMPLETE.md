# Benchmark Status: Questions Generated ✅

## Current State

**Questions:** ✅ GENERATED (30 clinical questions)  
**Episodes:** ✅ CREATED (40 clinical episodes)  
**Matched Pairs:** ✅ CONSTRUCTED (30 pairs, perfect balance)  
**Metrics:** ✅ IMPLEMENTED (5 causal metrics)  
**Models:** ⏳ READY TO CONNECT

---

## What Has Been Completed

### Phase 1: Data Preparation ✅
- [x] Extract episodes from cardiac benchmark data
- [x] Encode patient confounders (SOFA, comorbidities, pre-trends)
- [x] Construct matched pairs with covariate balance
- [x] Generate clinical questions
- [x] Define evaluation rubrics

### Phase 2: Evaluation Infrastructure ✅
- [x] Implement MCCS metric (causal direction)
- [x] Implement TCAE metric (timing)
- [x] Implement IEC metric (magnitude calibration)
- [x] Implement pre-trend invariance test
- [x] Implement shape similarity metric
- [x] Create LLM inference wrapper

### Phase 3: Ready for Execution ⏳
- [ ] Connect LLMs (Qwen, DeepSeek, Llama, Mistral)
- [ ] Run inference on all 30 questions
- [ ] Score responses against evaluation rubric
- [ ] Compute metrics per model
- [ ] Generate comparison report

---

## 30 Clinical Questions: Structure

```
Each question contains:

1. QUESTION STEM (shown to model)
   ├─ Patient A: [age, gender, diagnoses, meds, intervention]
   ├─ Patient B: [age, gender, diagnoses, meds, intervention]
   └─ Task: "Will their outcomes differ?"

2. GROUND TRUTH (hidden from model)
   ├─ Case A trajectory: [0.0, 0.05, 0.08, 0.13, ...]
   ├─ Case B trajectory: [0.0, 0.04, 0.10, 0.17, ...]
   └─ Causal comparison: A vs B difference

3. EVALUATION RUBRIC (used to score model)
   ├─ Direction accuracy (40%): Did model predict rise/fall correctly?
   ├─ Causal comparison (40%): Did model identify which changes more?
   ├─ Timing estimate (15%): Did model predict realistic timeline?
   └─ Clinical reasoning (5%): Is explanation sound?
```

---

## Question Distribution

| Comparison | Count | Goal |
|-----------|-------|------|
| PCI vs Observation | 5 | Does surgery help vs. no treatment? |
| PCI vs Vasopressors | 5 | Does surgery help vs. blood pressure meds? |
| PCI vs Antibiotics | 5 | Does surgery help vs. infection treatment? |
| Vasopressors vs Observation | 5 | Does BP support help vs. no treatment? |
| Vasopressors vs Antibiotics | 5 | Does BP support help vs. antibiotics? |
| Antibiotics vs Observation | 5 | Does antibiotics help vs. no treatment? |

**Total: 30 balanced questions testing causal reasoning across interventions**

---

## Files Generated

```
/scratch/users/karun09/SIMR-Research/benchmarks/causal-intervention/

data/
├── questions.json              ← 30 questions + ground truth
├── matched_pairs.json          ← 30 matched pairs
├── encoded_features.json       ← Patient confounders
└── episodes.json               ← 40 clinical episodes

docs/
├── STATUS_COMPLETE.md          ← This file
├── QUESTIONS_GENERATED.md      ← Question details
├── BENCHMARK_EXPLAINED.md      ← Simple explanation
└── HOW_IT_WORKS.md             ← Technical guide

scripts/
├── generate_questions.py       ← NEW
├── convert_cardiac_benchmark.py
├── encode_features.py
├── construct_matched_pairs.py
└── extract_episodes.py

models/
└── llm_inference.py            ← LLM wrapper (ready)

metrics/
└── causal_metrics.py           ← 5 metrics (ready)

eval/
└── benchmark_runner.py         ← Needs update for questions
```

---

## What Needs to Happen Next

### Step 1: Update Benchmark Runner
Modify `eval/benchmark_runner.py` to:
```python
# Instead of loading episodes directly:
# Load questions from questions.json
# Show question_stem to model
# Hide ground_truth from model
# Score based on evaluation_rubric

class QuestionBenchmarkRunner(BenchmarkRunner):
    def load_questions(self):
        """Load questions with hidden ground truth"""
        with open(QUESTIONS_FILE) as f:
            data = json.load(f)
        return data['questions']
    
    def run_inference(self, model, question):
        """Get model response to clinical question"""
        response = model.predict(question['question_stem'])
        return response
    
    def score_response(self, model_response, question):
        """Score against evaluation rubric"""
        # Check direction accuracy
        # Check causal comparison
        # Check timing estimate
        # Check clinical reasoning
        return score
```

### Step 2: Configure Models
Update `eval/benchmark_runner.py`:
```python
MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
    ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),
]
```

### Step 3: Run Evaluation
```bash
python3 eval/benchmark_runner.py
```

Output:
- `model_responses.json`: What each model said
- `benchmark_results.json`: Scores and metrics
- `RESULTS.md`: Comparison table

### Step 4: Analyze Results
```
Which models understand causality?
├─ High MCCS (0.65+): Understands causal effects
├─ Low TCAE (<6h): Knows intervention timing
├─ Low IEC (<0.05): Predictions well-calibrated
└─ Passes invariance test: Actually causal
```

---

## Example: What Model Will Be Asked

**QUESTION TEXT:**
```
You are a clinical AI evaluating trajectory predictions after medical interventions.

## Case A: Percutaneous Coronary Intervention (PCI / Angioplasty)
Patient: 69-year-old Female
Diagnoses: Acute coronary syndrome
Intervention: Catheter-based procedure to open blocked coronary arteries

Baseline Troponin I: 0.5 ng/mL

## Case B: Observation Only (No Intervention)
Patient: 72-year-old Female
Diagnoses: Acute coronary syndrome
Intervention: Patient monitored without procedural intervention

Baseline Troponin I: 0.5 ng/mL

QUESTION:
1. Which patient's troponin will change more?
2. How much change do you expect in each case?
3. When will you expect to see the intervention effect?

Provide reasoning based on the intervention type.
```

**WHAT MODEL SHOULD SAY:**
```
Reasoning: PCI is an interventional procedure that opens coronary arteries,
limiting myocardial damage. This should lead to:
- Case A (PCI): Troponin should fall faster (2-6 hours)
- Case B (Observation): Troponin depends on natural course

Expected outcome: Case A will show more improvement than Case B
within 4-6 hours
```

**HOW WE SCORE IT:**
- ✓ Direction: Predicted A falls more than B (40 points)
- ✓ Causal: Explicitly reasons about intervention mechanism (40 points)
- ✓ Timing: Mentions 4-6 hour window (15 points)
- ✓ Reasoning: References PCI mechanism (5 points)
- **Total: 100/100** (model understands causality!)

---

## Current Metrics System

Each model will be evaluated on:

### MCCS (Matched Counterfactual Consistency Score)
- **What:** Did model predict correct intervention direction?
- **Range:** 0.0-1.0 (0.5 = random)
- **Good:** 0.65+
- **Excellent:** 0.75+

### TCAE (Temporal Causal Alignment Error)
- **What:** How close is predicted response timing?
- **Range:** 0-24+ hours
- **Good:** <6 hours
- **Excellent:** <3 hours

### IEC (Intervention Effect Calibration)
- **What:** Are magnitude predictions calibrated?
- **Range:** 0.0+ (lower is better)
- **Good:** <0.05
- **Excellent:** <0.01

### Pre-Trend Invariance Test
- **What:** Does model use intervention or just confounders?
- **Result:** ✓ Pass or ✗ Fail
- **Good:** ✓ Passes (MCCS drops when interventions shuffled)

### Shape Similarity
- **What:** How similar are trajectory shapes?
- **Range:** 0.0+ (lower is better)
- **Purpose:** Auxiliary metric (lower weight)

---

## Success Criteria

Model is considered **causal-aware** if it:

✅ MCCS > 0.65 (predicts intervention effects >65% accuracy)  
✅ TCAE < 6 hours (understands intervention timing)  
✅ IEC < 0.05 (magnitude estimates are calibrated)  
✅ Passes pre-trend invariance test (actually uses interventions)  

Model is **NOT causal** if:

❌ MCCS ≈ 0.5 (same as random guessing)  
❌ TCAE > 12 hours (predicts wrong timing)  
❌ IEC > 0.2 (miscalibrated predictions)  
❌ Fails invariance test (ignores intervention, focuses on confounders)

---

## Next Actions Checklist

- [ ] Review questions.json to verify quality
- [ ] Update benchmark_runner.py to use questions
- [ ] Test with one model first (e.g., mock predictor)
- [ ] Configure real models (Qwen, DeepSeek, etc.)
- [ ] Run full benchmark: `python3 eval/benchmark_runner.py`
- [ ] Review results in output/RESULTS.md
- [ ] Identify which models understand causality
- [ ] Compare against baselines

---

## Questions to Answer Before Next Phase

1. **Compute Resources:** Do you have GPU access? (Needed for large models)
2. **Model Priorities:** Which models to test first? (Speed vs quality tradeoff?)
3. **Data Quality:** Should we improve lab context in questions, or is current data sufficient?
4. **Evaluation Focus:** Which metrics matter most to you? (MCCS vs TCAE vs IEC?)
5. **Timeline:** How much time do you want to spend on evaluation?

---

## Summary

✅ **Complete benchmark infrastructure ready**
- 30 clinical questions generated with ground truth
- 30 matched pairs ensure fair comparison
- 5 causal metrics implemented
- LLM inference wrapper ready
- Evaluation framework defined

⏳ **Next: Connect models and run evaluation**
- Update benchmark_runner.py (~30 minutes)
- Configure LLMs (5 minutes)
- Run inference (depends on GPU access, model size)
- Analyze results (15 minutes)

📊 **Expected output:**
- Which models understand medical causality
- Which understand intervention timing
- Which memorize confounders vs actual causal effects
- Comparison table with MCCS, TCAE, IEC, invariance test

---

**Status: READY FOR MODEL EVALUATION** ✨

All questions generated. All infrastructure ready. We just need to connect the LLMs.

