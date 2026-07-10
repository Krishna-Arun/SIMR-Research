# Quick Start Guide

## 5-Minute Setup

### 1. Verify Files Are in Place

```bash
cd /scratch/users/karun09/CAUSAL_BENCHMARK

# Check structure
ls -la
# Should show: questions/ answers/ outputs/ scripts/ data/ docs/ metrics/ models/

# Check key files
ls questions/questions.json        # ✓ 30 questions
ls data/matched_pairs.json         # ✓ 30 matched pairs
ls scripts/benchmark_runner.py     # ✓ Evaluation script
```

### 2. View a Sample Question

```bash
python3 << 'EOF'
import json

with open('questions/questions.json') as f:
    data = json.load(f)

q = data['questions'][0]

print("=" * 70)
print("QUESTION:")
print("=" * 70)
print(q['question_stem'][:500] + "...")
print()
print("=" * 70)
print("GROUND TRUTH (hidden from model):")
print("=" * 70)
print(f"Case A: {q['ground_truth']['case_a']['direction']} by {q['ground_truth']['case_a']['change']:+.4f}")
print(f"Case B: {q['ground_truth']['case_b']['direction']} by {q['ground_truth']['case_b']['change']:+.4f}")
print()
print("Evaluation rubric: 4 components (direction, causality, timing, reasoning)")
EOF
```

---

## Run Benchmark (3 Steps)

### Step 1: Install Dependencies

```bash
python3 -m pip install --user numpy pandas scipy transformers torch
```

### Step 2: Configure Models to Test

Edit `scripts/benchmark_runner.py`:

```python
# Line ~50, change:
MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),      # ← Add your models
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    # ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
    # ("mistralai/Mistral-7B-Instruct-v0.1", "huggingface"),
]

PROMPT_STYLES = ["zero_shot", "cot", "few_shot"]  # Try all 3
```

### Step 3: Run Evaluation

```bash
cd /scratch/users/karun09/CAUSAL_BENCHMARK

python3 scripts/benchmark_runner.py

# Wait for completion (2-30 minutes depending on GPU + model size)
# Results appear in outputs/
```

---

## View Results

### Summary Report

```bash
cat outputs/RESULTS.md
```

**Shows:**
- Model comparison table
- MCCS scores (causal understanding)
- TCAE scores (timing accuracy)
- IEC scores (calibration)
- Invariance test results

### Full Metrics

```bash
cat outputs/benchmark_results.json | python3 -m json.tool | less
```

**Contains:**
- Per-question scores
- Model predictions vs ground truth
- Confidence scores
- Detailed rubric evaluation

### Model Responses

```bash
cat answers/model_name_responses.json
```

**Contains:**
- What each model said for each question
- How the response was scored
- Detailed rubric breakdown

---

## Understanding Your Results

### Good Model Results

```
MCCS: 0.68+        ✓ Gets causal direction right
TCAE: <6 hours     ✓ Predicts realistic timing
IEC: <0.05         ✓ Well-calibrated
Invariance: ✓      ✓ Uses intervention, not confounders

→ Model understands causality!
```

### Poor Model Results

```
MCCS: 0.50-0.55    ✗ No better than random guessing
TCAE: >12 hours    ✗ Completely wrong timing
IEC: >0.2          ✗ Miscalibrated
Invariance: ✗      ✗ Ignores interventions

→ Model doesn't understand causality
```

---

## Common Scenarios

### Scenario 1: Test with Mock (No GPU Needed)

```python
# In scripts/benchmark_runner.py, use:
MODELS_TO_TEST = [
    ("mock", "mock"),
]
```

Run: `python3 scripts/benchmark_runner.py`
Time: <1 minute
Result: Baseline scores (should be ~0.43 MCCS - below random)

### Scenario 2: Test with Ollama (Local, Fast)

**Install Ollama:** https://ollama.ai

**Start server:**
```bash
ollama serve
```

**Pull models:**
```bash
ollama pull qwen
ollama pull deepseek-coder
```

**Configure:**
```python
MODELS_TO_TEST = [
    ("qwen", "ollama"),
    ("deepseek-coder", "ollama"),
]
```

### Scenario 3: Test with Hugging Face (Quality, Needs GPU)

```python
MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    ("meta-llama/Llama-2-7b-chat-hf", "huggingface"),
]
```

**Requirements:**
- GPU with 16+ GB VRAM
- 100+ GB disk space
- 30-60 minutes per model

---

## File Organization

### You'll Create These Files:

```
answers/
├── qwen_7b_responses.json
├── deepseek_responses.json
├── llama_responses.json
└── ...

outputs/
├── benchmark_results.json       ← All metrics
├── model_comparison.json        ← Rankings
└── RESULTS.md                  ← Summary table
```

### Pre-Generated Files:

```
questions/
├── questions.json              ← 30 questions (read-only)

data/
├── episodes.json               ← 40 episodes (read-only)
├── matched_pairs.json          ← 30 pairs (read-only)
└── encoded_features.json       ← Confounders (read-only)
```

---

## Troubleshooting

### Import Error: No module named 'numpy'

```bash
python3 -m pip install --user numpy pandas scipy
```

### Model Download Fails

```bash
# Check disk space
df -h

# Try smaller model
MODELS_TO_TEST = [
    ("Qwen/Qwen2-1.5B-Instruct", "huggingface"),  # ← Smaller
]
```

### Out of Memory

```python
# Use smaller model
"Qwen/Qwen2-1.5B-Instruct"  # 1.5B is fast, fits 8GB VRAM

# Or use Ollama (more memory-efficient)
("qwen", "ollama")
```

### Slow on CPU

```python
# Try smallest models only
MODELS_TO_TEST = [
    ("microsoft/phi-2", "huggingface"),  # Fast on CPU
    ("Qwen/Qwen2-1.5B-Instruct", "huggingface"),
]
```

---

## Next Steps

1. **Run with mock** (1 min): Test the pipeline
   ```bash
   # Edit to use ("mock", "mock")
   python3 scripts/benchmark_runner.py
   # Check outputs/RESULTS.md
   ```

2. **Run with real models** (30-60 min): See actual performance
   ```bash
   # Edit to use your models
   python3 scripts/benchmark_runner.py
   # Compare MCCS scores
   ```

3. **Analyze results**: Which models understand causality?
   - MCCS > 0.65? ✓ Good
   - TCAE < 6h? ✓ Good timing
   - IEC < 0.05? ✓ Well-calibrated
   - Invariance ✓? ✓ Actually causal

4. **Try different prompts**:
   ```python
   PROMPT_STYLES = ["zero_shot", "cot", "few_shot"]
   ```

---

## Key Commands

```bash
# View 30 questions
python3 << 'EOF'
import json
with open('questions/questions.json') as f:
    print(f"Total questions: {json.load(f)['n_questions']}")
EOF

# Run benchmark
python3 scripts/benchmark_runner.py

# Check results
cat outputs/RESULTS.md

# View model responses
python3 -c "import json; print(json.dumps(json.load(open('answers/model_responses.json')), indent=2)[:1000])"

# See metrics
python3 -c "import json; r=json.load(open('outputs/benchmark_results.json')); print(f\"Models tested: {len(r['results'])}\")"
```

---

## Support

**Questions?** Check:
- `docs/BENCHMARK_EXPLAINED.md` - Simple explanation
- `docs/HOW_IT_WORKS.md` - Technical details
- `docs/SPECIFICATION.md` - Full methodology

**Files provided:**
- 30 questions with hidden ground truth
- Evaluation rubrics
- Metrics implementation
- LLM inference wrapper

**Your job:**
- Configure models to test
- Run the benchmark
- Analyze results

---

**Status: READY TO RUN** ✨

Everything is set up. Just configure your models and run!

