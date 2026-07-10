# Benchmark-Paper Criteria Checklist

This checklist maps **Version 4** to the arguments a strong benchmark paper
must make. Each item states **concretely how v4 satisfies it**, and is honestly
tagged:

- **[Achieved]** — implemented and supported by data in hand.
- **[Planned / to-measure]** — designed and coded, but the number that
  proves it has not yet been collected.

See [SUMMERS_GOAL.md](SUMMERS_GOAL.md) for task definitions and
[README.md](README.md) for the run pipeline.

---

## A. The core arguments

### A1. It measures a capability we care about

**[Achieved]** The capability is **medical reasoning**, defined operationally
as constructing an inspectable, patient-specific causal tree (see
[SUMMERS_GOAL.md](SUMMERS_GOAL.md) §1). This matters clinically: a model that
can produce the correct *label* but not the *mechanism* is unsafe to deploy.
The rubric scores the mechanism directly (0.5 for generic textbook, 1.0 only
for patient-specific causal links), so the benchmark measures reasoning rather
than recall.

### A2. It measures it *well* (diverse, real ground truths)

**[Achieved]** components:
- **Real data.** MIMIC-IV v3.1, cardiac-ICU cohort cross-referenced from
  `mimic-iv-ext-cardiac-disease` — not synthetic vignettes.
- **Diversity of reasoning mode.** Four tasks cover retrieval-driven diagnosis
  (a), forward physiological prediction (b), counterfactual attribution (c),
  and calibrated prognosis (d).
- **Diversity of intervention arm.** Arm-balanced 34/34/32 across
  dialysis/transfusion/ventilation.
- **Objective ground truth where possible.** b directions (reference-band
  rule), c patient-ID, and d label are **deterministic and data-derived**, not
  model-judged.
- **Outcome integrity.** The 30-day readmission label was **repaired** from a
  broken 0% to 18.6% by re-deriving from the full admissions table per
  `subject_id` ([outcomes_fix.py](../Longitudinal/outcomes_fix.py)).

**[Planned / to-measure]** Judge reliability: **≥3 judge runs + a second judge
model**, reported via **Cronbach's α** and **inter-rater κ**, validated against
a **~20-item human-rated subset**. The reliability numbers are not yet
collected.

### A3. Current models do *not* have the capability

**[Planned / to-measure]** Target: strong models score **< 20%** on the
hardened full-credit metric, with **slow gains over time**. The v4 hardening is
explicitly designed to push scores down from the v3 baselines (gemma-4-e4b
0.675, qwen3-8b 0.660, llama-3.1-8b 0.607) by:
- removing lenient Stable-hedge credit and grading **joint all-labs-correct**
  in b;
- choosing **maximally ambiguous** attribution pairs (≈ chance) in c;
- **class-balancing** d so "always No" is not a free 0.80;
- keeping a **open-ended** with the golden lab **withheld** and requiring a
  ≥2-step patient-specific chain.

The v4 scores that confirm the < 20% target have not yet been measured.

### A4. Other benchmarks don't measure this

**Logical argument [Achieved].** Existing medical benchmarks (e.g.
multiple-choice board-exam style) reward selecting a correct option and can be
solved by pattern-matching to a canonical presentation. Version 4 differs on
three structural axes that no MC benchmark can capture:
1. **Open-ended** answers with the giveaway lab withheld (no option to
   back-solve).
2. **Chained, single-patient** tasks where later questions depend on earlier
   facts about the *same* patient.
3. **Counterfactual attribution** (task c), which requires reasoning about a
   treatment world that did *not* happen.

**Empirical argument [Planned / to-measure]** low correlation between v4
per-task scores and standard medical-QA scores for the same models. Not yet
measured.

### A5. Detailed failure analysis

**[Planned / to-measure]** The rubric is built for failure taxonomy: every
subjective score is 0 / 0.5 / 1, so failures separate cleanly into
**inaccurate (0)** vs. **generic-not-patient-specific (0.5)**. Objective tasks
localize failures further (which lab direction was wrong; whether the error was
the patient-ID or the mechanism). The per-step v3 breakdown already shows the
shape of failure (A2 answer-chain is weakest at 0.36 for gemma). The full v4
failure analysis is to be produced once scoring runs complete.

### A6. A path to improve model performance

**[Rebuilt + validated (world model) / Planned (LLM lift)]** The improvement
lever is an **action-conditioned latent counterfactual world model** (V-JEPA 2-AC
port) exposed as a `simulate()` tool, plus **GRPO** fine-tuning with the chain
rubric as reward. The V3 engine was rebuilt (see
[V4_UPGRADE_PLAN.md](V4_UPGRADE_PLAN.md)); the honest, load-bearing claims are now:
- **[Achieved]** Multi-step rollout beats persistence **and** mean-Δ (val AR-MSE
  1.119 vs 1.560 / 1.542) — the old "+35.8% over persistence" one-step metric is
  retired as non-evidence.
- **[Achieved]** *Motivating result:* treatment arm is predictable from the raw
  CLMBR latent at **macro-AUC 0.921** → the latents are confounded, so a naive
  world model is correlational, not causal.
- **[Achieved]** *Validation on ground truth:* IPW de-biases the ATE by **92%**
  under confounding; the positivity gate separates trustworthy (on-support) from
  untrustworthy (off-support, 2.1× PEHE) counterfactuals.
- **[Planned / to-measure]** Whether the validated `simulate()` lifts LLM scores
  via `vanilla / +sim(base) / +sim(GRPO)` — run **after** the validation gate, on
  the GPU cluster (v3 showed no lift with the *unvalidated* tool, motivating both
  the benchmark hardening and the engine rebuild).

---

## B. Benchmark-quality principles

| Principle | Status | How v4 satisfies it |
|---|---|---|
| **Scale** | Partial [Achieved] | 494 cardiac-ICU stays, 471 CLMBR-encoded; balanced 100-case chained eval set. Small but real; see Limitations in [README.md](README.md). |
| **Realism** | [Achieved] | Real MIMIC-IV v3.1 records; anchors are actual lab-driven ICU interventions; guideline-grounded question generation via PubMed MCP. |
| **Difficulty** | [Planned / to-measure] | Every task hardened to suppress guessing (open-ended, withheld golden lab, joint all-labs metric, ambiguous pairs, balanced classes). Target < 20% full-credit; not yet confirmed. |
| **Diversity** | [Achieved] | Four reasoning modes × three intervention arms (34/34/32) × 50/50 mortality balance. |
| **"Solving 10% ≠ solving all"** | [Achieved by design] | The chain requirement and joint all-labs-correct metric mean partial pattern-matching cannot masquerade as full competence; each task probes a distinct mode so a model cannot ride one strength. |
| **Scoring accuracy** | Mixed | Objective parts deterministic & data-derived **[Achieved]**; subjective parts on a 0/0.5/1 rubric with multi-run + second-judge reliability **[Planned / to-measure]**. |
| **Uncorrelated with other benchmarks** | [Planned / to-measure] | Structural novelty argues for low correlation (A4); empirical decorrelation not yet measured. |
| **Organized by importance** | [Achieved] | Tasks ordered a → b → c → d in clinical time; scoring separates load-bearing full-credit (patient-specific causal chain) from partial textbook credit. |

---

## C. Honesty ledger (what is real vs. pending)

**Already real:**
- Cohort, splits, inclusion filters, and anchors.
- Outcome labels including the repaired 30-day readmission (18.6%) and
  1-year mortality (19.8%).
- Balanced 100-case chained set.
- **V4 world-model rebuild:** multi-step rollout beats persistence + mean-Δ;
  leakage diagnostic (arm macro-AUC 0.921 from raw CLMBR latents); positivity
  finding (463/471 off-support); ground-truth validation (IPW −92% ATE bias,
  2.1× on/off-support PEHE). Code: `latent_wm.py`, `train_wm.py`, `causal.py`,
  `validate.py`.
- v3 baseline scores (gemma/qwen/llama) and the v3 `+sim` null result.

**Retired (was over-claimed in V3):**
- The "+35.8% over persistence" Δz-MSE, mortality AUC 0.678 (n=46 val), and lab
  MSE 0.438 as evidence of a working counterfactual engine — one-step, weak
  baseline, tiny n. Replaced by the honest metrics above.

**Still to measure:**
- v4 hardened-task scores for all models (the < 20% difficulty claim).
- Judge reliability (Cronbach's α, κ) and human-subset validation.
- Empirical decorrelation from existing medical benchmarks.
- Real-data cross-arm effects at scale (blocked by overlap at n=471 → needs
  full MIMIC-IV; W4, cluster).
- LLM lift from `+sim(base)` and `+sim(GRPO)` on the hardened set (GRPO run
  deferred to GPU cluster — see [README.md](README.md)), run after the
  validation gate.
