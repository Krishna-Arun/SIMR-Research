# System Architecture

## Data Flow

```
┌────────────────────────────────────────────────────────────────┐
│                    CAUSAL INTERVENTION BENCHMARK               │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   INPUT: Cardiac Benchmark Data     │
        │   (EHRSHOT cardiac cases)           │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Step 1: Extract Episodes           │
        │  convert_cardiac_benchmark.py       │
        │  - 48h pre-context + intervention   │
        │  - 48h post-window (trajectory)     │
        │  Output: episodes.json (40 cases)   │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Step 2: Encode Confounders         │
        │  encode_features.py                 │
        │  - SOFA severity scores             │
        │  - Comorbidity vectors              │
        │  - Pre-trend features               │
        │  Output: encoded_features.json      │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Step 3: Match Pairs                │
        │  construct_matched_pairs.py         │
        │  - Same severity, diff intervention │
        │  - Perfect covariate balance        │
        │  Output: matched_pairs.json (30)    │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Step 4: Generate Questions         │
        │  generate_questions.py              │
        │  - Clinical question stems          │
        │  - Hidden ground truth              │
        │  - Evaluation rubrics               │
        │  Output: questions.json (30)        │
        └─────────────────────────────────────┘
                              │
                              ▼
    ╔═════════════════════════════════════════╗
    ║  BENCHMARK READY FOR EVALUATION         ║
    ╚═════════════════════════════════════════╝
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Step 5: Run Models                 │
        │  run_question_benchmark.py          │
        │  1. Load questions                  │
        │  2. Get LLM predictions             │
        │  3. Score against rubric            │
        │  4. Compute metrics                 │
        │  Output: Model responses            │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Results & Analysis                 │
        │  - MCCS (causal direction)          │
        │  - TCAE (timing)                    │
        │  - IEC (calibration)                │
        │  - Invariance test                  │
        │  Output: benchmark_results.json     │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │  Report Generation                  │
        │  - Comparison table (RESULTS.md)    │
        │  - Model rankings                   │
        │  - Causal understanding scores      │
        └─────────────────────────────────────┘
```

---

## Directory Structure Explained

```
CAUSAL_BENCHMARK/
│
├── questions/                  ← INPUT: Clinical benchmark questions
│   └── questions.json          30 questions with hidden ground truth
│
├── answers/                    ← OUTPUT: LLM responses
│   ├── qwen_zero_shot_responses.json
│   ├── deepseek_cot_responses.json
│   └── ... (one per model+prompt combination)
│
├── outputs/                    ← OUTPUT: Evaluation results
│   ├── benchmark_results.json  Full metrics + scores
│   ├── RESULTS.md             Summary comparison table
│   └── model_comparison.json   Rankings by MCCS
│
├── scripts/                    ← DATA PIPELINE & EVALUATION
│   ├── convert_cardiac_benchmark.py    Extract episodes
│   ├── encode_features.py              Encode confounders
│   ├── construct_matched_pairs.py      Match similar patients
│   ├── generate_questions.py           Create questions
│   └── run_question_benchmark.py       Main evaluation (use this!)
│
├── data/                       ← PROCESSED DATA (read-only)
│   ├── episodes.json           40 clinical episodes
│   ├── encoded_features.json   Patient confounders
│   ├── matched_pairs.json      30 matched pairs
│   └── questions.json          30 benchmark questions
│
├── docs/                       ← DOCUMENTATION
│   ├── SPECIFICATION.md        Full methodology (NeurIPS-grade)
│   ├── BENCHMARK_EXPLAINED.md  Simple walkthrough
│   ├── HOW_IT_WORKS.md        Technical details
│   └── STATUS_COMPLETE.md      Current state
│
├── metrics/                    ← EVALUATION METRICS
│   ├── causal_metrics.py       MCCS, TCAE, IEC, invariance
│   └── __init__.py
│
└── models/                     ← LLM INFERENCE
    ├── llm_inference.py        Qwen, DeepSeek, Llama, Mistral wrapper
    └── __init__.py
```

---

## File Dependencies

```
run_question_benchmark.py (MAIN)
├── Reads:
│   ├── questions/questions.json
│   ├── models/llm_inference.py
│   └── metrics/causal_metrics.py
│
├── Writes:
│   ├── answers/*.json (LLM responses)
│   ├── outputs/benchmark_results.json (metrics)
│   └── outputs/RESULTS.md (report)
│
└── Uses:
    ├── Hugging Face transformers (if backend="huggingface")
    ├── Ollama (if backend="ollama")
    └── Mock predictor (if backend="mock")
```

---

## Component Architecture

### 1. Question Generation Pipeline

```
Input: Matched pairs of patients
  ↓
Format: Clinical scenario + interventions
  ↓
Add: Hidden ground truth (not shown to model)
  ↓
Add: Evaluation rubric (40% direction, 40% causal, 15% timing, 5% reasoning)
  ↓
Output: questions.json (30 questions)
```

### 2. LLM Inference Interface

```
Predictor (Abstract Base)
├── HuggingFaceLLMPredictor (uses transformers)
├── OllamaLLMPredictor (uses local models)
├── MockLLMPredictor (synthetic predictions)
└── Custom Predictors (extensible)

All follow same interface:
predict(episode) → trajectory
```

### 3. Evaluation Metrics

```
Input: Model predictions + ground truth
  ↓
MCCS: Compare intervention effect directions
TCAE: Compare inflection point timing
IEC: Compare outcome distributions
Invariance: Shuffle interventions, check MCCS drops
Shape: Trajectory similarity
  ↓
Output: 5 metrics per model
```

### 4. Scoring Pipeline

```
For each (model, question) pair:
├── Get question_stem (shown to model)
├── Get model prediction
├── Parse prediction
├── Score against evaluation_rubric
│   ├── Direction accuracy (40%)
│   ├── Causal comparison (40%)
│   ├── Timing estimate (15%)
│   └── Clinical reasoning (5%)
└── Aggregate into MCCS score
```

---

## Running the Benchmark

### Standard Flow

```bash
python3 scripts/run_question_benchmark.py
```

This will:
1. Load 30 questions from questions.json
2. For each (model, prompt_style) pair:
   - Create predictor (HuggingFace/Ollama/Mock)
   - Generate predictions for all 30 questions
   - Score predictions against rubric
   - Compute MCCS + auxiliary metrics
3. Save model responses to answers/
4. Save results to outputs/benchmark_results.json
5. Generate summary report in outputs/RESULTS.md

### Expected Output

```
answers/
├── Qwen_2_7B_Instruct_zero_shot_responses.json
├── Qwen_2_7B_Instruct_cot_responses.json
├── Qwen_2_7B_Instruct_few_shot_responses.json
├── ... (repeat for other models)

outputs/
├── benchmark_results.json
│   {
│     "results": [
│       {
│         "model": "Qwen/Qwen2-7B-Instruct",
│         "prompt_style": "cot",
│         "mccs": 0.68,
│         "n_correct": 20,
│         "n_scored": 30
│       },
│       ...
│     ]
│   }
├── RESULTS.md
│   | Model | Backend | Prompt | MCCS | Status |
│   | Qwen | huggingface | cot | 0.68 | Good |
│   ...
```

---

## Extending the Benchmark

### Add a New Model

1. **Via Hugging Face:**
   ```python
   # In run_question_benchmark.py, MODELS_TO_TEST:
   MODELS_TO_TEST = [
       ("your-model/name", "huggingface"),
   ]
   ```

2. **Via Ollama:**
   ```python
   MODELS_TO_TEST = [
       ("your-model-name", "ollama"),
   ]
   ```

3. **Custom Predictor:**
   ```python
   # Create class in models/llm_inference.py
   class YourLLMPredictor(LLMPredictor):
       def predict(self, episode) -> np.ndarray:
           # Your inference logic
           return trajectory
   ```

### Add a New Question Type

1. Edit `scripts/generate_questions.py`
2. Add new intervention types to `INTERVENTION_DESCRIPTIONS`
3. Rerun: `python3 scripts/generate_questions.py`

### Add a New Metric

1. Add to `metrics/causal_metrics.py`
2. Modify `run_question_benchmark.py` to compute it
3. Update `RESULTS.md` generation to display it

---

## Performance Characteristics

### Time Estimates

| Model | Backend | Per Question | All 30 Questions |
|-------|---------|--------------|-----------------|
| Mock | mock | <0.1s | ~3s |
| Phi-2 | ollama | ~0.5s | ~15s |
| Qwen 1.5B | huggingface | ~1-2s | ~60s |
| Qwen 7B | huggingface | ~5-10s | ~5-10 min |
| DeepSeek 7B | huggingface | ~5-10s | ~5-10 min |
| Llama 70B | huggingface | ~30-60s | ~30-60 min |

(Times depend on GPU VRAM, CPU speed, batch size)

### Resource Requirements

| Model Size | GPU VRAM | Disk Space | Time (30 questions) |
|------------|----------|-----------|-------------------|
| 1.5B | 4GB | 4GB | <2 min |
| 7B | 16GB | 15GB | 5-10 min |
| 13B | 28GB | 30GB | 10-20 min |
| 70B | 80GB+ | 150GB+ | 30+ min |

---

## Quality Assurance

### Validation Checks

1. **Question Validity:**
   - All 30 questions present
   - Each has ground truth
   - Each has evaluation rubric
   - Intervention pairs balanced

2. **Data Integrity:**
   - Matched pairs have SMD < 0.1
   - No duplicate questions
   - No data leakage (ground truth hidden)

3. **Results Validation:**
   - MCCS between 0.0-1.0
   - TCAE in reasonable range
   - All metrics computed
   - Results saved

---

## Error Handling

```
Try to load questions
  ❌ No? → FileNotFoundError + exit

Create LLM predictor
  ❌ No? → Log error, skip model

Get prediction for question
  ❌ No? → Log error, continue to next

Score prediction
  ❌ No? → Log error, continue to next

Save results
  ❌ No? → Log error, but report what we have
```

---

## Summary

**This system is designed to:**
1. ✅ Generate fair causal comparison questions from real patient data
2. ✅ Evaluate LLMs on genuine causal reasoning (not just trajectory prediction)
3. ✅ Compute metrics that distinguish causal vs. correlational learning
4. ✅ Support multiple LLM backends (HuggingFace, Ollama, custom)
5. ✅ Produce publication-ready results and comparisons

**Entry point:** `scripts/run_question_benchmark.py`

**Configuration:** Edit MODELS_TO_TEST and PROMPT_STYLES in the script

**Output:** answers/ and outputs/ directories with results

