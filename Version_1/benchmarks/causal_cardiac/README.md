# Causal Cardiac Benchmark

A single benchmark tests whether LLM agents reason causally about cardiac physiology interventions, or rely on memorized associations.

## Benchmark

### Benchmark A: Intervention → Physiological Effect (Forward Causal Prediction)

**Task:** Given a patient's pre-intervention clinical state + a procedure, predict post-intervention lab trajectory (direction + magnitude).

**What it tests:** Does the model use interventions as causal inputs that modify patient-specific trajectories?

**Example:**
```
Input: Pre-intervention labs showing troponin 0.15, CK 200, high BP. 
       Procedure: PTCA + drug-eluting stent on LAD
Output: Expected troponin direction (falling), magnitude (~-15% over 48h)
Causal reasoning: "PTCA restores coronary perfusion, enabling troponin washout..."
```

**Scoring:** direction (40%) + magnitude (30%) + causal justification (20%) + confidence calibration (10%)

---

## Architecture

```
benchmarks/causal_cardiac/
├── prep_common.py                      # Shared utilities: MIMIC data loading, lab/proc linking
├── prep_intervention_attribution.py    # Benchmark A: case discovery & generation
├── ollama_qwen_agent.mjs               # Qwen 3.6 agent via Ollama + logprobs extraction
├── run_causal_evaluation.mjs           # Main evaluation orchestrator
├── run_all_benchmarks.sh               # Full pipeline (prep → eval)
├── SCORING_RUBRIC.md                   # Detailed scoring criteria
└── README.md                           # This file
```

---

## Running the Benchmarks

### Prerequisites

1. **Ollama running** with Qwen 3.6:
   ```bash
   ollama pull qwen3.6:latest
   ollama serve
   ```

2. **Node.js + OpenAI SDK:**
   ```bash
   npm install openai
   ```

3. **Python 3.8+** with pandas:
   ```bash
   pip install pandas
   ```

### Step 1: Generate Cases (100 cases)

```bash
cd benchmarks/causal_cardiac/

# Benchmark A: Intervention → Physiological Effect
python3 prep_intervention_attribution.py
```

**Output:**
- `questions/a_001.json` ... `questions/a_100.json` (Benchmark A cases)
- `outputs/intervention_physiological_effect_manifest_v1.json`

### Step 2: Run Evaluation

```bash
# Run Benchmark A with & without PubMed access
node run_causal_evaluation.mjs
```

**Output:**
- `results/a_with_pubmed_results.json`
- `results/a_without_pubmed_results.json`

### Or: Full Pipeline

```bash
chmod +x run_all_benchmarks.sh
./run_all_benchmarks.sh
```

---

## Confidence Extraction from Activations

Each Qwen prediction includes confidence metrics extracted from **token log probabilities**:

```json
{
  "confidence": {
    "categorical": "high | medium | low",
    "score": 0.87,           // [0, 1] computed from logits
    "logprob_avg": -1.23,    // Average log probability per token
    "entropy": 0.34,         // Shannon entropy of token distribution
    "n_tokens": 312
  }
}
```

**How confidence_score is computed:**
```
confidence = 0.6 * normalize(logprob) + 0.4 * normalize(1 - entropy)

- normalize(logprob): maps [-15, 0] → [0, 1]
- normalize(entropy): maps [0, 5] → [1, 0] (inverted: lower entropy = higher confidence)
- Thresholds: high (≥0.70), medium (0.40-0.70), low (<0.40)
```

**Post-hoc calibration:** We cross-tab confidence vs. actual accuracy to measure how well the model's confidence predicts correctness.

---

## Scoring

See `SCORING_RUBRIC.md` for detailed criteria.

### Quick Summary

**Benchmark A Total Score:**
```
score = 0.40 * direction_acc + 0.30 * magnitude_acc + 0.20 * causal_just + 0.10 * conf_calib
```

Ranges [0, 1].

---

## Data Sources

- **MIMIC-IV Cardiac Extension** (`heart_labevents_examination_group.csv`, `heart_procedures.csv`, `heart_diagnoses_all_true.csv`)
- **100 cases** derived from real patient admissions with serial labs + procedures
- **No data leakage:** Case generation extracts only pre-intervention data; ground truth hidden from agent

---

## Key Features

✅ **Real clinical data** from MIMIC-IV  
✅ **Forward causal reasoning task** (intervention → physiological effect)  
✅ **Confidence from token logits** (not just categorical labels)  
✅ **Comprehensive rubrics** with mechanistic reasoning grading  
✅ **With/without external knowledge** (PubMed access condition)  
✅ **Structured JSON output** for automated scoring  
✅ **Calibration metrics** (confidence vs. accuracy analysis)  

---

## Timeline

- **Case generation:** ~5-10 min (100 cases)
- **Evaluation (100 cases × 2 conditions):** ~1-2 hours via Ollama (depends on model speed)

---

## Notes

- Requires Ollama with Qwen 3.6 locally (models run on GPU/CPU)
- Node.js OpenAI SDK communicates with Ollama's `/v1` endpoint
- Logprobs extraction assumes Ollama's completions API supports `logprobs=true`
- PubMed condition is a placeholder; currently no actual PubMed tools integrated (prep for future MCP expansion)

---

## Contact

For questions on case generation or scoring, see:
- `prep_common.py` for MIMIC data loading utilities
- `SCORING_RUBRIC.md` for detailed scoring criteria
- Comments in `run_causal_evaluation.mjs` for evaluation logic
