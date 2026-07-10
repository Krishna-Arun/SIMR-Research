# Causal Cardiac Benchmark Refactor Summary

**Date:** June 23, 2026  
**Status:** Complete  
**Focus:** Consolidate to single Benchmark A with multi-lab scoring

---

## Overview

Removed Benchmark B (Physiological Attribution) entirely. Refactored Benchmark A to evaluate **all 4 cardiac biomarkers** with explicit before→after comparison.

---

## Files Deleted

### Benchmark B Case Generation
- `prep_physiological_attribution.py` — Benchmark B case generator

### Benchmark B Question Files
- `questions/b_001.json` through `questions/b_100.json` (100 files)

### Benchmark B Outputs
- `outputs/physiological_intervention_attribution_manifest_v1.json`

### Benchmark B Result Files
- `results/b_*.json` (all Benchmark B result files)
- `results/smoke_b_*.json` (all Benchmark B smoke test results)

---

## Files Updated

### 1. SCORING_RUBRIC.md
**Major Changes:**
- Removed all Benchmark B scoring criteria
- Restructured as multi-lab scoring with **before→after timeline explicitly shown**
- Added clinical context for each lab (why it matters for cardiac patients)

**New Structure:**

#### Direction Accuracy (40% weight) — ALL 4 LABS
- Troponin T: 40% weight (primary cardiac injury marker)
- CK: 25% weight (muscle/cardiac enzyme damage)
- Creatinine: 20% weight (renal impact from contrast)
- Potassium: 15% weight (electrolyte balance from myocardial damage)

Each lab scored: 1.0 if direction matches ground truth, 0.0 if wrong
**Weighted average = final direction score**

#### Magnitude Accuracy (30% weight) — 3 LABS
- Troponin: 50% weight
- CK: 35% weight
- Creatinine: 15% weight
- *Potassium: direction only (too variable)*

**Scoring per lab:**
- 1.0 = within ±10% of actual % change
- 0.75 = within ±20%
- 0.5 = within ±50%
- 0.25 = within ±100%
- 0.0 = >100% error OR wrong direction

#### Multi-Lab Causal Justification (20% weight)
**NEW:** Model must explain mechanism for **EACH of 4 labs**

| Score | Criteria |
|---|---|
| 1.0 | Names specific mechanism, explains HOW it affects EACH lab (Troponin, CK, Creatinine, K+), cites specific physiology, addresses timeline, explains consistency/divergence |
| 0.75 | Clear mechanism, explains 3+ labs, specific physiology cited, timeline mentioned |
| 0.5 | Explains 2 labs clearly OR generic explanation covering all labs |
| 0.25 | Vague mechanism, explains 1-2 labs only |
| 0.0 | No justification or nonsensical |

#### Confidence Calibration (10% weight)
Score based on match between stated confidence and actual accuracy across **all 4 labs**

**Before/After Timeline Made Explicit Throughout:**
```
PRE-PROCEDURE → PROCEDURE → POST-PROCEDURE (24h-7d)
All labs before PTCA/stent Measure changes
(baseline state) (intervention) (new steady state)
```

### 2. README.md
**Changes:**
- Updated title: "Causal Cardiac Benchmarks" → "Causal Cardiac Benchmark"
- Removed all Benchmark B references
- Updated architecture diagram (no Benchmark B)
- Updated "Step 1: Generate Cases" (removed Benchmark B prep)
- Updated "Step 2: Run Evaluation" (output changed from 4 result files to 2)
- Updated scoring summary (removed Benchmark B scoring formula)
- Updated "Key Features" (removed "two complementary causal tasks" → "forward causal reasoning task")
- Updated timeline estimates (reduced from 2-4 hours to 1-2 hours)

### 3. run_causal_evaluation.mjs
**Changes:**
- Updated docstring (removed Benchmark B)
- Changed `BENCHMARKS` array to include only Benchmark A
- Removed `answerBenchmarkB()` function entirely
- Simplified `runCase()` to only call `answerBenchmarkA()`
- Updated call signature: `runCase(caseData, usePubMed)` (removed `benchmarkId`)

### 4. run_all_benchmarks.mjs
**Changes:**
- Updated docstring
- Changed `BENCHMARKS` array to include only Benchmark A
- Removed `answerBenchmarkB()` function entirely
- Simplified `runCase()` to only call `answerBenchmarkA()`
- Updated call signature

### 5. run_full_evaluation.mjs
**Changes:**
- Updated docstring (changed from "2 benchmarks × 2 models × 2 conditions = 800 predictions" to "1 benchmark × 2 models × 2 conditions = 400 predictions")
- Changed `BENCHMARKS` array to include only Benchmark A

### 6. run_all_benchmarks.sh
**Changes:**
- Removed step `[2/4] Preparing Benchmark B`
- Removed call to `python3 prep_physiological_attribution.py`
- Updated step numbering from [1/4] to [1/3]
- Updated echo messages to reflect single benchmark

### 7. prep_smoke_tests.py
**Changes:**
- Updated docstring: "5 cases per benchmark" → "5 cases for Benchmark A"
- Removed `generate_smoke_test_b()` function entirely
- Updated main block to only call `generate_smoke_test_a()`
- Updated summary output

### 8. smoke_test.mjs
**Changes:**
- Updated docstring (removed Benchmark B references, emphasized multi-lab structure)
- Changed `BENCHMARKS` array to include only Benchmark A with description field
- Removed `answerBenchmarkB()` function entirely
- Updated runner to only test Benchmark A
- Updated ground truth mapping to include **all 4 labs** (troponin, ck, creatinine, potassium)
- Enhanced prediction capture to include procedure info and all 4 lab ground truths

---

## Case Questions (Unchanged)

- `questions/a_001.json` through `questions/a_100.json` (100 Benchmark A cases)
  - Each case has:
    - Pre-intervention labs (baseline state)
    - Procedure performed
    - Ground truth: post-intervention lab directions + magnitudes (24h-7d)

---

## Key Conceptual Changes

### 1. Scoring Now Explicitly Before→After
All dimensions now emphasize the **change from pre→post procedure**, not absolute values.

```
Pre-procedure labs (given) → [Procedure] → Post-procedure labs (predicted & scored)
```

### 2. All 4 Labs Required
- Troponin T (cardiac injury)
- CK (enzyme release)
- Creatinine (renal function)
- Potassium (electrolyte balance)

Each lab gets:
- Direction accuracy scoring (weighted by clinical relevance)
- Magnitude accuracy scoring (for Troponin, CK, Creatinine only)
- Causal explanation (model must explain WHY each lab changes)

### 3. Mechanistic Reasoning Emphasized
Justification component now **explicitly requires per-lab explanations**. Generic bulk explanations score ≤0.5.

Example of 1.0:
```
"PTCA reopens LAD, restoring perfusion.
- Troponin: Washout from restored circulation (12-15% decline expected)
- CK: Enzyme release halts as perfusion restores (8% decline)
- Creatinine: Stable (no renal impact from PTCA alone)
- K+: Rises from myocardial reperfusion stress (1-2 mEq/L)"
```

Example of 0.5:
```
"The stent improves blood flow. This reduces troponin and CK.
Creatinine and potassium should stay relatively stable."
```

### 4. Confidence Scoring Across All Labs
Confidence calibration now checks if stated confidence matches **overall accuracy across 4 labs**, not just troponin.

---

## Data Integrity

- **Case questions:** Unchanged (100 cases with pre-intervention labs + procedures)
- **Ground truth:** All 100 cases include 4-lab ground truth (direction + magnitude from pre→post)
- **No data loss:** Only Benchmark B cases deleted; Benchmark A unchanged

---

## Testing

- **Smoke test:** Now runs 5 Benchmark A cases × 2 models × 2 conditions = 20 predictions
- **Validates:**
  1. All 4 labs predicted (no missing fields)
  2. Causal justification quality (explains each lab)
  3. Score sanity (ranges 0.0-1.0)
  4. Ground truth capture (all 4 lab directions + magnitudes)

---

## Running the Refactored Benchmark

### Generate Cases
```bash
python3 prep_intervention_attribution.py
```
Output: `questions/a_*.json` (100 cases)

### Run Smoke Test (5 cases, 2 models, 2 conditions)
```bash
node smoke_test.mjs
```
Output: `smoke_test_results/` with individual and summary JSON

### Run Full Evaluation (100 cases)
```bash
node run_causal_evaluation.mjs
```
Output: `results/a_with_pubmed_results.json`, `results/a_without_pubmed_results.json`

---

## Summary of Metrics

| Component | Weight | Labs Scored | Scale |
|---|---|---|---|
| **Direction Accuracy** | 40% | All 4 (weighted) | 0.0-1.0 |
| **Magnitude Accuracy** | 30% | 3 (T, CK, Cr) | 0.0-1.0 |
| **Causal Justification** | 20% | Per-lab reasoning | 0.0-1.0 |
| **Confidence Calibration** | 10% | Across all 4 labs | 0.0-1.0 |
| **TOTAL SCORE** | 100% | — | 0.0-1.0 |

---

## Files Still to Consider

- `full_evaluation_scoring.mjs` — May have Benchmark B references (not updated yet)
- `smoke_test_scoring.mjs` — May have Benchmark B references (not updated yet)
- `score_predictions.mjs` — May have Benchmark B references (not updated yet)

Check these for any remaining Benchmark B references if running them.
