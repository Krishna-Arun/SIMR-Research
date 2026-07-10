# Benchmark Methodology Audit

## Executive Summary

**Status**: ⚠️ **CRITICAL ISSUES FOUND**

The benchmark claims to use real MIMIC-IV data with 48-hour prediction windows, but the actual data reveals significant quality and methodological issues:

1. **Empty Post-Intervention Data**: `post_trajectory` fields are completely empty (0 measurements)
2. **Sparse Pre-Context**: Only 1 measurement per marker pre-intervention (not 48-hour dense labs)
3. **Window Mismatch**: 48-hour windows don't align with sparse MIMIC measurement frequency
4. **Data Leakage**: Requires verification in prompts
5. **Matching Criteria**: Needs clarification on similarity thresholds

---

## Detailed Findings

### 1. Data Availability & Time Windows

**What we claim:**
```
Pre-intervention: 48 hours of lab data before intervention
Post-intervention: 48 hours of lab data to predict
```

**What MIMIC-IV actually has:**

| Metric | Finding |
|--------|---------|
| **Troponin T measurements** | 10,056 total across 3,751 admissions |
| **Measurements per admission** | Median = 2.0 (min=1, max=23) |
| **Time gaps between measurements** | 8-20+ hours (sparse, not dense) |
| **Admissions with 3+ measurements in 48h** | ~1,477 (~40% of admissions) |
| **Current extraction** | Finding ZERO post-intervention measurements |

**Example admission with Troponin T:**
```
2128-10-21 06:55:00: 1.09
2128-10-21 15:00:00: 2.08  (8 hours later)
2128-10-22 11:00:00: 1.74  (20 hours later)

Total: 3 measurements over ~30 hours
If intervention at 2128-10-21 12:00:00:
  - Pre-window (48h before): 1 measurement
  - Post-window (48h after): 1-2 measurements
→ Can't reliably predict 48-hour trajectory from 1-2 sparse points
```

**⚠️ Issue**: Current extraction returns ZERO post-measurements (empty post_trajectory)

---

### 2. Pre-Context Data Quality

**Current state**:
```python
"pre_context": {
    "markers": {
        "Troponin T": [0.045],  # ← ONLY 1 VALUE
        "CK-MB": [6.0]          # ← ONLY 1 VALUE
    }
}
```

**Problem**: 
- Can't establish "trend" with 1 data point
- Can't assess change direction (rising/falling)
- Models get minimal clinical context
- Looks like mock data, not real dense labs

**What we SHOULD have**:
```python
"pre_context": {
    "markers": {
        "Troponin T": [0.040, 0.042, 0.045, 0.043, 0.041],  # ← Multiple values
        "CK-MB": [2.5, 2.7, 2.85, 2.8, 2.75],               # ← Shows trend
    }
    "timeline_hours": 48  # Dense measurements within window
}
```

---

### 3. Post-Trajectory (Prediction Target) 

**Current state**:
```python
"post_trajectory": {}  # ← COMPLETELY EMPTY!
```

**Impact**: 
- Nothing to evaluate against
- Models generate made-up trajectories
- Explains why all models returned identical linear predictions
- **Benchmark is fundamentally broken**

**Required fix**:
```python
"post_trajectory": {
    "markers": {
        "Troponin T": [0.050, 0.065, 0.090, 0.110, 0.095, 0.060, 0.045, ...]
    }
}
```

---

### 4. Data Leakage Analysis

**Questions to verify**:

1. **Do prompts reveal intervention results?**
   ```
   ✓ PASS: Prompts only show pre-intervention data
   ✓ PASS: Prompts ask for post-prediction (ground truth hidden)
   ✗ NEED TO CHECK: Do metadata/demographics leak intervention info?
   ```

2. **Do prompts reveal similar cases?**
   ```
   ✓ PASS: No matched pair info given
   ✗ NEED TO CHECK: Could models infer from patient IDs?
   ```

3. **Do matched pairs have stable causal relationships?**
   ```
   ✓ PASS: Pairs are specific interventions vs observation
   ✗ NEED TO CHECK: How similar are baseline characteristics?
   ```

**Required verification:**
- [ ] Audit first 10 prompts for leakage
- [ ] Check patient ID encoding (should be anonymized)
- [ ] Verify demographic similarity in matched pairs

---

### 5. Matched Pair Quality

**Current matching criteria** (from `construct_matched_pairs.py`):

```python
"matching_criteria": {
    "severity_bin": ...,
    "pre_trend_direction": ...,
    "pre_trend_magnitude": ...
}
```

**Questions**:

1. **How close are matched patients?**
   - Severity: What bins? (e.g., low/medium/high?)
   - Pre-trend: Are slopes within tolerance?
   - Missing: Age, comorbidities, baseline health

2. **Are interventions truly different?**
   - PCI vs observation: Yes, different
   - PCI vs medication: Moderate difference
   - Do confounders explain outcomes vs intervention?

3. **Sample sizes**:
   - 50 episodes total
   - 30 matched pairs
   - But only 1477 admissions have 3+ troponin measurements
   - Selection bias toward specific patient subsets?

---

## Recommendations for Frontier Model Evaluation

### Phase 1: Fix the Benchmark (Week 1)

**Priority 1 - Resolve Empty Data**:
```
1. Extend time windows (e.g., ±72 hours or ±7 days)
2. Accept sparse measurements + interpolate
3. OR use synthetic realistic data for now
```

**Priority 2 - Improve Pre-Context**:
```
1. Require minimum 3+ measurements pre-intervention
2. Show measurement timeline (timestamps)
3. Compute trend direction from multiple points
```

**Priority 3 - Data Leakage Audit**:
```
1. Anonymize patient IDs
2. Remove episode ordering info
3. Verify no demographic leakage
```

### Phase 2: Frontier Model Evaluation (Week 2-3)

**GPU Requirements**:
```
Model             | Params | Batch | GPU Memory | Recommended GPU
─────────────────────────────────────────────────────────────
Llama 3.1-8B      | 8B     | 2     | 16GB       | 1x L40S or H100
Llama 3.1-70B     | 70B    | 1     | 80GB       | 1x H100 or 2x A100
Claude (API)      | N/A    | -     | N/A        | API (no GPU needed)
GPT-4             | N/A    | -     | N/A        | API (no GPU needed)
Qwen2-72B         | 72B    | 1     | 80GB       | 1x H100
```

**Recommended Setup**:
```
✓ Use H100 (80GB) for largest models
✓ Use L40S (48GB) for smaller models
✓ Use API for proprietary models (GPT-4, Claude)
```

**3 Models to Test**:
1. **Meta Llama 3.1-70B** (SOTA open-source, 70B parameters)
2. **Qwen2-72B** (Competitive with Llama, good medical reasoning)
3. **GPT-4o (via API)** (Frontier proprietary baseline)

---

## Execution Plan for Valid Benchmark

### Step 1: Data Quality Fix (CRITICAL)

```bash
# Fix 1: Extend time windows to ±72 hours
python3 scripts/extract_episodes_from_physionet.py \
  --pre_window_hours=72 \
  --post_window_hours=72

# Fix 2: Require minimum measurement density
# Only accept episodes with 3+ pre AND 2+ post measurements

# Fix 3: Add interpolation
# For sparse measurements, use linear interpolation between points
```

### Step 2: Data Leakage Audit

```python
# Audit script checklist
[ ] Remove patient IDs from prompts
[ ] Anonymize all demographics  
[ ] Verify no matched pair hints
[ ] Confirm ground truth not in prompt
[ ] Check randomization of episode order
```

### Step 3: Run Frontier Models

```bash
# Model 1: Llama 3.1-70B (H100 required)
python3 scripts/run_frontier_benchmark.py \
  --model "meta-llama/Llama-3.1-70b-instruct" \
  --gpu_type "h100" \
  --batch_size 1

# Model 2: Qwen2-72B  
python3 scripts/run_frontier_benchmark.py \
  --model "Qwen/Qwen2-72B-Instruct" \
  --gpu_type "h100" \
  --batch_size 1

# Model 3: GPT-4o (via API)
python3 scripts/run_frontier_benchmark.py \
  --model "gpt-4o" \
  --api_key $OPENAI_API_KEY \
  --batch_size 5
```

### Step 4: Rigorous Evaluation

```
MCCS: Does model understand intervention causality?
  - 0.5 = random guessing
  - 0.7+ = good understanding
  
TCAE: Is timing prediction accurate?
  - <2h = excellent
  - 2-6h = good
  - >12h = poor
  
IEC: Are magnitude predictions calibrated?
  - <0.05 = well-calibrated
  - 0.05-0.2 = reasonable
  - >0.5 = poor
```

---

## Critical Issues Blocking Frontier Model Testing

| Issue | Severity | Fix Time | Blocks |
|-------|----------|----------|--------|
| Empty post_trajectory | 🔴 Critical | 1-2 days | All evaluation |
| Sparse pre_context | 🔴 Critical | 1 day | Clinical realism |
| Data leakage check | 🟠 High | 1 day | Validity |
| GPU resource booking | 🟠 High | 2-3 days | H100 testing |
| Matched pair verification | 🟡 Medium | 1-2 days | Methodology |

---

## Next Steps

1. **This week**: Fix data extraction (extend windows, require density)
2. **Next week**: Run data leakage audit + frontier models on H100
3. **Week 3**: Compile results with proper statistical analysis

**DO NOT proceed with frontier models until**:
- ✅ post_trajectory is populated with real data
- ✅ pre_context has 3+ measurements
- ✅ Data leakage audit passes
- ✅ H100 GPU is available

---

## Questions for User Clarification

1. **Time windows**: Should we extend to 72 hours given MIMIC's measurement frequency?
2. **Matching**: What thresholds for "similar patient" (age ±5yr? severity ±1 bin?)
3. **Sparse data**: Acceptable to interpolate between sparse measurements?
4. **Frontier models priority**: GPT-4 > Llama 70B > Qwen 72B?
5. **Timeline**: Can we get H100 access this week?
