# Task C — Counterfactual Treatment-Effect Benchmark (PCI / ACS)

**Generated:** 2026-06-25T14:21:07.973478
**Primary outcome (auto-selected):** `delta_creatinine_72h`  ·  **secondary:** `peak_troponin_72h`
**Matched episodes:** 625  ·  **Propensity AUC:** 0.8027  ·  **Embedding:** pca_whiten_8  ·  **Caliper:** 0.3082

## Covariate balance / overlap

- mean|SMD| pre-match → post-match: **0.2074 → 0.0827** (post max 0.2372; target <0.1)
- propensity overlap: PCI [0.0211, 0.9921] vs control [0.0001, 0.9211]; matched: PCI 0.991, control 0.826

## Proxy trust — matched-estimator factual validation

How well the k-NN matcher reproduces *observed* outcomes from same-arm neighbors (a held-out factual check). Larger error ⇒ trust the proxy counterfactual less.
- factual RMSE = **0.6492** (nRMSE 1.0049, n=608)

## Headline — causal performance

Treatment-effect **sign agreement** = does sign(predicted ITE) match sign(proxy ITE) (the core 'who benefits' quantity; vs the matched proxy). **Flip** = when the treatment is swapped, how often does the predicted direction change / by how much (proxy-free — high ⇒ the model genuinely conditions on the intervention).

| Method | n | effect-sign agree | flip dir-rate | flip rel-Δ |
|---|---|---|---|---|
| baseline_matched_nn (proxy ceiling) | 541 | **1.0** | — | — |
| baseline_T_learner | 625 | **0.4436** | — | — |
| baseline_S_learner | 625 | **0.2551** | — | — |
| mock [zero_shot] | 625 | **0.4769** | 1.0 | 1.0 |

## Reliability — proxy-free (fully real)

| Method | factual RMSE | log10 RMSE | factual dir-acc | conf ECE |
|---|---|---|---|---|
| baseline_matched_nn (proxy ceiling) | 0.6571 | — | — | — |
| baseline_T_learner | 0.6267 | — | — | — |
| baseline_S_learner | 0.6365 | — | — | — |
| mock [zero_shot] | 0.6598 | — | 0.4732 | 0.2268 |

## Magnitude — vs k-NN proxy (AGREEMENT-WITH-MATCHER, not true PEHE)

| Method | proxy-PEHE | CF dir-acc | policy value | Δ vs observed | %treat |
|---|---|---|---|---|---|
| baseline_matched_nn (proxy ceiling) | 0.0 | — | -0.0537 | 0.2529 | 0.479 |
| baseline_T_learner | 0.9095 | — | 0.2119 | -0.0098 | 0.489 |
| baseline_S_learner | 0.7204 | — | 0.1715 | 0.0307 | 0.099 |
| mock [zero_shot] | 0.7476 | 0.4955 | 0.1736 | 0.0285 | 0.0 |

## Caveats (read before interpreting)

1. **proxy-PEHE is agreement-with-a-matcher, not true-effect error.** Real data has no observed Y(1)−Y(0); the proxy is itself a k-NN matching estimator, so the `baseline_matched_nn` row scores ~0 *by construction* (it IS the label) and is a ceiling, not a competitor. The T-/S-learner rows are independent of the label.
2. **Policy value is a surrogate-target metric, not clinical benefit.** PCI mechanically raises troponin and can raise creatinine, and mortality is unavailable in this data subset, so 'improving' the lab does not equal helping the patient.
3. **Ignorability is conditional on available covariates.** Age and sex (classic PCI confounders) are absent from this dataset; the sodium negative control and post-match SMD are the residual-confounding diagnostics. A full-MIMIC-IV track (mortality + demographics + RCT anchor) is the planned follow-on that resolves this.
