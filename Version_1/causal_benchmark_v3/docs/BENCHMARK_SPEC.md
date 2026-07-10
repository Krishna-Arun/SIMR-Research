# CTB — Counterfactual Treatment Benefit Benchmark (v3)

All numbers below are measured on the existing model outputs + reference oracles
(`scripts/score_v3.py`, `outputs/ctb_scores.json`). The 96h demo outcome is confounded
(see §4/§5); the data upgrade in §5 removes that.

---

## (1) One-liner

**CTB tests whether a model can tell if a treatment will actually *help* a specific patient —
predicting the treatment's causal effect relative to a matched untreated twin, while not
inventing benefit where there is none.**

---

## (2) How scoring works

For each matched pair (treated twin A, untreated twin B), per marker, the ground-truth
**benefit** is the difference-in-differences of each arm's change from its **own** baseline:

```
effect_treated = (final_A - baseline_A)/|baseline_A|
effect_control = (final_B - baseline_B)/|baseline_B|
DiD            = effect_treated - effect_control
label = helps  if DiD < -TAU   (treated recovers more than the twin)
        hurts  if DiD > +TAU
        no-different otherwise            (TAU = 0.10)
```

Reported metrics (one coherent answer per case, plus its probability):

| metric | what it catches |
|---|---|
| **decisive accuracy** (on helps\|hurts cases) | the core skill: can you tell when treatment matters |
| **negative-control false-effect rate** (sodium, truth ≡ no-different) | hallucinated benefit |
| **calibration ECE** on the recorded activation-function probability | confident-but-wrong benchmaxing |
| **well-formed rate** (validity gate) | garbage/0-output scored as abstention, not silently averaged |
| **cluster-robust accuracy** (averaged per treated patient) | pair-reuse non-independence |

**The model must record a probability distribution over {helps, hurts, no-different}** (read
from the answer-token logits). This is a first-class output, scored by ECE — not an afterthought.

A predictor only looks good if it has **high decisive accuracy AND low negative-control
false-effect rate** simultaneously. Measured profiles:

```
predictor            acc   decisive  NC-FP↓  wellform  ECE↓
[oracle] baseline_copy 0.36   0.00     0.00     1.00     —     <- lazy "nothing changes"
[oracle] always_helps  0.24   0.32     0.88     1.00     —     <- "treatment fixes everything"
[oracle] pretrend      0.44   0.49     0.53     1.00     —     <- intervention-blind extrapolation
[oracle] physiology    0.65   0.59     0.00     1.00     —     <- real reasoner (TARGET PROFILE)
Qwen3-8B/zero          0.53   0.39     0.02     0.99    0.55
DeepSeek-R1-7B/zero    0.42   0.41     0.44     0.68    0.37   <- hallucinates effects + 32% garbage
```

Only the physiology oracle achieves high decisive **and** zero NC-FP. No lazy strategy does.

---

## (3) Why this is novel

- **Predicts a causal effect, not a value.** Almost all clinical-LLM benchmarks predict a lab
  value (forecasting) or answer an exam item (knowledge). CTB predicts the **sign of a
  counterfactual treatment effect** against a matched twin — a causal, per-patient question.
- **Benefit-aligned outcome separates "transient harm" from "real harm."** Using resolution at
  a long horizon (not the acute injury level) distinguishes the periprocedural troponin hump
  (treatment working) from genuine deterioration — a confound that sinks the naive version.
- **A negative-control marker as a benefit-hallucination trap.** Sodium has no causal pathway;
  predicting an effect there is scored as a false positive. Uncommon in clinical LLM evals.
- **The answer's probability is recorded from activations and scored for calibration.** Testing
  the *calibration of causal confidence* (not just accuracy) is, to our knowledge, not standard
  in clinical counterfactual LLM benchmarks.

---

## (4) Current solutions and why they fail

| approach | why it fails to test treatment usefulness |
|---|---|
| **Lab-value forecasting** (next-lab, trajectory) | rewards copying the baseline; a "no-change" oracle scored **0.66** on our v1. Measures curve-fitting, not causation. |
| **Medical QA** (MedQA, PubMedQA, MedMCQA) | tests recalled facts, not patient-specific counterfactual reasoning. |
| **Our v1 (level-MCCS)** | compared absolute final values → dominated by baseline ordering; the lazy "nothing changes" oracle **beat every LLM** (0.66 vs 0.49). |
| **Classical causal ML** (propensity / IPW / T-learner) | estimates *population-average* effects from structured tables; doesn't test an LLM reading a raw chart, and isn't per-patient from text. |
| **Naive "predict troponin direction after PCI"** | periprocedural hump inverts the benefit sign — beneficial PCI looks "harmful." Confirmed in golden samples (big-infarct cases labelled HURTS). |

---

## (5) Methodology

1. **Cohort:** MIMIC-IV cardiac admissions. Treated arms = PCI / CABG (revascularization);
   control = cardiac admission, labs, no revascularization. Index time event-grounded.
2. **Matched twins:** 1:K matching on comorbidity vector + baseline marker level + pre-trend
   direction (existing `build_matched_pairs.py`). Pairs are scored **cluster-robust by treated
   patient** to remove reuse inflation.
3. **Prompt:** per-patient, blind to the twin. Leakage-scrubbed notes + injected comorbidities
   (from v2). The model never sees outcomes; ICD discharge diagnoses are withheld (they leak).
4. **Outcome (the key upgrade):** **resolution at a long horizon** —
   `resolution = (peak_post − last_post)/peak_post` within index+14d (`extract_benefit_outcome.py`,
   run via `run_extract.sbatch`). Looks *past* the periprocedural hump so the marker movement
   reflects recovery, i.e. benefit. Sodium kept as negative control.
5. **Task:** model outputs, per marker, a benefit class {helps, hurts, no-different} **and a
   probability distribution over those classes** (read from answer-token logits — captured and
   stored as raw text + logits; the v1 pipeline failed to store raw text, v3 fixes this).
6. **Ground truth:** matched-pair DiD on `resolution`. Negative-control truth ≡ no-different.
7. **Scoring:** §2 metrics. Single canonical answer+probability from ONE mechanism (the v1
   parse-vs-logit contradiction of 68–83% is eliminated by reading the class probability directly).

---

## (6) Why this tests real reasoning, and why the lazy cheater fails

The matched twins have the *same* sickness, comorbidities, and baseline trend — **only the
treatment differs.** So "this patient looks sick → bad outcome" pattern-matching carries no
signal; the model must reason about what the *intervention* changes for *this* substrate
(fresh occlusion vs completed infarct, renal clearance, vessels treated).

Each cheating strategy is provably defeated (measured above):

- **Copy-baseline / "nothing changes":** DiD = 0 → "no-different" everywhere → **decisive
  accuracy 0.0.** It cannot tell help from harm — the only thing that matters.
- **"Treatment helps everything":** **negative-control false-effect rate 0.88.** Caught
  inventing benefit on sodium.
- **Intervention-blind extrapolation:** NC-FP 0.53 and mediocre decisive — confounded by drift.
- **Confident benchmaxing:** penalized by **calibration ECE** on the recorded probabilities;
  the answer must be probabilistically honest, not just frequently lucky.
- **Baseline-ordering exploit (what broke v1):** removed by construction — DiD subtracts each
  arm's own baseline, so "sicker starts higher" gives zero advantage.

To score well a model needs **high decisive accuracy AND a clean negative control AND
calibrated probabilities** at once — achievable (the physiology oracle does it: 0.59 / 0.00)
only by actually reasoning about whether the treatment helps this patient.
