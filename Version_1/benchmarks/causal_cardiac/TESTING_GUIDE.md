# Causal Cardiac Benchmarks — Testing & Evaluation Guide

## Overview

This guide covers running smoke tests (5 cases per benchmark) to verify correctness, check for data leakage, and then running the full evaluation (100 cases) with model comparison.

### Testing Matrix

```
Benchmarks:  A (Intervention→Effect), B (Physiology→Intervention)
Models:      qwen3.6, qwen3.4b
Conditions:  with_pubmed, without_pubmed

Total combinations: 2 × 2 × 2 = 8
- Smoke test: 5 cases × 8 = 40 predictions
- Full eval:  100 cases × 8 = 800 predictions
```

---

## Prerequisites

### 1. Ollama Setup

Ensure you have Ollama running with both models available:

```bash
# Start Ollama in one terminal
ollama serve

# In another terminal, pull models
ollama pull qwen3.6:latest
ollama pull qwen3.4b:latest

# Verify models are available
curl http://localhost:11434/api/tags
```

**Verify endpoint:**
```bash
curl http://localhost:11434/v1/models
# Should list both qwen3.6:latest and qwen3.4b:latest
```

### 2. Case Files

Ensure case files are generated (run once):

```bash
cd benchmarks/causal_cardiac
python3 prep_intervention_attribution.py      # Generates a_001.json - a_100.json
python3 prep_physiological_attribution.py     # Generates b_001.json - b_100.json
```

### 3. Environment Variables (Optional)

```bash
export OLLAMA_BASE_URL=http://localhost:11434/v1
export OLLAMA_MODEL=qwen3.6:latest
export CONCURRENCY=2  # For full eval: adjust based on system capacity
```

---

## Phase 1: Smoke Test (5 cases per benchmark)

### Step 1a: Run Smoke Test Predictions

```bash
cd benchmarks/causal_cardiac
node smoke_test.mjs
```

**Output structure:**
```
smoke_test_results/
├── a_qwen3.6_with_pubmed_smoke.json
├── a_qwen3.6_without_pubmed_smoke.json
├── a_qwen3.4b_with_pubmed_smoke.json
├── a_qwen3.4b_without_pubmed_smoke.json
├── b_qwen3.6_with_pubmed_smoke.json
├── b_qwen3.6_without_pubmed_smoke.json
├── b_qwen3.4b_with_pubmed_smoke.json
├── b_qwen3.4b_without_pubmed_smoke.json
└── smoke_test_summary.json
```

**What to watch for:**
- ✓ 5 predictions per file (40 total)
- ✓ Each prediction has `case_id`, `prediction`, `ground_truth`
- ⚠️ Model response time (baseline for full eval)
- ❌ Any Ollama connection errors

### Step 1b: Score Smoke Test & Check Data Leakage

```bash
node smoke_test_scoring.mjs
```

**Output structure:**
```
smoke_test_scored/
├── a_qwen3.6_with_pubmed_scored.json
├── ... (8 files, one per combination)
├── all_smoke_scored.json
└── data_leakage_report.json
```

**What to check:**

#### **Data Leakage Report** (`data_leakage_report.json`)

This detects cases where:
1. **Predicted magnitude suspiciously matches ground truth** (within ±0.5%)
2. **Perfect procedure match** (model selected exactly the right procedures, could indicate prompt injection)

**Example leakage issue:**
```json
{
  "case_id": "a_001",
  "issues": [
    "Troponin magnitude suspiciously close: predicted -12.3, actual -12.5"
  ]
}
```

**Action:** If leakage detected:
- Review the case JSON for ground truth visibility
- Check if ground truth was accidentally included in the prompt
- Fix and re-run

#### **Score Sanity Checks**

In `all_smoke_scored.json`, for each combination verify:

```json
{
  "a_qwen3.6_with_pubmed": {
    "n_cases": 5,
    "summary": {
      "mean_score": 0.62,      // ✓ Reasonable (0.3-0.8)
      "median_score": 0.71,
      "std_score": 0.18,       // ✓ Not 0.0 (variance present)
      "min_score": 0.2,        // ✓ Some variance
      "max_score": 0.85
    }
  }
}
```

**Red flags:**
- ❌ `mean_score` = 0.0 or 1.0 (all perfect or all wrong)
- ❌ `std_score` = 0.0 (no variance)
- ❌ All scores in narrow range (0.48-0.52)

### Step 1c: Manual Verification (Optional)

Pick 1-2 cases and review manually:

```bash
cat smoke_test_results/a_qwen3.6_with_pubmed_smoke.json | jq '.predictions[0]'
```

Verify:
1. ✓ Prediction makes clinical sense
2. ✓ Causal justification references mechanism
3. ✓ Ground truth is not in the prediction text
4. ✓ Confidence value is reasonable (0.0-1.0)

---

## Phase 2: Full Evaluation (100 cases per benchmark)

**Only proceed if:**
- ✓ Smoke test has no data leakage issues
- ✓ Scores are reasonable (not all 0 or 1)
- ✓ Model responses are valid JSON
- ✓ Runtime is acceptable (scale by cases: 40 cases took ~X min → 100 cases ~Y min)

### Step 2a: Run Full Evaluation

```bash
node run_full_evaluation.mjs
```

**Expected runtime:**
- 5 cases: ~2-5 minutes (smoke test)
- 100 cases: ~40-100 minutes (depending on model, concurrency, hardware)

**Concurrency control:**
```bash
# For GPUs with good VRAM, increase concurrency
CONCURRENCY=4 node run_full_evaluation.mjs

# For slower systems
CONCURRENCY=1 node run_full_evaluation.mjs
```

**Output:**
```
results_full/
├── a_qwen3.6_with_pubmed_results.json
├── ... (8 files)
├── b_qwen3.4b_without_pubmed_results.json
└── all_results.json
```

Each file contains 100 predictions per benchmark/model/condition.

### Step 2b: Score Full Results & Generate Comparison

```bash
node full_evaluation_scoring.mjs
```

**Output:**
```
scored_results_full/
├── a_qwen3.6_with_pubmed_scored.json
├── ... (8 files with scores)
├── all_scored.json
├── comparison_summary.json
└── comparison_summary.txt  (human-readable)
```

### Step 2c: Review Results

#### **Text Summary** (`comparison_summary.txt`)

```
CAUSAL CARDIAC BENCHMARKS — MODEL COMPARISON
======================================================================

BENCHMARK A
----------------------------------------------------------------------

Mean Scores by Model & Condition:
  Model        | With PubMed | Without PubMed | Delta
  ------------------------------------------------------------------
  qwen3.6      | 0.68        | 0.61           | 0.07
  qwen3.4b     | 0.55        | 0.49           | 0.06

PubMed Impact Analysis:
  qwen3.6: +11.5% improvement with PubMed
  qwen3.4b: +12.2% improvement with PubMed

BENCHMARK B
...
```

#### **Detailed Comparison** (`comparison_summary.json`)

Structure:
```json
{
  "benchmarks": {
    "a": {
      "by_model": {
        "qwen3.6": {
          "with_pubmed": 0.68,
          "without_pubmed": 0.61
        },
        "qwen3.4b": {
          "with_pubmed": 0.55,
          "without_pubmed": 0.49
        }
      },
      "pubmed_impact": {
        "qwen3.6": {
          "delta": 0.07,
          "percent_improvement": 11.5
        },
        "qwen3.4b": {
          "delta": 0.06,
          "percent_improvement": 12.2
        }
      }
    }
  }
}
```

---

## Interpreting Results

### Model Comparison

**Qwen 3.6 vs 3.4B:**
- If 3.6 scores significantly higher (>10% difference), it has better causal reasoning capability
- If scores are similar, 3.4B may be sufficient and more efficient

### PubMed Impact

**With vs Without PubMed:**
- Large delta (>10%) → Model benefits from external knowledge
- Small delta (<5%) → Model relies on context, not memorization
- Negative delta → Model confuses external knowledge (rare)

### Score Distribution

```
Excellent: [0.85, 1.0]  — Strong causal reasoning
Good:      [0.70, 0.85) — Solid understanding
Fair:      [0.50, 0.70) — Partial credit
Poor:      [0.0, 0.50)  — Weak reasoning
```

**Healthy distribution:**
- ✓ ~20-40% Excellent/Good
- ✓ ~40-50% Fair
- ✓ ~10-20% Poor

**Red flags:**
- ❌ >60% Excellent (might be overfitting to cases)
- ❌ >40% Poor (model not capable)

---

## Data Leakage Checklist

### False Positives to Ignore

Sometimes the algorithm flags valid cases as "suspicious":
- A model genuinely gets the correct answer (high confidence + correct)
- The predicted magnitude happens to be close to ground truth (statistical chance)

### Real Leakage to Fix

- Ground truth values in the prompt (e.g., "troponin is expected to fall 12.5%")
- Case ID mapping the model can exploit
- Procedure names in Benchmark B appearing in the ground truth explanation

**If leakage found:**
1. Review the case JSON structure
2. Identify what leaked (procedure names? magnitude?)
3. Fix in `run_causal_evaluation.mjs` or `run_full_evaluation.mjs`
4. Re-run smoke test to verify fix

---

## Troubleshooting

### Issue: Ollama connection refused

```
Error: connect ECONNREFUSED 127.0.0.1:11434
```

**Fix:**
```bash
# Start Ollama
ollama serve

# Or use remote endpoint
OLLAMA_BASE_URL=http://remote-host:11434/v1node smoke_test.mjs
```

### Issue: Model not found

```
Error: Model qwen3.4b:latest not found
```

**Fix:**
```bash
ollama pull qwen3.4b:latest
```

### Issue: Predictions are null/empty

Check:
1. Is Ollama responding? `curl http://localhost:11434/api/tags`
2. Is the model loaded? `ollama list`
3. Are case files present? `ls questions/a_*.json`

### Issue: Smoke test takes too long

- Reduce `SMOKE_TEST_SIZE` in `smoke_test.mjs` (e.g., to 2)
- Run with fewer concurrent requests: `CONCURRENCY=1`
- Check Ollama logs: `docker logs ollama` (if containerized)

---

## File Organization

After completing all tests:

```
benchmarks/causal_cardiac/
├── smoke_test_results/           (40 predictions)
├── smoke_test_scored/            (scores + leakage report)
├── results_full/                 (800 predictions)
├── scored_results_full/          (scores + comparison)
└── archive/                      (optional: move old results here)
```

To clean up old runs:
```bash
mv smoke_test_results smoke_test_results.$(date +%Y%m%d)
mv smoke_test_scored smoke_test_scored.$(date +%Y%m%d)
```

---

## Next Steps

After evaluation:

1. **Analysis:** Review `comparison_summary.txt` for key findings
2. **Reporting:** Generate plots from `comparison_summary.json`
3. **Optimization:** If scores are low, consider:
   - Adjusting rubric weights
   - Refining system prompts
   - Adding more external knowledge context
4. **Publication:** Archive results with timestamp for reproducibility

---

## Commands Quick Reference

```bash
# Smoke test
node smoke_test.mjs                    # Run predictions
node smoke_test_scoring.mjs            # Score + leakage check

# Full evaluation
node run_full_evaluation.mjs           # Run all 800 predictions
node full_evaluation_scoring.mjs       # Score + comparison

# Inspect results
cat smoke_test_scored/all_smoke_scored.json | jq .
cat scored_results_full/comparison_summary.txt
```

---

## Data Leakage Detection Details

### Benchmark A Checks

1. **Magnitude proximity:** `|predicted - actual| < 0.5%`
   - Flags troponin magnitude predictions suspiciously close to ground truth
   - False positive: Model genuinely accurate
   - Real leakage: "expected_magnitude_pct: 12.5" visible in prompt

2. **Direction match:** (future enhancement)
   - Could add check for troponin direction appearing in causal text verbatim

### Benchmark B Checks

1. **Perfect procedure match:** All 7 procedures selected correctly with high confidence
   - False positive: Model very confident but actually correct
   - Real leakage: Procedure names in the case description

---

## Appendix: Scoring Rubrics (Quick Reference)

### Benchmark A

| Dimension | Weight | Details |
|-----------|--------|---------|
| Direction | 40% | Rising/falling/stable accuracy |
| Magnitude | 30% | % error vs ground truth |
| Causal Justification | 20% | Quality of mechanistic explanation |
| Confidence Calibration | 10% | Does confidence match accuracy? |

### Benchmark B

| Dimension | Weight | Details |
|-----------|--------|---------|
| Selection (F1) | 40% | Precision + Recall of procedure selection |
| Causal Justification | 30% | Quality of mechanistic explanation |
| Justification Precision | 20% | Per-procedure role articulation |
| Calibration | 10% | Per-procedure confidence vs correctness |
