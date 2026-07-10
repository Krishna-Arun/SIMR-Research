# Task C (multi-arm) — PCI vs CABG vs medical

**Generated:** 2026-06-25T16:42:07.043594
**Primary:** readmission_30d   **Secondary:** AKI   **Answer-key:** pending (proxy-free only)

## Outcome: readmit30

| Method | n | factual AUC | calib ECE | interv. spread | best-arm mix | justif. (0/.5/1) | sign vs key | best-arm acc |
|---|---|---|---|---|---|---|---|---|
| mock [zero_shot] | 400 | 0.5 | 0.0475 | 0.0 | 1.00/0.00/0.00 | 0.482 (0.035/0.965/0.0) | — | — |

## Outcome: aki

| Method | n | factual AUC | calib ECE | interv. spread | best-arm mix | justif. (0/.5/1) | sign vs key | best-arm acc |
|---|---|---|---|---|---|---|---|---|
| mock [zero_shot] | 356 | 0.4852 | 0.1343 | 0.1125 | 0.00/0.00/1.00 | 0.5 (0.0/1.0/0.0) | — | — |

## Notes

- **factual AUC/Brier/ECE**: predicted risk under the arm the patient actually got, vs the observed outcome — fully real, no counterfactual assumptions.
- **interv. spread**: mean (max−min) of predicted risk across the 3 arms; ~0 means the model ignores the treatment.  **best-arm mix**: pci/cabg/medical share of recommendations.
- **sign/PEHE/best-arm acc** vs the causal-forest answer-key (blank until it's built); these are *agreement-with-estimator*, scored only on each contrast's common-support patients.
- **justif. (0/.5/1)** = worded-justification rubric: mean score + fraction at each level (0 nonsense / 0.5 general / 1 patient-specific + causally verified). Grounding & causal-direction are automatic; coherence via judge. **Ceiling is 0.5 until the answer-key lands** (can't confirm 'causally verified' without a reference direction).
- Mortality is reported separately as a population ATE-vs-RCT check (too rare for per-patient).