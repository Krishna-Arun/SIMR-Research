# V4 Upgrade Plan — Counterfactual-Simulation Engine

**Status:** active. Scope chosen: **full rebuild + counterfactual validation**.
Compute: **laptop / CPU only** (scale-up and GRPO are documented cluster TODOs).

This plan supersedes the `CounterfactualSim/` design described in
[SUMMERS_GOAL.md](SUMMERS_GOAL.md) §3. The benchmark side (chained a→b→c→d,
hardening, agent scoring) is **unchanged and carried forward** — it is the
strong part of V4. What changes is the world model and how its value is proven.

---

## 0. Why (framing shift)

A novelty review of the 2026 literature found the *concept* "action-conditioned
JEPA world model for EHR counterfactual simulation" is already published in
multiple forms:

- **Clin-JEPA** (arXiv:2605.10840) — JEPA representation pretraining on EHR.
- **SMB-Structure** — JEPA world model for structured EHR.
- **EHRWorld** (arXiv:2602.03569), **ICOM** — intervention-conditioned clinical
  world models.
- **MedDreamer** (arXiv:2505.19785) — latent-imagination world model + ICU RL.
- **SepsisAgent / "Agentifying Patient Dynamics"** (arXiv:2605.14723) — LLM +
  clinical world model + RL (the `simulate()`-tool + GRPO idea).
- **CRN** (Bica 2020), **Causal Transformer**, **DeepBlip** — adversarially
  balanced counterfactual estimation over time (this *is* the "balance adapter").

Each individual ingredient of the V3/V4 engine is therefore **not novel**. The
one gap every EHR-world-model paper above *skips* is causal rigor: EHRWorld
explicitly states it "does not establish whether simulated treatment effects are
causally valid versus simply predictive," and uses **no** propensity / IPW /
doubly-robust / positivity machinery. That gap is the paper.

**Revised thesis for the world-model half:**

> Foundation-model-latent (CLMBR) clinical world models silently learn
> **confounded** dynamics — a naive action-conditioned rollout reproduces
> confounding-by-indication ("sick patients get treated and deteriorate")
> rather than a treatment effect. We (a) **diagnose** this leakage, (b)
> **correct** it with a balancing + doubly-robust layer with a positivity gate,
> and (c) provide the **first counterfactual validation** (semi-synthetic PEHE +
> RCT emulation) in this class of model.

This is *combination + rigor* novelty, not a new primitive. It must be defended
with (i) the leakage diagnostic figure and (ii) the validation numbers.

---

## 1. What dies

| File | Fate | Reason |
|---|---|---|
| `ac_jepa.py` | **replaced** | Not a JEPA; per-transition MLP; trained 1-step, served 3-step (OOD). |
| `world_model.py` | **deleted** | Transformer + EMA teacher present but never wired into training or serving — dead code. |
| `readout.py` | folded into new heads | Unused `ReadoutHeads` schema; superseded. |
| "+35.8% over persistence", AUC 0.678 (n=46) | **retired as evidence** | Persistence is the weakest baseline; n=46 val is noise. Not proof of a CF engine. |

## 2. What gets built (CPU-runnable)

### P1 — `latent_wm.py` (foundation)
1-D port of V-JEPA 2-AC's `VisionTransformerPredictorAC`:
- Per-step token block `[action_t, Δt_t, z_t]`, **block-causal** attention over
  the real temporal sequence.
- Predict **residual Δz** (natural history base); `z_{t+1} = z_t + Δz`.
- **Loss = teacher-forcing + autoregressive rollout** (V-JEPA 2-AC Eq. 2+3, L1).
  Training on its own rollouts is the fix for the documented "rollout direction
  drift." *Exit gate:* beats persistence **and** mean-Δ **and** 1-step baseline
  on **multi-step** val, in-distribution.

### P2 — causal rigor layer (`causal.py`, integrated in training)
- **Balance adapter Φ(z) + GRL adversary** — "if treatment is predictable from
  Φ, the representation didn't balance." Implemented as a **tuned Wasserstein
  IPM** (swept `λ_bal`), *not* max-strength (over-balancing destroys prognosis).
- **Propensity head + stabilized IPW**, combined with two potential-outcome
  heads (`μ₀` natural history, `μ₁` treated) into a **doubly-robust / R-learner**
  contrast → the arm difference is orthogonal to nuisance error.
- **Per-step balancing** (CRN-style) for time-varying confounding.
- **Positivity gate** at serve time: off-support queries → refuse / widen bands
  rather than extrapolate. Safety feature; wired into `simulate_server.py`.
- **Leakage diagnostic**: treatment-predictability from raw `z` vs `Φ(z)`, and
  the resulting bias in naive vs balanced rollouts. **← key paper figure.**

### P3 — validation (`validate.py`) — the milestone
CF error is invisible on factual data, so:
- **Semi-synthetic** benchmark with known potential outcomes (CRN tumor-growth
  style or MIMIC-derived sim) → **PEHE / error-on-ATE**. Fully CPU-runnable.
- **Small real-data trial emulation** on the existing 471 CLMBR embeddings
  against one decisive RCT direction (e.g. restrictive-vs-liberal transfusion,
  TRICC/TRISS; early-vs-late RRT, STARRT-AKI). Underpowered by design at n=471 —
  reported as a sanity check, not the headline.
- Negative/placebo controls; calibration/coverage of MC bands.
- *Exit gate:* passes semi-synthetic PEHE and recovers ≥1 emulated-trial
  direction. **Until this passes, `simulate()` is not trustworthy.**

### W7 — docs honesty (cheap, immediate)
Demote world-model `[Achieved]` rows in [PAPER_CRITERIA.md](PAPER_CRITERIA.md)
A6 and [SUMMERS_GOAL.md](SUMMERS_GOAL.md) §3 to `[Planned / to-measure]` pending
P3; add the 2026 related-work diff so the novelty claim is scoped to rigor.

## 3. Deferred to cluster (documented, not run on CPU)
- **W4 scale** — CLMBR-encode full MIMIC-IV (~50–65K stays) + eICU replication.
  The world model should be a *population* model; the benchmark stays cardiac-ICU.
- **W6 GRPO** — `vanilla / +sim(base) / +sim(GRPO)` ablation, run **only after
  P3 passes** (else it repeats V3's null with a still-broken tool).

## 4. Sequence & gates

| Phase | Deliverable | Gate |
|---|---|---|
| P0 | this doc + framing | agreed |
| P1 | `latent_wm.py` + smoke | beats multi-step baselines in-distribution |
| P2 | `causal.py` + diagnostic | adversary→base-rate w/o wrecking outcome head |
| P3 | `validate.py` | **semi-synthetic PEHE + 1 emulated trial** ← real milestone |
| W7 | doc corrections | claims match evidence |
| (cluster) | W4 scale, W6 GRPO | after P3 |

If P3 fails, the fallback is still publishable: a strong benchmark paper + an
honest negative result on FM-latent counterfactual simulation.
