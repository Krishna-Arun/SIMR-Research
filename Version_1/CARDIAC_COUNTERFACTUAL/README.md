# Cardiac Counterfactual Benchmark (PCI vs CABG vs medical)

Measures whether an LLM can reason **counterfactually** about the revascularization decision in
acute coronary syndrome: from a patient's pre-treatment chart, predict the outcome under each of
three treatments (PCI / CABG / medical management), pick the best one, and **justify** it — graded
against real outcomes, a causal-forest answer-key, and published trial effects.

## Treatment arms & time-zero
- **PCI / CABG / medical** (the revascularization decision; real clinical equipoise).
- **Time-zero = the treatment-decision point**: procedure time for treated arms; a *matched
  decision window* (treated arms' median time-to-procedure) for medical. Input = everything
  BEFORE time-zero; nothing after.

## Outcomes
- **Primary:** 30-day readmission.   **Secondary:** AKI (KDIGO, from creatinine).
- **Mortality:** population-level RCT-anchor only (too rare per-patient).

## Pipeline (run in order)
1. `scripts/assign_index.py`        → `data/index.json`     (arm + time-zero)
2. `scripts/build_context.py`       → `data/context.json`   (pre-index chart: notes + full
   timestamped labs + comorbidities + AKI)
3. `scripts/build_multiarm_cohort.py` → `data/multiarm_cohort.json` (durable outcomes + landmark)
4. `scripts/overlap_diagnostic.py`  → `data/overlap_diagnostic.json` (pairwise common support)
5. `scripts/run_taskC_multiarm.py`  → `answers/` (LLM predicts each arm: value+direction+confidence+justification)
6. `scripts/score_taskC_multiarm.py`→ `outputs/TASKC_MULTIARM_RESULTS.md` (the scorecard)

`scripts/build_answerkey.py` (TODO, needs `econml` + age/sex) → `data/answerkey_multiarm.json`
(causal-forest per-patient effects; unlocks pairwise PEHE, best-arm accuracy, and the
justification rubric's 1.0 ceiling).

## Run
```bash
sbatch jobs/run_pipeline.sbatch      # data pipeline (CPU)
CAUSAL_BACKEND=mock python3 scripts/run_taskC_multiarm.py   # GPU-free smoke
sbatch jobs/run_gpu.sbatch           # real LLMs (public gpu partition) + scoring
```

## Scoring
- **Proxy-free (real):** factual AUC / calibration, intervention-spread, best-arm mix.
- **Justification rubric (0/0.5/1):** 0 nonsense, 0.5 general, 1 patient-specific + causally
  verified (grounding + causal-direction automatic; coherence via judge).
- **Vs answer-key:** pairwise effect sign/PEHE, best-arm accuracy.
- **Vs reality:** average effect vs PCI trials; ~0 on a negative-control lab.

## Layout
`scripts/` pipeline · `metrics/` (multiarm_metrics, justification_rubric) · `models/`
(llm_inference) · `jobs/` (sbatch) · `data/` `outputs/` `answers/` `logs/`.
`scripts/cardiac_defs.py` holds shared definitions (arm codes, comorbidities, extractors) so the
folder is self-contained. Raw data: MIMIC-IV cardiac-ext subset + full MIMIC-IV core tables.
