# MIMIC Multi-Lab Reversal Benchmark — Smoke Test

## Overview

This is the **smoke test phase** of the multi-lab reversal benchmark. Only proceed to full 500-case evaluation **after smoke test passes**.

**Smoke test validates:**
- ✅ Ollama connection and Qwen inference
- ✅ Confidence extraction from token logits (activation function)
- ✅ JSON schema validation and parsing
- ✅ Scoring module correctness
- ✅ Results aggregation and reporting

**Test cases:** 20 representative cases across different phases
- Pre-procedure (natural disease progression)
- Peri-procedure (immediate intervention response)
- Immediate post (0-6h recovery)
- Short-term post (6-24h, most common reversal window)
- Medium-term post (24-72h, delayed complications)

---

## Prerequisites

### 1. Ollama Running Locally
```bash
# Install Ollama if needed
# https://ollama.ai

# Pull Qwen model
ollama pull qwen:latest

# Start Ollama server (if not already running)
ollama serve
```

Verify Ollama is running:
```bash
curl http://localhost:11434/api/tags
```

### 2. Node.js Dependencies
```bash
cd benchmarks/mimic_multilab_reversal
npm install
```

---

## Running the Smoke Test

### Quick Start
```bash
cd benchmarks/mimic_multilab_reversal
npm run smoke-test
```

### Expected Output

The smoke test will:
1. Load 20 test cases
2. Run Qwen inference on each case
3. Extract confidence from token logits
4. Score predictions against ground truth
5. Generate aggregate report

**Sample output:**
```
═══════════════════════════════════════════════════════
MIMIC MULTI-LAB REVERSAL BENCHMARK — SMOKE TEST
═══════════════════════════════════════════════════════

Loaded 20 smoke test cases
Ollama endpoint: http://localhost:11434/v1
Model: qwen:latest

Running: smoke_001 (short_term_post)
  ✓ Direction accuracy: 0.833
  ✓ Reversal detection: 1.0
  ✓ Justification: 0.85
  ✓ Total score: 0.871
  ✓ Confidence: high (score: 0.87)

[... 19 more cases ...]

═══════════════════════════════════════════════════════
AGGREGATE SCORES
═══════════════════════════════════════════════════════
Cases evaluated: 20
Mean direction accuracy: 0.833
Mean reversal detection: 0.917
Mean causal justification: 0.823
Mean total score: 0.858

Score distribution:
  Excellent (≥0.85): 14
  Good (0.70-0.85): 5
  Fair (0.50-0.70): 1
  Poor (<0.50): 0

Confidence metrics:
  Mean confidence score: 0.814
  High confidence cases: 18
  Medium confidence cases: 2
  Low confidence cases: 0

✓ SMOKE TEST PASSED

Results saved to: ./results/smoke_test_results.json
```

---

## Test Case Structure

Each test case includes:

### Patient Context
```json
{
  "case_id": "smoke_001",
  "hadm_id": 12345,
  "demographics": { "age": 65, "gender": "M" },
  "comorbidities": ["CKD Stage 2", "Hypertension", "Prior MI"],
  "procedure": { "name": "PTCA + stent", "contrast_volume": 180 }
}
```

### Visible State (what the model sees)
```json
{
  "visible_state": {
    "timestamp": "2023-01-16T18:00:00Z",
    "labs": { "Troponin": 0.48, "CK": 520, "Creatinine": 1.18 },
    "visible_trends": { "Troponin": "rising", "CK": "rising", "Creatinine": "stable" }
  }
}
```

### Ground Truth (answer key)
```json
{
  "ground_truth": {
    "directions": { "Troponin": "falling", "CK": "falling", "Creatinine": "rising" },
    "reversals": { "Troponin": true, "CK": true, "Creatinine": false }
  }
}
```

### Clinical Question (what the model answers)
```
"Given this patient's baseline kidney function (eGFR 60, CKD Stage 2), 
prior MI, and the high contrast volume used, predict what will happen 
at 2023-01-17 10:00 (24 hours post-procedure):
1. Will Troponin rise, fall, or stay stable?
2. Will CK rise, fall, or stay stable?
3. Will Creatinine rise, fall, or stay stable?
For EACH lab, explain the mechanism using this patient's specific factors..."
```

---

## Confidence Extraction (Token Logits)

The benchmark extracts confidence from Qwen's token logits:

**Metrics computed per response:**
- `average_logprob` — mean log probability of tokens
- `min_logprob` — lowest probability token (bottleneck)
- `average_entropy` — Shannon entropy of token distributions
- `confidence_score` — normalized [0,1] (60% logprob + 40% entropy)
- `confidence_level` — categorical (high/medium/low)

**Example output:**
```json
{
  "average_logprob": -1.234,
  "min_logprob": -3.456,
  "average_probability": 0.291,
  "average_entropy": 0.456,
  "confidence_score": 0.814,
  "confidence_level": "high",
  "n_tokens": 312
}
```

---

## Scoring Breakdown

### Direction Accuracy (40% weight)
- **1.0** — Predicted direction matches ground truth for that lab
- **0.0** — Predicted direction doesn't match

### Reversal Detection (30% weight)
- **1.0** — Correctly identified whether reversal occurs
- **0.0** — Missed reversal or hallucinated reversal

### Causal Justification (20% weight)
- **1.0** — Explains mechanism + baseline + complications + timeline + patient-specific
- **0.75** — Clear mechanism + baseline; timeline/complications mentioned
- **0.5** — Mechanism + baseline without patient context
- **0.25** — Vague; barely addresses mechanism
- **0.0** — No justification

### Confidence Calibration (10% weight)
- **1.0** — High confidence + ≥75% accuracy
- **0.75** — High confidence + ≥50% accuracy
- **0.5** — Medium confidence + ≥50% accuracy
- **0.25** — High confidence + <50% accuracy
- **0.0** — Low confidence

---

## Results Files

After running, results are saved to `./results/`:

```
results/
├── smoke_test_results.json          # Full results (cases + aggregated scores)
└── (future: full_experiment_results.json)
```

---

## Next Steps (After Smoke Test Passes)

1. **Validate confidence correlations** — Check if high-confidence predictions actually have higher accuracy
2. **Expand test cases** — Move to 100-case full evaluation
3. **Compare against baselines** — Measure against random/naive baselines
4. **Scale to 500 cases** — Full benchmark evaluation

---

## Troubleshooting

### "Ollama connection refused"
- Ensure Ollama is running: `ollama serve`
- Check endpoint: `curl http://localhost:11434/api/tags`

### "Model not found: qwen:latest"
- Pull the model: `ollama pull qwen:latest`
- Verify: `ollama list | grep qwen`

### "JSON parsing failed"
- Qwen may be returning markdown code fences; the parser auto-cleans these
- If still failing, check Qwen's raw output in the error log

### Cases are too slow
- Reduce `max_tokens` in config.yaml (currently 4096)
- Run fewer cases in parallel (modify smoke_test.mjs)
- Use a faster Qwen variant (qwen:4b instead of full model)

---

## File Structure

```
benchmarks/mimic_multilab_reversal/
├── package.json                     # Node.js dependencies
├── config.yaml                      # Configuration
├── smoke_test.mjs                   # ← RUN THIS
├── models/
│   └── ollama_qwen_agent.mjs       # Qwen inference + confidence extraction
├── scoring/
│   └── score.mjs                    # Direction, reversal, justification scoring
├── cases/
│   ├── smoke_test_cases.json        # 20 test cases
│   └── (future: full_dataset/)
└── results/
    └── smoke_test_results.json      # Output (generated after running)
```

---

## Ready to Test?

```bash
npm run smoke-test
```

🚀 **The benchmark is modular and extensible.** Once smoke test passes, expanding to 500 cases only requires:
1. Generating more MIMIC case JSON files
2. Pointing the runner to the full dataset
3. Tuning batch size and parallelism

