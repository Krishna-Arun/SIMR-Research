# SIMR Counterfactual Simulation — System Plan (canonical)

Supersedes `V4_UPGRADE_PLAN.md`. Reflects the CAD-cohort pivot and the hourly
state–action redesign. Status tags: ✅ done · ⏳ next/planned · 🔒 cluster/deferred.

---

## 0. Thesis

Foundation-model / EHR world models are usually **confounded** (sicker patients get
more treatment), so a naive rollout reproduces association, not effect. Our contribution
is **causal validity + validation**: deconfound the simulator and prove it recovers known
truths (RCTs, pharmacology) — the check the 2026 EHR-world-model papers skip. The engine
is exposed to an LLM as a `simulate()` tool and the LLM is RL-fine-tuned to reason with it.

---

## 1. Cohort building

### Cohort A — CAD multi-modality (population causal VALIDATION anchor) ✅
`build_cad_cohort_full.py`, `enrich_labs.py`
- Source: full MIMIC-IV v3.1 `hosp`.
- CAD dx (ICD-9 410–414 / ICD-10 I20–I25): 108,833 admits.
- **Decision-node restriction:** keep only angiographically evaluated (cath) → **22,328**.
  This makes "medical" = *chose medical management*, balancing the arms (~6.5k each).
- Modality: CABG / PCI / medical. Presentation: STEMI / NSTEMI / UA / stable-chronic.
- Outcomes: in-hospital death, 1-yr mortality, LOS.
- Confounders: age, sex, 11 comorbidities, 14-lab baseline panel (chunked from labevents).
- Overlap proven: honest cross-fitted propensity AUC 0.66–0.78, ~12,447 edge patients.

### Cohort B — Hourly ICU state–action substrate (world-model TRAINING data) ✅
`build_hourly.py` → `hourly_substrate.pkl`
- 12,179 CAD ICU stays, first **72 h** each; 12,023 pass the ≥6-valid-hour filter.
- **STATE(t):** 7 vitals (chartevents) + 12 labs (LOCF, labevents) + **cumulative prior
  procedures** (ventilation, dialysis, …; ⏳ appending now).
- **ACTION(t):** 11 drug drips per hour (inputevents; rate/hour).
- Heavy scans (chartevents 3.3 G, labevents 2.4 G) cached to parquet.

---

## 2. Architecture

### 2a. Simulation engine
- **`latent_wm.py`** — 1-D action-conditioned world model (V-JEPA-2-AC port): block-causal
  transformer over the hourly sequence; per-step tokens `[action, Δt, state]`; predicts
  **residual Δstate**. Loss = **teacher-forcing + autoregressive rollout** (masked to
  observed values so irregular sampling is handled). Training on its own rollouts prevents
  multi-step drift. ✅ built · ⏳ hourly training.
- **`causal.py`** — deconfounding: balance adapter Φ + GRL adversary, **per-step (CRN)
  balancing** for time-varying confounding, propensity π(drug|state) + IPW, doubly-robust
  contrast, **positivity gate** (refuse off-support). ✅ built (tabular) · ⏳ port to hourly.
- **Counterfactual** = roll forward under a **modified action sequence** (withhold/adjust a
  drug at hour t) and compare trajectories = neural g-computation / CRN.

### 2b. LLM agent 🔒/⏳
- Engine served as MCP **`simulate()`**: state@t + proposed drug change → predicted
  trajectory + outcome, **with uncertainty and on/off-support flag**.
- LLM answers the chained benchmark, calling `simulate()`; **GRPO** fine-tunes it with the
  rubric as reward. Ablation: `vanilla / +sim(base) / +sim(GRPO)`.

---

## 3. Training plan + validation gates

| Phase | Trains | Gate | Status |
|---|---|---|---|
| **P1 Dynamics** | `latent_wm` on Cohort B | next-hour prediction beats persistence **and** mean-Δ, multi-step, held-out | ⏳ now |
| **P2 Deconfound** | balance + propensity + DR, per-step | adversary→chance w/o wrecking prediction; leakage diagnostic | ⏳ |
| **P3 CF validation** | (eval) | recovers known pharmacology (norepi→BP↑), dose-response monotonicity, ≥1 drug-RCT direction; gate refuses off-support | ⏳ **milestone** |
| **P4 Individual CATE** | DR-learner / matched twins on balanced rep | sorted-group test ≳2σ | ⏳ |
| **P5 Agent** | LLM via GRPO + `simulate()` | `+sim(GRPO)` > `vanilla`/`+sim(base)` on hardened benchmark | 🔒 |

**Already validated (population):** CAD medical-vs-PCI recovers the ISCHEMIA null (stable,
AIPW −0.4 pp) AND the ACS benefit (−3.7 pp), by **two independent methods** (AIPW + matched
twins). Naive analysis confounds both into a spurious −6 pp. This is the causal-validity
proof; the hourly engine extends it to drug-level, better-overlap counterfactuals.

**Known ceiling (honest):** individual CAD CATE was noise-limited — the decisive modifier
(coronary anatomy) is unobserved (lives in cath-report text; `extract_anatomy.py` is a first
pass). Hourly drug data has far better overlap, so P4 is a genuine re-test there.

---

## 4. File map
`build_cad_cohort_full.py` `enrich_labs.py` `effect_cad.py` `matched_cad.py` `cate_cad.py`
`train_cf_sim.py` `extract_anatomy.py` (Cohort A + population causal work) ·
`build_hourly.py` `latent_wm.py` `causal.py` `train_wm.py` (Cohort B + engine) ·
`hourly_substrate.pkl` `cad_cohort_full.parquet` `cad_labs.parquet` `cad_matched.parquet`
`cad_anatomy.parquet` (artifacts).
