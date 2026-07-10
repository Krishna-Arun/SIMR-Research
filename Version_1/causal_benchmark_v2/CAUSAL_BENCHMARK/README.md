# Causal Intervention Benchmark

A NeurIPS-grade benchmark for evaluating whether open-source LLMs can predict physiological trajectories conditioned on medical interventions while correctly accounting for observational confounding.

## 📁 Directory Structure

```
CAUSAL_BENCHMARK/
├── README.md                    ← You are here
├── QUICK_START.md              ← How to run the benchmark
├── ARCHITECTURE.md             ← System design
│
├── questions/                  ← 30 clinical questions
│   └── questions.json          ← Ground truth hidden
│
├── answers/                    ← LLM responses
│   └── [model_name]_responses.json
│
├── outputs/                    ← Evaluation results
│   ├── benchmark_results.json  ← Metrics (MCCS, TCAE, IEC, etc)
│   ├── RESULTS.md             ← Summary report
│   └── model_comparison.json  ← Model rankings
│
├── scripts/                    ← Data pipeline & evaluation
│   ├── convert_cardiac_benchmark.py    (Step 1: Extract episodes)
│   ├── encode_features.py              (Step 2: Encode confounders)
│   ├── construct_matched_pairs.py      (Step 3: Match pairs)
│   ├── generate_questions.py           (Step 4: Generate questions)
│   └── benchmark_runner.py             (Step 5: Evaluate models)
│
├── data/                       ← Processed data files
│   ├── episodes.json           ← 40 clinical episodes
│   ├── encoded_features.json   ← Patient confounders
│   ├── matched_pairs.json      ← 30 matched pairs
│   └── questions.json          ← 30 benchmark questions
│
├── docs/                       ← Full documentation
│   ├── SPECIFICATION.md        ← Full methodology
│   ├── BENCHMARK_EXPLAINED.md  ← Simple guide
│   ├── HOW_IT_WORKS.md        ← Technical details
│   ├── STATUS_COMPLETE.md      ← Current status
│   └── QUESTIONS_GENERATED.md  ← Question details
│
├── metrics/                    ← Evaluation metrics
│   ├── causal_metrics.py       ← MCCS, TCAE, IEC, invariance test
│   └── __init__.py
│
└── models/                     ← LLM inference
    ├── llm_inference.py        ← Qwen, DeepSeek, Llama, Mistral wrapper
    └── __init__.py
```

---

## ⚡ Quick Start

### 1. View Questions (What Models Will Be Asked)

```bash
# See 30 clinical benchmark questions
python3 << 'EOF'
import json

with open('questions/questions.json') as f:
    data = json.load(f)

q = data['questions'][0]
print(q['question_stem'])
print("\n[GROUND TRUTH - NOT SHOWN TO MODEL]")
print(q['ground_truth'])
print("\n[EVALUATION RUBRIC]")
print(json.dumps(q['evaluation_rubric'], indent=2))
EOF
```

### 2. Run Benchmark with LLMs

```bash
# Edit scripts/benchmark_runner.py to configure models
# Then run:

python3 scripts/benchmark_runner.py

# Results appear in outputs/
```

### 3. Check Results

```bash
cat outputs/RESULTS.md        # Summary table
cat outputs/benchmark_results.json | python3 -m json.tool  # Full metrics
```

---

## 📊 What This Benchmark Tests

**Question:** Can an AI model understand that medical interventions cause different outcomes?

**Example:**
```
Patient A: Gets PCI (heart surgery)
Patient B: No intervention

Question: Will patient A have better outcomes?

Good model: "Yes, PCI limits heart damage → troponin falls faster"
Bad model: "I don't know, maybe both are the same"
```

### The 5 Evaluation Metrics

| Metric | What It Tests | Good Value |
|--------|---------------|-----------|
| **MCCS** | Does model predict correct intervention direction? | 0.65+ |
| **TCAE** | Does model predict realistic timing? | <6 hours |
| **IEC** | Are predictions well-calibrated? | <0.05 |
| **Invariance** | Does model use intervention (not just confounders)? | ✓ Passes |
| **Shape** | How similar are trajectory shapes? | Auxiliary |

---

## 🔧 Configuration

### Adding Models to Test

Edit `scripts/benchmark_runner.py`:

```python
MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
    ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),
    ("microsoft/phi-2", "huggingface"),
]
```

Supported backends:
- `huggingface`: Remote models via Hugging Face
- `ollama`: Local models via Ollama
- `mock`: Synthetic predictions (for testing)

### Changing Prompt Strategy

```python
PROMPT_STYLES = ["zero_shot", "cot", "few_shot"]
```

- `zero_shot`: Direct prediction, no examples
- `cot`: Chain-of-thought (explicit reasoning)
- `few_shot`: 2-5 clinical examples for in-context learning

---

## 📈 Understanding Results

### MCCS (Matched Counterfactual Consistency Score)

```
MCCS = % of matched pairs where model predicts correct direction

Example:
├─ Pair 1: PCI vs Observation
│  Real: PCI better (troponin falls more)
│  Model predicts: PCI better ✓
│
├─ Pair 2: Vasopressors vs Observation
│  Real: Vasopressors better
│  Model predicts: Vasopressors better ✓
│
├─ Pair 3: Antibiotics vs Observation
│  Real: Antibiotics better
│  Model predicts: No difference ✗

MCCS = 2/3 = 0.67 (67% accuracy)

Interpretation:
├─ 0.50 = Random guessing
├─ 0.65 = Good understanding
└─ 0.75+ = Excellent understanding
```

### TCAE (Temporal Causal Alignment Error)

```
TCAE = How many hours off is the model's timing?

Example:
├─ PCI expected to work: 2-6 hours
├─ Model predicts: Works at 10 hours
└─ Error: 4-8 hours late

TCAE = 6 hours (WORSE)

Interpretation:
├─ <2h = Perfect
├─ 2-6h = Good
└─ >12h = Poor
```

### Full Results Example

```
| Model | Prompt | MCCS | TCAE | IEC | Invariance | Status |
|-------|--------|------|------|-----|-----------|--------|
| Qwen 7B | CoT | 0.68 | 4.2h | 0.012 | ✓ | GOOD |
| DeepSeek 7B | CoT | 0.65 | 5.1h | 0.014 | ✓ | GOOD |
| Llama 7B | CoT | 0.62 | 6.3h | 0.016 | ~ | MEDIUM |
| Mistral 7B | Zero | 0.58 | 8.5h | 0.020 | ✗ | POOR |

Interpretation:
├─ Qwen: Understands causality, good timing
├─ DeepSeek: Competitive with Qwen
├─ Llama: OK but slower to respond
└─ Mistral (zero-shot): Needs better prompting
```

---

## 📋 Data Overview

### 30 Clinical Questions

Balanced across 6 intervention pair types:
- PCI vs Observation (5 questions)
- PCI vs Vasopressors (5 questions)
- PCI vs Antibiotics (5 questions)
- Vasopressors vs Observation (5 questions)
- Vasopressors vs Antibiotics (5 questions)
- Antibiotics vs Observation (5 questions)

### 40 Clinical Episodes

From cardiac benchmark:
- 48h pre-context (clinical history)
- Intervention point (PCI, vasopressors, antibiotics, or observation)
- 48h post-window (trajectory to predict)

### Matched Pairs (30)

Perfect covariate balance:
- Same severity bin
- Same pre-trend direction
- Similar magnitude
- Different interventions

---

## 🚀 Running the Full Pipeline

```bash
# Step 1: Extract episodes (already done)
python3 scripts/convert_cardiac_benchmark.py

# Step 2: Encode confounders
python3 scripts/encode_features.py

# Step 3: Match pairs
python3 scripts/construct_matched_pairs.py

# Step 4: Generate questions
python3 scripts/generate_questions.py

# Step 5: Evaluate models
python3 scripts/benchmark_runner.py

# Results in outputs/
```

---

## 📖 Documentation

For detailed information, see:

- **Quick Start:** See this file
- **Architecture:** `docs/SPECIFICATION.md` (full methodology)
- **Simple Explanation:** `docs/BENCHMARK_EXPLAINED.md` (easy to understand)
- **Technical Details:** `docs/HOW_IT_WORKS.md` (implementation details)
- **Status:** `docs/STATUS_COMPLETE.md` (current state)
- **Questions:** `docs/QUESTIONS_GENERATED.md` (question details)

---

## 🎯 Key Features

✅ **Tests Causality, Not Accuracy**
- Standard: "Did you predict the right number?"
- Ours: "Did you understand the intervention caused the change?"

✅ **No Fake Ground Truth**
- Uses matched observational pairs instead of synthetic counterfactuals
- Methodologically sound for NeurIPS review

✅ **Clinically Relevant**
- Tests whether AI understands when interventions help
- Applicable to medical decision support

✅ **Mathematically Rigorous**
- Explicitly controls for confounders
- Tests causal vs. correlational learning

---

## 📝 Questions?

Refer to the documentation in `docs/` directory or check the Python docstrings in the scripts.

---

**Status:** ✅ Questions generated, ready for model evaluation

