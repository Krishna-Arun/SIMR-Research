# Summer's Goal

This document states the research goal for **Version 4** of the SIMR
clinical-reasoning benchmark and the three questions it must answer:

1. **What is medical reasoning?** — a precise, operational definition.
2. **How do we identify it?** — the four chained benchmarks (a → b → c → d)
   that force a model to *exhibit* reasoning rather than pattern-match.
3. **How do we improve it?** — a novel action-conditioned world-model
   fine-tuning technique intended to beat Gemma / Qwen / DeepSeek-class
   open models on these tasks.

All benchmarks run on **real MIMIC-IV v3.1** data restricted to a cardiac-ICU
cohort. Supporting code lives in [Longitudinal/](../Longitudinal/),
[Benchmark_a/](../Benchmark_a/), and [CounterfactualSim/](../CounterfactualSim/).

---

## 1. Defining reasoning in a medical context

> **Medical reasoning is the construction of an interpretable causal tree:
> from a clinical query, descending through causal links to concrete, known
> physiological principles and patient-specific quantitative evidence, such
> that the links also verify *upward* — each step is inspectable, and the
> chain reconstructs the answer.**

Expanding this definition into the properties we actually test:

- **Directed and causal.** A reasoning step is not an association ("patients
  with high creatinine often need dialysis") but a mechanism ("this patient's
  creatinine rose from X to Y over 48h with falling urine output, indicating
  intrinsic AKI that fluid management could not correct, therefore renal
  replacement"). Correlational shortcuts score as textbook, not reasoning.

- **Grounded downward.** Every leaf of the tree must terminate either in a
  *known physiological principle* (something a clinician would accept without
  citation) or in *this patient's quantitative evidence* (a specific lab
  value, date, or trajectory retrieved from the record). A chain that never
  touches the patient's numbers is generic.

- **Verifiable upward.** Given the leaves, the intermediate links must
  reconstruct the answer. This is what makes the tree *inspectable*: a grader
  (human or agent) can walk from evidence back up to the conclusion and check
  that each edge holds. Reasoning that cannot be reconstructed is not
  distinguishable from a lucky guess.

- **Patient-specific.** The same disease in two patients produces two
  different trees. A response that would be identical across all patients with
  the same diagnosis is, by construction, not reasoning about *this* patient.

The scoring rubric operationalizes exactly this definition (see §2 and
[PAPER_CRITERIA.md](PAPER_CRITERIA.md)): a justification earns **1.0** only
when it cites patient-specific causal links, **0.5** for generic-but-correct
textbook physiology, and **0** when irrelevant or inaccurate.

---

## 2. The benchmarks that identify medical reasoning

Version 4 evaluates **one patient at a time**, asking four questions in
**time order** so that later tasks depend on facts established earlier. Each
task isolates a different reasoning mode; together they cover retrieval-driven
diagnosis, forward physiological prediction, counterfactual attribution, and
calibrated prognosis.

### Cohort under test

- **494** cardiac-ICU stays cross-referenced from
  `mimic-iv-ext-cardiac-disease` (49 dialysis / 88 transfusion /
  357 ventilation), **471** CLMBR-encoded.
- Patient-level split: **train 328 / val 46 / test 97** (no subject appears in
  two splits).
- **Inclusion filters:** alive at t0; ICU-only; ≥20 distinct lab itemids **and**
  ≥50 measurements per admission; ≥2 labs pre-anchor **and** ≥2 within 72h
  post-anchor.
- **Anchor** = earliest lab-driven ICU intervention: dialysis / ventilation
  from `procedureevents`, transfusion from `inputevents` RBC itemids.
- **Outcome labels:** 1-year mortality **19.8%** positive; 30-day readmission
  **18.6%** positive (repaired — previously 0% because admissions were sliced
  by index `hadm_id`; re-derived from the full MIMIC-IV admissions table per
  `subject_id`, see [outcomes_fix.py](../Longitudinal/outcomes_fix.py)).
- A **balanced 100-case chained set** (50/50 mortality; arm-diverse
  34/34/32 across dialysis/transfusion/ventilation) is selected for evaluation
  ([balanced_cases.json](../Longitudinal/cohort_data/balanced_cases.json)).

### Benchmark a — Request + Answer (agentic diagnosis)

| | |
|---|---|
| **Mode** | Agentic, tool-using, open-ended |
| **Input** | Minimal patient stub; tools to *request* more data |
| **Output** | Open diagnosis / next-intervention answer + a patient-specific causal chain citing retrieved values |
| **Scoring** | Evaluator agent, 0 / 0.5 / 1 on request quality and answer chain |

The model is given a gate tool **`Access_All_supplementals_no_values`** that
returns lab and microbiology **names + dates only, with no values**. To obtain
values it must call **`Request_a_supplemental`** / **`Request_values`** and
*justify* each request; **PubMed** is available for guideline grounding. It
then answers an **open-ended** question ("what is the driving diagnosis / what
is the next appropriate intervention?") and must support it with a
**≥2-step patient-specific causal chain** citing the values it retrieved.

**Why it is hard:** the answer is open-ended (no multiple choice to
back-solve); the "golden lab" that would give the answer away is **withheld**
from the initial view; lab signatures **overlap across intervention families**
(a transfusion candidate and a dialysis candidate can look similar at
baseline); and full credit requires the chain, not just the label.
Infrastructure lives in [Benchmark_a/](../Benchmark_a/)
([tools.py](../Benchmark_a/tools.py), [agentic_loop.py](../Benchmark_a/agentic_loop.py),
[mcp_client.py](../Benchmark_a/mcp_client.py)).

### Benchmark b — 72h Lab Trajectory (forward prediction)

| | |
|---|---|
| **Input** | Pre-anchor labs + the intervention that was performed |
| **Output** | For each core lab: direction **Rising / Falling / Stable** + causal justification + a confidence distribution |
| **Scoring** | Deterministic ground truth (reference-band rule) + agent-graded justification |

Given the patient's pre-anchor state and the known intervention, the model
predicts how each core lab moves over the next 72h and *why*. Ground truth is
**data-derived** from the actual post-anchor panel via a reference-band rule.

**Hardening vs. Version 3:** lenient "Stable-hedge" partial credit is
**removed** (hedging toward Stable no longer earns points), and the headline
metric is the **joint all-labs-correct rate** rather than per-lab average,
which is far less forgiving of guessing.

### Benchmark c — Intervention Attribution (counterfactual)

| | |
|---|---|
| **Input** | Two real patients with **similar baselines** but **different interventions**, plus one observed 72h post-panel |
| **Output** | Which patient the panel belongs to **and** a causal-physiology justification |
| **Scoring** | Deterministic patient-ID correctness + agent-graded mechanism |

This is a counterfactual discrimination task: the same starting point, two
different treatment worlds, one observed outcome — which world produced it?

**Hardening vs. Version 3:** pairs are chosen to be **maximally ambiguous** so
that label-only guessing sits near chance (binary ≈ 0.5), and **full credit
requires the correct causal mechanism**, not just the right patient.

### Benchmark d — 1-Year Mortality Outcome (calibrated prognosis)

| | |
|---|---|
| **Input** | The patient's longitudinal trajectory |
| **Output** | Mortality prediction + calibrated confidence + causal risk rationale |
| **Scoring** | Correctness + calibration (Brier / ECE vs. token-logit probability) + agent-judged rationale |

**Class-balanced** so that "always No" is *not* a free 0.80 baseline
(recall the base rate is 19.8% positive). The model must produce a probability
whose **calibration** is measured, not just a label.

### Scoring architecture (all four)

- **Objective components** — b directions, c patient-ID, d label — use
  **deterministic, data-derived ground truth**.
- **Subjective components** — causal justifications, request quality, open
  answers — are graded by an **evaluator agent (GPT-OSS-20B)** on a
  **0 / 0.5 / 1** rubric:
  - **0** = irrelevant or inaccurate;
  - **0.5** = generic textbook physiology, not patient-specific;
  - **1** = patient-specific causal links citing *this* patient's values.
- **Reliability:** ≥3 judge runs plus a **second judge model**, reported via
  **Cronbach's α** and **inter-rater κ**, validated against a **~20-item
  human-rated subset**. Scoring entry points:
  [score_longitudinal.py](../Longitudinal/score_longitudinal.py) and
  [evaluator_agent.py](../Benchmark_a/evaluator_agent.py).

---

## 3. The novel fine-tuning technique (to beat Gemma / Qwen / DeepSeek)

The hypothesis: reasoning about *what an intervention will do* improves when a
model can **simulate** the intervention against a learned causal model of the
patient, then reason over the simulated result. Version 4 introduces an
**action-conditioned JEPA counterfactual world model** exposed to the LLM as a
`simulate()` tool, and fine-tunes the LLM with **GRPO** using the chain rubric
as reward.

### World-model architecture (V4 rebuild)

> The V3 engine (`ac_jepa.py` + dead `world_model.py`) was rebuilt. It was not a
> JEPA (per-transition MLP, trained 1-step / served 3-step), and its headline
> "+35.8% over persistence" was a one-step residual metric against the weakest
> possible baseline. The rebuild and its rationale are in
> [V4_UPGRADE_PLAN.md](V4_UPGRADE_PLAN.md). **Thesis:** foundation-model latents
> encode *which treatment a patient gets*, so a naive rollout is confounded; we
> diagnose, correct, and — the part the 2026 EHR-world-model literature (EHRWorld,
> ICOM, MedDreamer, Clin-JEPA) skips — **validate** the counterfactuals.

```
CLMBR latent encoder ─► z_t (frozen 768-d, per timestep)
        │
        ▼
latent_wm.py  1-D action-conditioned predictor (faithful V-JEPA 2-AC port:
        │     block-causal attention over [action, Δt, state] tokens; residual Δz;
        │     TEACHER-FORCING + AUTOREGRESSIVE-ROLLOUT loss — trained on its own
        │     rollouts so multi-step serving does not drift)
        ▼
causal.py     deconfounding layer:
   ├─ leakage diagnostic  (is the arm predictable from z? → confounding present)
   ├─ balance adapter Φ + GRL adversary  (push arm-predictability toward chance)
   ├─ propensity π(arm|z) + stabilized IPW   (on RAW z, not Φ)
   ├─ doubly-robust (AIPW) contrast          (consistent if outcome OR π is right)
   └─ positivity gate     (refuse / widen bands off-support — never extrapolate)
        │
        ▼
validate.py   ground-truth counterfactual validation (semi-synthetic PEHE + IPW ATE)
```

Code: [latent_wm.py](../CounterfactualSim/latent_wm.py),
[train_wm.py](../CounterfactualSim/train_wm.py),
[causal.py](../CounterfactualSim/causal.py),
[validate.py](../CounterfactualSim/validate.py).

### Results (V4 engine, CPU, real 471-patient cohort + semi-synthetic)

| Metric | Value | Note |
|---|---|---|
| Multi-step AR rollout MSE (val) | **1.119** | vs. persistence 1.560 (**+28.3%**) **and** mean-Δ 1.542 — honest multi-step, beats *both* baselines |
| **Leakage: arm-predictability from raw CLMBR z** | **macro-AUC 0.921** | chance 0.5 → strong confounding-by-indication *is present in the latents* (the motivating result) |
| Leakage after balancing Φ | macro-AUC 0.724 | balancing removes ~0.20 AUC; residual reflects the over-balancing trade-off |
| Positivity (real cohort) | **463/471 off-support** for ≥1 arm | overlap is badly violated at n=471 → cross-arm CF largely unidentifiable here; gate is essential |
| Validation: IPW de-biases ATE | naive bias 1.02 → **0.08 (−92%)** | semi-synthetic, known ground truth, moderate confounding |
| Validation: overlap-stratified PEHE | off-support **2.1×** worse than on-support | gate flags exactly where CF is unreliable |

### Exposure + RL fine-tuning

The trained world model is served to the LLM as an MCP **`simulate()`** tool
([simulate_server.py](../CounterfactualSim/simulate_server.py)); the RL
environment lives in [CounterfactualSim/rl_env/](../CounterfactualSim/rl_env/).
The LLM is then **GRPO** reinforcement-fine-tuned with the **chain rubric as
the reward signal**, so the model is optimized directly for the property we
defined as reasoning in §1.

### Ablation arms

| Arm | Description |
|---|---|
| **vanilla** | Base LLM, no simulator |
| **+sim(base)** | Base LLM with access to `simulate()` |
| **+sim(GRPO)** | GRPO-fine-tuned LLM with `simulate()` |

**Motivation from Version 3:** on the pre-hardening v3 set, `+sim` gave **no
lift (0.677 → 0.680)** because the benchmark was too easy for the simulator to
matter. That null result is *why* Version 4 hardens every task — the aim is a
benchmark on which the world model can actually demonstrate value.

---

## Question-generation methodology

Questions are produced with the **Evaluator-Optimizer** pattern from
Anthropic's [*Building Effective Agents*](https://www.anthropic.com/engineering/building-effective-agents):

- **Optimizer = Mistral Small 3.1** drafts each patient-specific question.
- **Evaluator = GPT-OSS-20B** critiques and returns revisions until the
  question meets criteria (patient-specificity, single defensible ground
  truth, appropriate difficulty).
- **Both agents have PubMed MCP access** for clinical-guideline grounding, so
  generated questions and their rubrics are anchored to real guidelines rather
  than model priors.

Generation and orchestration code:
[Benchmark_a/optimizer_agent.py](../Benchmark_a/optimizer_agent.py),
[Benchmark_a/evaluator_agent.py](../Benchmark_a/evaluator_agent.py),
[Longitudinal/orchestrator.py](../Longitudinal/orchestrator.py).

---

## Baselines to beat (Version 3, pre-hardening)

Per-step mean scores on the longitudinal set:

| Model | Total | A1 | C | B | A2 |
|---|---|---|---|---|---|
| gemma-4-e4b | **0.675** | 0.98 | 0.51 | 0.74 | 0.36 |
| qwen3-8b | 0.660 | — | — | — | — |
| llama-3.1-8b | 0.607 | — | — | — | — |

These are the numbers Version 4's hardened tasks and the `+sim(GRPO)` arm must
improve on.
