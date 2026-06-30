# Causal Intervention Benchmark Results

**Timestamp:** 2026-06-23T23:06:10.375909
**Pairs:** 30
**Episodes:** 40

## Metric Summary

| Model | Backend | Prompt | MCCS | TCAE (h) | IEC | Invariance | Status |
|-------|---------|--------|------|----------|-----|-----------|--------|
| mock_qwen | mock | zero_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_qwen | mock | cot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_qwen | mock | few_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_deepseek | mock | zero_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_deepseek | mock | cot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_deepseek | mock | few_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_llama | mock | zero_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_llama | mock | cot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_llama | mock | few_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_mistral | mock | zero_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_mistral | mock | cot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |
| mock_mistral | mock | few_shot | 0.4333 | 28.00 | 1.2039 | ✗ | ✗ Poor |

## Metric Definitions

- **MCCS** (Matched Counterfactual Consistency Score): Proportion of matched pairs where predicted outcome ordering is correct. Higher is better. Baseline: 0.5 (random).
- **TCAE** (Temporal Causal Alignment Error): Median error in inflection point timing (hours). Lower is better.
- **IEC** (Intervention Effect Calibration): Wasserstein distance between predicted and actual outcome distributions. Lower is better.
- **Invariance** (✓/✗): Pre-trend invariance test passed? Drop of 10+ MCCS points when interventions shuffled.

## Key Findings

TODO: Add interpretation
