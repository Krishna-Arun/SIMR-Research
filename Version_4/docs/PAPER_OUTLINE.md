# SIMR — Paper Outline: Benchmarks, Counterfactual Engine, and Novelty

One thesis ties the two halves together:

> **Measure medical *reasoning* (not recall), and improve it by letting a model reason
> against a counterfactual simulator that is proven to be causally valid.**

- The **benchmark** is the *measurement instrument* (does a model construct an inspectable,
  patient-specific causal chain?).
- The **counterfactual engine** is the *improvement lever* (a `simulate()` tool the model
  reasons with) — and, separately, a methods contribution in its own right because it is
  **validated against real RCTs**, which the 2026 EHR-world-model literature does not do.

---

## PART I — The benchmark (measurement)

Chained, single-patient, real MIMIC-IV cardiac-ICU cases. Four tasks in clinical time order
around an **anchor** (the first lab-driven intervention). Every task scores the *causal chain*
(0 = wrong, 0.5 = generic textbook, 1 = patient-specific causal link), not just the label.

| Task | INPUT | PROCESS | OUTPUT | SCORING |
|---|---|---|---|---|
| **a — Request + Answer** | Minimal patient stub; tools that return lab/micro **names+dates only** (values withheld); PubMed | Agentic loop: model *requests* specific values and must justify each; then answers an **open-ended** diagnosis / next-intervention | Diagnosis + **≥2-step patient-specific causal chain** citing retrieved values | Evaluator agent, 0/0.5/1 on request quality + chain |
| **b — 72h Lab Trajectory** | Pre-anchor labs + the intervention performed | Predict each core lab's 72h direction + mechanism + confidence | {lab → Rising/Falling/Stable} + causal justification + confidence | **Deterministic** reference-band ground truth (**joint all-labs-correct**) + agent-graded justification |
| **c — Intervention Attribution** | Two patients, **similar baselines / different interventions**, + one observed 72h post-panel | Decide which patient the panel belongs to and why (counterfactual discrimination) | Patient-ID + causal-physiology mechanism | **Deterministic** patient-ID (pairs tuned so label-guessing ≈ chance) + agent-graded mechanism |
| **d — 1-Year Mortality** | Patient's longitudinal trajectory | Predict mortality + calibrated confidence + risk rationale | Probability + rationale | Correctness + **calibration** (Brier/ECE) + agent-judged rationale |

**Why it's hard to game:** open-ended answers with the "golden" lab withheld (a); joint
all-labs-correct instead of per-lab partial credit (b); maximally ambiguous pairs (c);
class-balanced so "always No" isn't free (d). Reasoning quality is graded directly.

Status: tasks + cohort + scoring built; reliability (α/κ, human subset) and the <20%
difficulty target are **to-measure**.

---

## PART II — The counterfactual engine (improvement lever + methods result)

### II.1 Cohort building — INPUT→PROCESS→OUTPUT
- **INPUT:** full MIMIC-IV v3.1 (local).
- **PROCESS:**
  1. CAD admissions (ICD 410–414 / I20–I25): 546k → **108,833**.
  2. **Decision-node filter** — keep only angiographically evaluated: → **22,328** (this is what
     makes "medical" a real *choice*, not incidental coding).
  3. Label modality (medical/PCI/CABG), presentation (STEMI/NSTEMI/UA/stable), outcomes
     (in-hospital + 1-yr mortality), confounders (age, sex, 11 comorbidities, 14-lab panel).
  4. **Equipoise restriction** — 3-way propensity; keep patients with ≥10% probability of
     *each* arm → **6,976** who could honestly have gone any way (13,151 one-way excluded).
  5. **Hourly substrate** — link to ICU stays; first 72h; **STATE** = 7 vitals + 12 labs (LOCF)
     + 2 procedure flags; **ACTION** = 11 drug drips/hour.
- **OUTPUT:** Cohort A (population, RCT-validation) + Cohort B (hourly, equipoise, engine training).

### II.2 The engine — INPUT→PROCESS→OUTPUT
- **INPUT:** hourly (state, action) sequence for an equipoise patient.
- **PROCESS:** 1-D action-conditioned world model (V-JEPA-2-AC port: block-causal transformer,
  residual Δstate, teacher-forcing + rollout loss) + deconfounding (balance adapter, per-step
  CRN balancing, propensity/IPW, doubly-robust) + **positivity gate**.
- **OUTPUT:** predicted next-hour state → counterfactual rollout under a **modified drug
  sequence**, with uncertainty bands and an **on/off-support flag** (refuses when unanswerable).
- **As a tool:** served as MCP `simulate(state@t, proposed intervention)`; the LLM calls it
  while answering the benchmark; **GRPO** fine-tunes the LLM with the rubric as reward.

### II.3 Validation — the part that earns the paper
- **INPUT:** the engine's effect estimates. **PROCESS:** compare to external truth.
- **RESULTS (population, ✅ done):** deconfounded PCI-vs-medical recovers **both** the
  ISCHEMIA/COURAGE **null** in stable CAD (AIPW −0.4 pp) **and** the early-invasive **benefit**
  in NSTEMI/ACS (−3.7 pp) — by **two independent methods** (doubly-robust *and* matched twins),
  where the naive analysis confounds both into a spurious −6 pp.
- **RESULTS (hourly, ⏳):** next-hour prediction beats persistence/mean-Δ (P1 gate, in training);
  then drug counterfactuals checked against **known pharmacology** (norepi→BP↑), **dose-response
  monotonicity**, and ≥1 **drug RCT** direction.

---

## What the paper looks like

**Title (working):** *Causally-Validated Counterfactual Simulation for Clinical Reasoning:
recovering randomized-trial effects from EHRs, and using them to teach an LLM to reason.*

**Structure:**
1. **Problem** — LLMs and EHR "world models" produce plausible interventional predictions that
   are actually confounded; nobody checks them against ground truth.
2. **Benchmark** — SIMR chained a→d, scoring the causal chain (Part I).
3. **Engine** — equipoise-restricted, deconfounded counterfactual simulator (Part II).
4. **Validation** — recovers 2 RCT truths by 2 methods (headline figure); honest ceilings.
5. **Application** — `simulate()` + GRPO improves benchmark reasoning (`vanilla/+sim/+sim(GRPO)`).
6. **Limitations** — below.

**Headline figures:** (i) naive −6 pp "PCI saves lives" collapsing to the RCT-consistent
stratified truths; (ii) equipoise/overlap funnel (22k→7k); (iii) the benchmark difficulty +
`+sim(GRPO)` lift.

---

## Where the novelty is (honest, ranked)

**Genuinely novel / defensible:**
1. **Causal *validation* of an EHR counterfactual simulator against multiple RCTs.** The 2026
   world-model papers (EHRWorld, ICOM, MedDreamer, Clin-JEPA, SMB-Structure) condition on
   interventions but **never establish causal validity** (EHRWorld says so explicitly). Recovering
   the ISCHEMIA null *and* the ACS benefit — two opposite truths, two methods — is the contribution.
2. **Methodological cautions with teeth** (each demonstrated, not asserted):
   - naive propensity in high-dim/FM-latent space **fabricates** positivity violations
     (overfit AUC 0.9 vs honest 0.6) — a trap the field will keep hitting;
   - **cohort definition, not scale, creates identifiability** (the angiography filter turned a
     dead 92k-medical arm into a balanced, overlapping cohort);
   - **individual counterfactuals are capped by unobserved effect-modifiers** (coronary anatomy),
     proven by two estimators failing an honest sorted-group test — a bound, not a bug.
3. **The benchmark** — chained, single-patient, causal-chain-scored, with a counterfactual-
   attribution task (c) that no multiple-choice medical benchmark captures.
4. **The integration** — a *validated* CF simulator as an LLM tool + GRPO for reasoning.

**NOT novel (own it in related work):**
- Action-conditioned latent EHR world models (taken).
- JEPA-for-EHR (Clin-JEPA), Dreamer-for-ICU (MedDreamer).
- Adversarial balancing / CRN, doubly-robust estimation, overlap weights (established methods —
  we *apply and validate*, we don't claim to invent).

**One-line positioning:** *not "we built an EHR world model" (done five times), but "EHR
counterfactual simulators are confounded and unvalidated — here is one that provably recovers
randomized-trial effects, an honest map of where individual prediction breaks, and its use as a
reasoning tool."*

---

## Honest limitations (state them, don't hide them)
- Individual (per-patient) counterfactuals not yet reliable — bounded by unobserved anatomy
  (extractable from cath-report text; first-pass extractor built).
- Observational; residual confounding possible (no SYNTAX/LVEF yet). The two-method, two-RCT
  agreement is the mitigation.
- Small anatomy-labeled subset (~1,500); scaling needs the `mimic-iv-note` download.
- GRPO/agent lift is designed but **unrun** (cluster).
- Hourly engine trained on CPU as proof-of-gate; tuned model is a GPU job.
```
