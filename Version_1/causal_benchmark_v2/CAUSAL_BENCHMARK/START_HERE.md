# 🎯 START HERE

## Welcome to the Causal Intervention Benchmark

This is a **complete, production-ready benchmark** for evaluating whether open-source LLMs understand medical causality.

---

## ⚡ In 30 Seconds

**What:** 30 clinical questions comparing similar patients with different medical interventions

**Why:** Tests if LLMs understand that interventions cause different outcomes (causal reasoning, not just memorization)

**How:** 
1. Models read clinical questions (ground truth hidden)
2. Models make predictions
3. We score using 4 rubric components
4. We compute causal metrics (MCCS, TCAE, IEC)

**Result:** Identifies which LLMs actually understand medical causality

---

## 📚 Documentation Map

### Quick Navigation

Start with one of these based on your goal:

**I want to run the benchmark right now**
→ Read: `QUICK_START.md` (5 minutes)

**I want to understand what this benchmark does**
→ Read: `docs/BENCHMARK_EXPLAINED.md` (10 minutes)

**I want to understand the full methodology**
→ Read: `docs/SPECIFICATION.md` (30 minutes)

**I want to know the technical details**
→ Read: `ARCHITECTURE.md` + `docs/HOW_IT_WORKS.md` (20 minutes)

---

## 🚀 Quick Start (5 Minutes)

### 1. Verify Setup

```bash
cd /scratch/users/karun09/CAUSAL_BENCHMARK
ls -la
# Should show: questions/, answers/, outputs/, data/, docs/, scripts/, models/, metrics/
```

### 2. View a Question

```bash
python3 << 'EOF'
import json

with open('questions/questions.json') as f:
    data = json.load(f)
    q = data['questions'][0]
    print("QUESTION STEM:")
    print(q['question_stem'][:800])
    print("\n[GROUND TRUTH - NOT SHOWN TO MODEL]")
    print(f"Case A: {q['ground_truth']['case_a']['direction']} by {q['ground_truth']['case_a']['change']:+.4f}")
    print(f"Case B: {q['ground_truth']['case_b']['direction']} by {q['ground_truth']['case_b']['change']:+.4f}")
EOF
```

### 3. Configure Models

Edit `scripts/run_question_benchmark.py`, line ~50:

```python
MODELS_TO_TEST = [
    ("Qwen/Qwen2-7B-Instruct", "huggingface"),
    ("deepseek-ai/deepseek-llm-7b-chat", "huggingface"),
    # Add your models here
]
```

### 4. Run Benchmark

```bash
python3 scripts/run_question_benchmark.py
```

### 5. Check Results

```bash
cat outputs/RESULTS.md
```

---

## 📋 What You Have

### 30 Clinical Questions

Each question tests causal understanding:
- Scenario: 2 similar patients with different interventions
- Ground truth: Hidden outcomes
- Scoring: 4 components (direction, causality, timing, reasoning)
- Interventions: PCI, vasopressors, antibiotics, observation

### 40 Clinical Episodes

Pre-processed data from EHRSHOT cardiac benchmark:
- 48h clinical history (labs, diagnoses, medications)
- Intervention point
- 48h post-intervention trajectory

### 30 Matched Pairs

Rigorous causal setup:
- Same severity level
- Same pre-trend direction
- Similar confounders
- Different interventions
- Perfect covariate balance (SMD < 0.1)

### 5 Evaluation Metrics

**MCCS** (Primary)
- Did model predict correct intervention direction?
- 0.5 = random, 0.65+ = good, 0.75+ = excellent

**TCAE** (Secondary)
- Did model predict realistic response timing?
- <6 hours = good

**IEC** (Secondary)
- Are outcome predictions well-calibrated?
- <0.05 = good

**Invariance Test**
- Does model use intervention or just confounders?
- ✓ = model is causal

**Shape Similarity** (Auxiliary)
- How similar are trajectory shapes?
- Lower = better, less important

---

## 🎯 Understanding Results

### Good Model Results

```
MCCS: 0.68     ← Gets causal direction right
TCAE: 4.2h     ← Predicts realistic timing
IEC: 0.012     ← Well-calibrated
Invariance: ✓  ← Actually uses interventions

→ Model understands causality!
```

### Poor Model Results

```
MCCS: 0.50     ← Same as random guessing
TCAE: 12h+     ← Wrong timing
IEC: 0.2+      ← Miscalibrated
Invariance: ✗  ← Ignores interventions

→ Model doesn't understand causality
```

---

## 📁 File Organization

```
questions/              ← Your questions (read-only)
├── questions.json      30 questions with hidden ground truth

data/                   ← Processed data (read-only)
├── episodes.json       40 clinical episodes
├── matched_pairs.json  30 matched pairs
└── encoded_features.json

scripts/                ← Data pipeline
├── run_question_benchmark.py  ← MAIN: Run this!
└── [other scripts for reference]

outputs/                ← Your results (created when you run)
├── RESULTS.md          Summary table
└── benchmark_results.json

answers/                ← LLM responses (created when you run)
├── model_name_responses.json

docs/                   ← Full documentation
├── SPECIFICATION.md    Full methodology
└── [other guides]

metrics/                ← Evaluation code
└── causal_metrics.py

models/                 ← LLM inference
└── llm_inference.py
```

---

## ❓ Common Questions

**Q: Do I need GPU?**
A: No for mock/small models. Yes (16GB+ VRAM) for 7B+ models on HuggingFace.

**Q: How long does it take?**
A: Depends on model:
- Mock: <1 minute
- Qwen 1.5B: 1-2 minutes
- Qwen 7B: 5-10 minutes
- 70B models: 30+ minutes

**Q: What interventions are tested?**
A: PCI (heart surgery), vasopressors (blood pressure support), antibiotics (infection treatment), observation (no treatment)

**Q: Can I add my own models?**
A: Yes! Edit `MODELS_TO_TEST` in `scripts/run_question_benchmark.py`

**Q: What if I don't have GPU?**
A: Use mock predictor (for testing) or Ollama with small models

---

## 🔗 Key Links

**In this folder:**
- `README.md` - Overview
- `QUICK_START.md` - How to run
- `ARCHITECTURE.md` - System design
- `docs/SPECIFICATION.md` - Full methodology
- `docs/BENCHMARK_EXPLAINED.md` - Simple explanation

**To run:**
```bash
python3 scripts/run_question_benchmark.py
```

**To check results:**
```bash
cat outputs/RESULTS.md
```

---

## ✨ What Makes This Special

✅ **Tests Causality, Not Accuracy**
- Standard benchmarks ask: "Did you predict the right number?"
- This benchmark asks: "Did you understand the intervention caused the change?"

✅ **No Fake Ground Truth**
- Uses real matched pairs instead of synthetic counterfactuals
- Methodologically sound for academic publications

✅ **Clinically Relevant**
- Tests whether AI understands when interventions help
- Directly applicable to medical decision support

✅ **Production Ready**
- 30 balanced questions
- Complete evaluation infrastructure
- Professional documentation

---

## 📞 Need Help?

1. **How to run?** → Read `QUICK_START.md`
2. **What does it test?** → Read `docs/BENCHMARK_EXPLAINED.md`
3. **Technical details?** → Read `ARCHITECTURE.md`
4. **Full methodology?** → Read `docs/SPECIFICATION.md`

---

## 🎬 Next Action

```bash
cd /scratch/users/karun09/CAUSAL_BENCHMARK
cat QUICK_START.md
```

Then configure your models and run:
```bash
python3 scripts/run_question_benchmark.py
```

---

**Status:** ✅ Ready to run  
**Questions:** 30  
**Ground truth:** Hidden  
**Metrics:** 5 (MCCS, TCAE, IEC, invariance, shape)  
**Support:** Full documentation included  

🚀 You're all set! Go benchmark some LLMs!
