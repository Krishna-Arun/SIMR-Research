# Causal Cardiac Benchmarks — Execution Log

## Timeline

### Phase 1: Case Generation ✅ COMPLETE
- **Start:** 2026-06-23 16:52 (approx)
- **Duration:** ~2 minutes
- **Result:** 200 cases generated
  - Benchmark A: 100 cases (a_001.json ... a_100.json)
  - Benchmark B: 100 cases (b_001.json ... b_100.json)
- **Location:** `questions/` folder (4.7 MB total)
- **Manifests:** 
  - `outputs/intervention_physiological_effect_manifest_v1.json`
  - `outputs/physiological_intervention_attribution_manifest_v1.json`

### Phase 2: Evaluation (IN PROGRESS)
- **Start:** 2026-06-23 16:57 (approx)
- **Expected Duration:** 2-4 hours
- **Process:** `node run_causal_evaluation.mjs`
- **Model:** Qwen 3.6 via Ollama (http://localhost:11434/v1)
- **Concurrency:** 5 cases in parallel
- **Total Cases:** 200 (Benchmark A: 100 with PubMed + 100 without) × (Benchmark B: 100 with PubMed + 100 without)

**Progress:**
```
Benchmark A: WITH PubMed
  [running...]
```

**Output Files (being written):**
- `results/a_with_pubmed_results.json`
- `results/a_without_pubmed_results.json`
- `results/b_with_pubmed_results.json`
- `results/b_without_pubmed_results.json`

### Phase 3: Scoring (PENDING)
- **Start:** After evaluation completes
- **Duration:** ~5-10 minutes
- **Process:** `node score_predictions.mjs`
- **Input:** Results from Phase 2
- **Output:**
  - `scored_results/a_with_pubmed_scored.json`
  - `scored_results/a_without_pubmed_scored.json`
  - `scored_results/b_with_pubmed_scored.json`
  - `scored_results/b_without_pubmed_scored.json`
  - `scored_results/aggregate_summary.json`

---

## Evaluation Details

### Benchmarks

**Benchmark A: Intervention → Physiological Effect**
- Input: Pre-intervention patient state + procedure name
- Output: Predicted lab trajectory (direction + magnitude)
- Cases: 100
- Conditions: 2 (with PubMed, without PubMed)
- Model: Qwen 3.6 via Ollama

**Benchmark B: Physiology → Intervention Attribution**
- Input: Pre + post lab changes (procedure hidden)
- Output: Ranked list of 21 candidate procedures (identify top-7)
- Cases: 100
- Conditions: 2 (with PubMed, without PubMed)
- Model: Qwen 3.6 via Ollama

### Confidence Extraction

Each prediction includes confidence metrics from token logits:
```json
{
  "categorical": "high | medium | low",
  "score": 0.87,           // [0, 1] from logprobs
  "logprob_avg": -1.23,    // average log probability
  "entropy": 0.34,         // Shannon entropy
  "n_tokens": 312
}
```

### Scoring Rubrics

**Benchmark A Weights:**
- Direction accuracy: 40%
- Magnitude accuracy: 30%
- Causal justification: 20%
- Confidence calibration: 10%

**Benchmark B Weights:**
- Ranking accuracy: 40%
- Top-3 quality: 20%
- Causal justification: 30%
- Confidence correlation: 10%

---

## Data Flow

```
questions/ (200 case files)
    ↓
run_causal_evaluation.mjs (calls Qwen via Ollama)
    ↓
results/ (4 result files with predictions + confidence)
    ↓
score_predictions.mjs (grades predictions)
    ↓
scored_results/ (4 scored files + aggregate summary)
```

---

## Expected Output Summary

After scoring completes, each benchmark/condition will have:

```json
{
  "benchmark": "intervention_physiological_effect",
  "condition": "with_pubmed",
  "model": "qwen3.6:latest",
  "summary": {
    "n_scored": 100,
    "n_failed": 0,
    "mean_score": 0.65,
    "median_score": 0.71,
    "std_score": 0.18,
    "score_distribution": {
      "excellent": 25,
      "good": 35,
      "fair": 30,
      "poor": 10
    }
  },
  "component_scores": {
    "direction_accuracy": 0.78,
    "magnitude_accuracy": 0.65,
    "causal_justification": 0.62,
    "confidence_calibration": 0.58
  },
  "confidence_analysis": {
    "high_confidence_accuracy": 0.82,
    "medium_confidence_accuracy": 0.55,
    "low_confidence_accuracy": 0.35
  }
}
```

---

## Next Steps

1. ⏳ Monitor evaluation progress (Phase 2)
2. 📊 Run scoring script (Phase 3)
3. 📈 Analyze results and confidence calibration
4. 💾 Commit final results to git

---

## Resources

- Evaluation log: `evaluation.log` (stdout)
- Progress check: `./check_progress.sh`
- Benchmark documentation: `README.md`, `SCORING_RUBRIC.md`
