# Causal Intervention Benchmark - Results

**Timestamp:** 2026-06-25T12:12:28.296890
**Episodes Evaluated:** 630
**Matched Pairs:** 724
**Models Tested:** 2

## Model Comparison

| Model | Backend | Prompt | MCCS | TCAE (h) | IEC | Status |
|-------|---------|--------|------|----------|-----|--------|
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | huggingface | cot | 0.4480 | 31.00 | 0.6782 | ✗ Poor |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | huggingface | zero_shot | 0.4419 | 23.00 | 0.6581 | ✗ Poor |

## Per-Contrast / Per-Marker Breakdown

(troponin/CK-MB = injury signal; sodium = negative control)

| Model | Prompt | Contrast | Marker | Role | n | MCCS | non-stable% (A) | NC-discrim |
|-------|--------|----------|--------|------|---|------|-----------------|-----------|
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | pci_vs_control | Troponin T | positive | 654 | 0.448 | 88% | 0.5377 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | pci_vs_control | Creatine Kinase, MB Isoenzyme | positive | 304 | 0.444 | 88% | 0.5377 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | pci_vs_control | Sodium | negative_control | 322 | 0.469 | 34% | 0.5377 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | multivessel_vs_singlevessel_pci | Troponin T | positive | 70 | 0.514 | 86% | 0.5714 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | multivessel_vs_singlevessel_pci | Creatine Kinase, MB Isoenzyme | positive | 22 | 0.591 | 86% | 0.5714 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | multivessel_vs_singlevessel_pci | Sodium | negative_control | 46 | 0.364 | 29% | 0.5714 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | pci_vs_control | Troponin T | positive | 654 | 0.442 | 86% | 0.4544 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | pci_vs_control | Creatine Kinase, MB Isoenzyme | positive | 304 | 0.383 | 81% | 0.4544 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | pci_vs_control | Sodium | negative_control | 322 | 0.440 | 38% | 0.4544 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | multivessel_vs_singlevessel_pci | Troponin T | positive | 70 | 0.529 | 89% | 0.6571 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | multivessel_vs_singlevessel_pci | Creatine Kinase, MB Isoenzyme | positive | 22 | 0.588 | 93% | 0.6571 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | multivessel_vs_singlevessel_pci | Sodium | negative_control | 46 | 0.462 | 25% | 0.6571 |

**Direction calibration (ECE, troponin):** deepseek-ai/DeepSeek-R1-Distill-Qwen-7B=0.2721

## Intervention-flip sensitivity (causal probe)

Same patient, intervention swapped in the prompt → how much does the troponin prediction change? Higher = the model genuinely conditions on the intervention (causal); ~0 = ignores it.

| Model | Prompt | direction-flip rate | mean rel. change | n |
|-------|--------|--------------------|------------------|---|
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | cot | 0.6028 | 0.5954 | 501 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | zero_shot | 0.6076 | 0.5568 | 502 |

**NC-discrim** = (mean non-stable rate on positive markers) − (non-stable rate on the sodium negative control). Higher is better: a discriminating model predicts an effect on injury markers but NOT on the inert control. Near 0 = the model spuriously 'moves everything' after PCI.

**ECE** = expected calibration error of the troponin-direction prediction vs the model's own logit-derived confidence (lower = better calibrated; open-source models only).

## Metric Definitions

- **MCCS:** Matched Counterfactual Consistency Score (% pairs correct)
  - 0.50 = Random guessing
  - 0.65 = Good causal understanding
  - 0.75+ = Excellent understanding

- **TCAE:** Temporal Causal Alignment Error (hours off)
  - <2 hours = Perfect
  - 2-6 hours = Good
  - >12 hours = Poor

- **IEC:** Intervention Effect Calibration (scale-free relative error, 0-1; lower better)
  - <0.10 = Well-calibrated magnitude
  - 0.10-0.30 = Acceptable
  - >0.30 = Poorly calibrated
