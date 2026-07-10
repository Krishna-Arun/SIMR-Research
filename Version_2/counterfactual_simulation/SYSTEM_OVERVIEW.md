# Counterfactual Simulation Engine — System Overview

A component-by-component and pipeline-by-pipeline walkthrough of the cardiac
counterfactual simulator. Every entry gives **purpose** and **input → process →
output** so you can trace a lab value from MIMIC all the way to a counterfactual
treatment contrast.

**The one-line idea:** freeze a pretrained EHR foundation model (CLMBR) as the
patient-state encoder, learn a small *action-conditioned* predictor on top of its
latent that says "given this state and this treatment, here is the next state,"
then decode that latent into labs and outcome risk. Because the predictor is
action-conditioned, you can ask it counterfactual questions ("what if we had *not*
given the drip?") by swapping the action sequence.

All paths are relative to
`/scratch/users/karun09/Version_2/counterfactual_simulation/`.

---

## 0. The mental model (read this first)

```
   RAW MIMIC-IV                    FROZEN                    LEARNED (small MLPs)
   ┌──────────┐   MEDS    ┌──────────────┐   z_t    ┌───────────────────────┐
   │ labs,dx, │ ────────► │  CLMBR-t     │ ───────► │  AC-JEPA predictor     │
   │ meds,proc│  (codes)  │  encoder     │  768-d   │  ẑ_{t+1}=z_t+f(z,a,Δt) │
   └──────────┘           │  (femr)      │  latent  └───────────┬───────────┘
        │                 └──────────────┘                      │ z_t / ẑ_{t+1}
        │ drips/procs                                           ▼
        ▼                                            ┌──────────────────────┐
   ┌──────────┐                                      │ LabDecoder  z→14 labs│
   │ enriched │  a_t (34-dim action vector) ────────►│ OutcomeDec  z→risk   │
   │ actions  │                                      └──────────────────────┘
   └──────────┘
```

- **State `z_t`** = a 768-d CLMBR latent. Encoder is **frozen** — never trained here.
- **Action `a_t`** = a 34-dim vector describing the treatment given in the
  interval that *drives* the transition into state `t`.
- **Predictor** = the only "dynamics" model. Small (~0.3M params). Predicts the
  *residual* `ẑ_{t+1} − z_t` with a Gaussian head (mean + variance → uncertainty).
- **Decoders** = read-out heads. Turn a latent into human-readable labs and into
  mortality risk. They do **not** model dynamics; they just translate `z`.
- **Anti-circularity wall** = one patient-level train/val/test split, fixed once
  (`build_split.py`), reused by *every* stage so no patient leaks.

---

## 1. Components (the model pieces)

### 1.1 CLMBR encoder (frozen foundation model)
- **Purpose:** turn a patient's entire coded medical timeline into a single
  768-d latent per timepoint — the "state." Chosen so we inherit a rich
  representation without training on our tiny cohort.
- **Input:** a patient's MEDS event stream (birth, gender, diagnoses,
  procedures, meds as NDC, labs as LOINC+value), full lifetime history as context.
- **Process:** `femr` runs the pretrained `clmbr-t-base` (StanfordShahLab) over
  the timeline; a patched `encode_clmbr` emits one embedding per event time and
  records the **absolute timestamp** of each (`abs_times`) so actions can be aligned.
- **Output:** `data/encoded_states_clmbr.pkl` — list of
  `{patient_id, s:[T,768], abs_times:[T], outcomes}`.
- **Key fact:** never fine-tuned. Everything downstream lives or dies by how much
  clinical signal this frozen latent already carries (see the probe, §3.7).

### 1.2 AC-JEPA predictor — `ACJEPA` (`train_substrate_wm.py:55`)
- **Purpose:** the world model. Predict the next latent state given current state,
  action, and elapsed time. This is what makes counterfactuals possible.
- **Input:** `z_t` (768), `a_t` (34-dim action), `Δt` (hours since previous state).
- **Process:**
  - `adapter`: 768 → 128 (a "balance" representation used for deconfounding).
  - `act_enc`: 34 → 32; `dt_enc`: featurizes Δt as `[log1p(Δt), Δt/24]` → 16.
  - `trunk`: concat(128+32+16) → 256 → 256 with LayerNorm/ReLU/Dropout.
  - Two heads: `mu` (768) and `logvar` (768) → **residual** prediction
    `ẑ_{t+1} = z_t + mu`, with `logvar` giving a per-dimension uncertainty.
  - `arm_head` (128 → n_arm): the **CRN adversary**, fed through a gradient-reversal
    layer, used only to strip treatment-selection signal from the adapter.
- **Output:** predicted next latent `ẑ_{t+1}` (point) or `(mu, logvar)` (for MC
  sampling in rollouts).
- **Losses it exposes:** `nll` (Gaussian negative log-likelihood on the residual,
  IPW-weighted) and `adv_loss` (adversary cross-entropy on arm).

### 1.3 LabDecoder — `LabDecoder` (`train_substrate_wm.py:86`)
- **Purpose:** translate a latent into the 14 core lab values so predictions are
  human-readable and gradable.
- **Input:** a latent `z` (768) — either the real `z_t` or a predicted `ẑ_{t+1}`.
- **Process:** MLP 768 → 128 → 14, trained to regress **standardized** lab values
  (per-lab z-scored on the train split). Masked MSE so missing labs don't
  contribute.
- **Output:** 14 standardized lab predictions; multiply by saved scaler
  (mean/var) to get real units.
- **14 labs:** creatinine, bun, potassium, sodium, chloride, bicarbonate,
  anion_gap, glucose, magnesium, phosphate, hemoglobin, hematocrit, platelets, wbc.

### 1.4 OutcomeDecoder — `OutcomeDecoder` (`add_outcome_decoder.py:15`)
- **Purpose:** translate a latent into outcome risk (mortality).
- **Input:** a latent `z` (768).
- **Process:** MLP 768 → 128 → 2, BCE-with-logits on patient outcomes
  `[mortality, mortality_30d]`. Evaluated **patient-level** (mean risk per patient)
  so repeated timepoints can't inflate AUROC.
- **Output:** 2 risk logits → sigmoid → probabilities.
- **Result:** test AUROC **mortality 0.864**, **mortality_30d 0.733**.

### 1.5 Deconfounding machinery (not a separate file — woven into training)
- **Purpose:** the whole point is *counterfactual* contrast, so treatment-selection
  bias must be removed. Sicker patients get more treatment; naïvely the model would
  learn "treatment → death."
- **Two mechanisms:**
  1. **Stabilized IPW** (`train_substrate_wm.py:146`): fit a propensity model
     `π(arm | z_t)`, weight each transition by `marginal(arm) / π(arm|z)`, clipped
     to `[0.1, 10]`. Down-weights over-represented treatment/state combos.
  2. **CRN adversary** (gradient reversal on the adapter): the adapter is trained
     so an arm classifier *cannot* recover the treatment arm from it → a
     balanced representation.
- **Measured effect (the honest number):** arm-predictability from the latent drops
  only **0.703 → 0.685**. Small. This is a known weak spot (see §5).

### 1.6 Action vocabulary / schema (`data/action_schema.json`)
- **Purpose:** define the 34-dim action layout and how continuous rates are normalized.
- **Layout (34 dims):**
  - 11 continuous drips × (on-bit + normalized rate) = 22 dims: norepinephrine,
    epinephrine, dopamine, dobutamine, vasopressin, phenylephrine, milrinone,
    insulin, propofol, fentanyl, midazolam.
  - 5 presence-only drips: heparin_iv, furosemide_iv, amiodarone, nitroglycerin,
    nicardipine.
  - 5 procedures: ventilation, dialysis, cardiac_cath, iabp, impella.
  - 2 point interventions: pci, cabg.
- **Rate normalization ("Option A"):** per drug, cap at 99.5th pct → `log1p` →
  robust-scale (median/IQR). **Fit on TRAIN patients only** and saved, so val/test
  reuse the same scalers (no leakage).

---

## 2. Data processing pipeline (raw MIMIC → training substrate)

Run **in order**. Everything below the split reads the frozen split, so nothing
leaks. Encoder stages run in the `clmbr311` env (needs `femr`/`datasets`);
modeling stages run in `simr` (torch 2.6 + CUDA).

### Stage D1 — Cohort MEDS build (`build_cohort_meds.py`)
- **Purpose:** build MEDS for *only* the ~1,431 cohort admissions' patients,
  emitting codes in the exact Athena namespaces CLMBR recognizes. The critical
  trick: relabel MIMIC-native lab itemids to `LOINC/<code>` via a crosswalk —
  otherwise labs are invisible to CLMBR.
- **Input:** `cohort/cohort_v1.parquet` (the cardiac cohort with arm + outcomes),
  raw MIMIC-IV CSVs (patients, admissions, diagnoses, procedures, prescriptions,
  labevents), `cohort/lab_loinc_final.json` (lab→LOINC map).
- **Process:** per subject, collect birth/gender/death, dotted-ICD diagnoses &
  procedures, NDC-normalized meds, LOINC-mapped labs with numeric values; sort by
  time; keep full lifetime history as CLMBR context; also carve out the
  index-admission window as the "trajectory" (label times + precomputed action_ids).
- **Output:**
  - `data/mimic_meds/data/cohort_000.parquet` — MEDS for the encoder.
  - `data/trajectories.pkl` — per-patient index-window events with lab values,
    action_ids, and outcomes (arm, mortality, etc.). **This is the label source
    for everything downstream.**
  - `data/action_vocab.json`.

### Stage D2 — CLMBR encode (external, `femr`)
- **Purpose:** run the frozen encoder over the MEDS to produce latents.
- **Input:** `data/mimic_meds/…parquet`.
- **Process:** patched `encode_clmbr` → embeddings + `abs_times` per timepoint.
- **Output:** `data/encoded_states_clmbr.pkl`.

### Stage D3 — Canonical split (`build_split.py`)  ← the anti-circularity wall
- **Purpose:** one patient-level train/val/test split, seeded and checked in, that
  every stage reuses. Patient-level (not admission-level) so no patient leaks;
  stratified by arm so balance holds in each split.
- **Input:** `data/trajectories.pkl` (patient_id + arm).
- **Process:** shuffle within each arm (seed 0), 70/10/20; assert zero overlap.
- **Output:** `data/splits.json` — **train 972 / val 140 / test 277** patients
  (arm mix e.g. test: medical 171, pci 75, cabg 31).

### Stage D4 — Enriched actions (`build_enriched_actions.py`)
- **Purpose:** build the 34-dim action vector aligned to CLMBR timepoints.
- **Input:** `data/encoded_states_clmbr.pkl` (for `abs_times`),
  `data/trajectories.pkl` (PCI/CABG point events), `cohort/cohort_v1.parquet`,
  MIMIC `icu/inputevents` (drips) + `icu/procedureevents`, `data/splits.json`.
- **Process:** for each transition interval `(T_{i-1}, T_i]`, mark any drip/procedure
  overlapping the window (on-bit + normalized max rate for continuous drips), and
  any PCI/CABG point event. **Alignment rule:** `action_matrix[i]` describes the
  treatment driving the transition *into* state `i`; `action_matrix[0]` is zeros.
  Rate scalers fit on train only.
- **Output:** `data/enriched_actions.pkl` (per-patient `[T,34]` matrix) +
  `data/action_schema.json`.

### Stage D5 — Training substrate (`build_train_substrate.py`)
- **Purpose:** fix two data-quality bugs and produce the *single* file everything
  trains on. Without this, dense-charting patients dominate (top patient = 29% of
  timepoints) and some patients' timepoints span multiple years.
- **Input:** `data/encoded_states_clmbr.pkl`, `data/enriched_actions.pkl`,
  `data/action_schema.json`, `cohort/cohort_v1.parquet`, MIMIC admissions.
- **Process:**
  1. **WINDOW** — keep only timepoints inside the cohort admission window (±6h).
     Kills multi-year contamination (CLMBR still saw full history as context).
  2. **CAP** — uniformly subsample to ≤150 timepoints/patient so no one patient
     dominates (Δt is a model input, so wider gaps are fine).
- **Output:** `data/train_substrate.pkl` — list of
  `{patient_id, s:[T,768], abs_times, hours, action_matrix:[T,34], action_cols,
  outcomes}`. **Every model/probe/eval reads THIS file.**

### (Parallel, in progress) ICU widening — D1′–D5′ on a 10k broad sample
- **Purpose:** test whether 7× more data lifts the weak lab-direction gate.
- **Scripts:** `build_icu_sample.py` → `build_icu_meds.py` →
  `filter_icu_meds_bounded.py` (bound context to admission window so the encode is
  tractable) → `split_icu_shards.py` (4 shards for parallel encode) →
  (encode per shard) → `merge_icu_shards.py` → `build_enriched_actions_icu.py` →
  `build_train_substrate_icu.py`.
- **Status:** encode job queued/pending; **not a dependency** for the cardiac
  prototype, which is complete.

---

## 3. Training & evaluation pipeline (substrate → results)

All read `data/train_substrate.pkl` + `data/splits.json`. Run in `simr`.

### T1 — World model + lab decoder (`train_substrate_wm.py`)
- **Purpose:** train the predictor and the lab decoder; run the go/no-go gates.
- **Input:** `data/train_substrate.pkl`, `data/trajectories.pkl`, `data/splits.json`.
- **Process:**
  1. Build transitions `(z_t, a_t, Δt, z_{t+1}, arm)` + LOCF lab panels at both endpoints.
  2. Fit stabilized IPW weights on arm.
  3. Train `ACJEPA` 60 epochs: `nll(IPW-weighted) + 0.5·adv_loss`.
  4. Train `LabDecoder` 80 epochs: masked MSE on standardized labs.
  5. Gates: (a) val MSE < persistence; (b) arm-predictability raw→adapter;
     (c) lab-direction balanced accuracy.
- **Output:** `data/world_model_enriched.pt` (+ lab scaler) and
  `data/world_model_enriched_metrics.json`.
- **Results:** val MSE **0.851 vs persistence 1.229** (beats), train/val gap
  **−0.05** (no overfit), arm-predictability **0.703 → 0.685**, lab-direction mean
  balacc **0.398** (chance 0.333) — the weak spot.

### T2 — Outcome decoder (`add_outcome_decoder.py`)
- **Purpose:** add the mortality-risk head and fold it into the checkpoint.
- **Input:** `data/train_substrate.pkl`, `data/splits.json`,
  `data/world_model_enriched.pt`.
- **Process:** train `OutcomeDecoder` 60 epochs (BCE), evaluate patient-level AUROC
  on test.
- **Output:** `outcome_dec` added to `data/world_model_enriched.pt`;
  `data/outcome_decoder_metrics.json`.
- **Results:** mortality **0.864**, mortality_30d **0.733**.

### T3 — Model-free benchmark eval (`eval_simulator_benchmarkB.py`)  ← the honest proof
- **Purpose:** does the simulator actually predict real lab movement on held-out
  patients, without any LLM? Uses Benchmark-B's own direction rule.
- **Input:** `data/train_substrate.pkl`, `data/trajectories.pkl`, `data/splits.json`,
  `data/world_model_enriched.pt`, Benchmark-B `questions.jsonl` (for ref ranges).
- **Process:** for each (lab, time-zero) on TEST, roll the model forward through
  the **actual** actions to the last timepoint within H=48h, decode → predicted
  post value → Rising/Falling/Stable. Compare to persistence and majority. **Require
  a real remeasurement** (fixes the LOCF "fake stable" artifact).
- **Output:** `data/benchmarkB_eval.json`.
- **Results:** overall a **tie** (sim 0.585 vs pers 0.584); but on the
  **abnormal-baseline** subset — where a lab can actually move — sim **0.512 vs
  pers 0.333** (persistence structurally can only say "Stable" there). This is the
  defensible headline.

### T4 — Counterfactual rollout (`rollout_counterfactual.py`)
- **Purpose:** the demo artifact — one patient, two treatment plans, uncertainty bands.
- **Input:** `data/world_model_enriched.pt`, `data/train_substrate.pkl`, `data/splits.json`.
- **Process:** pick a test patient with an abnormal baseline + horizon ≥5. From
  `z0`, MC-roll (**K=64** samples through the Gaussian head) under two action
  sequences — **factual** vs **no-treatment** — decoding labs + mortality risk at
  each step; report 10–90 percentile bands and the treatment contrast (Δ risk).
- **Output:** `data/rollout_example.json` with per-step `{mean, lo, hi}` per lab and
  per outcome, a treatment-contrast Δ, and a reliability flag (RELIABLE only for
  abnormal-baseline cases).
- **Caveat:** multi-step error compounds (step-5 bands blow out); the Δ is still
  confounded because deconfounding is weak (§5).

### T5 — State-design probe (`probe_lab_decodability.py`)  ← the diagnostic
- **Purpose:** the gate that decided "state = single 768-d latent + decoder head."
  Answers: how much lab signal is even *in* the frozen latent?
- **Input:** `data/train_substrate.pkl`, `data/trajectories.pkl`, `data/splits.json`.
- **Process:** Ridge `z → lab` (per lab), fit on train, R² on test.
- **Output:** `data/lab_decodability.json`.
- **Results:** **median R² ≈ 0.49** (e.g. chloride 0.64, sodium 0.61, bun 0.52,
  creatinine 0.49; anion_gap 0.26, bicarbonate 0.33). Verdict: "decode-only
  viable" — **but** this 0.49 is the information ceiling: half of lab variance is
  not in the latent, which caps how well direction can ever be predicted.

### T6 — Ablation: delta-aware, cardiac-only (`train_delta_decoder_cardiac.py`)
- **Purpose:** isolate the *training-objective* lever from the *data-scale* lever.
  Does up-weighting *moving* labs in the decoder loss fix the direction gate?
- **Input:** `data/train_substrate.pkl`, `data/trajectories.pkl`, `data/splits.json`.
- **Process:** same predictor; **delta-aware** lab decoder — loss =
  value-MSE + `ALPHA(=2.0)·Δ-loss`, where Δ-loss is MSE on
  `decode(z_{t+1}) − decode(z_t)` vs the real lab change, up-weighted by `|Δ|` on
  **real remeasurements** (`RMt`). Also retrains outcome head. Evaluated with the
  1-step direction gate on the cardiac TEST split.
- **Output:** `data/world_model_cardiac_delta.pt`, `data/cardiac_delta_metrics.json`.
- **Result (clean NEGATIVE):** predictor still beats persistence (test MSE
  **0.827 vs 1.200**), but the gate did **not** improve — overall **0.549 vs 0.574**,
  abnormal **0.508 vs 0.333**. Conclusion: the objective is **not** the bottleneck →
  the latent simply doesn't carry the movement signal (consistent with T5's 0.49
  ceiling).

### Utilities
- `validate_clmbr.py` — sanity checks on the CLMBR encodings.
- `dump_example_io.py` — writes `data/example_io.json` (a concrete input→output sample).

---

## 4. Artifact map (what each file on disk is)

| File | Produced by | Contents |
|---|---|---|
| `cohort/cohort_v1.parquet` | (upstream cohort build) | cardiac admissions + arm + outcomes |
| `data/mimic_meds/…parquet` | `build_cohort_meds.py` | MEDS event streams for CLMBR |
| `data/trajectories.pkl` | `build_cohort_meds.py` | index-window events, lab values, action_ids, outcomes (**label source**) |
| `data/encoded_states_clmbr.pkl` | CLMBR encode | `{patient_id, s:[T,768], abs_times, outcomes}` |
| `data/splits.json` | `build_split.py` | train 972 / val 140 / test 277 (anti-circularity wall) |
| `data/enriched_actions.pkl` | `build_enriched_actions.py` | per-patient `[T,34]` action matrices |
| `data/action_schema.json` | `build_enriched_actions.py` | 34-dim layout + rate scalers |
| `data/train_substrate.pkl` | `build_train_substrate.py` | **the training file** (windowed + capped) |
| `data/world_model_enriched.pt` | `train_substrate_wm.py` + `add_outcome_decoder.py` | predictor + lab decoder + outcome decoder + scalers |
| `data/world_model_enriched_metrics.json` | `train_substrate_wm.py` | predictor/gate metrics |
| `data/outcome_decoder_metrics.json` | `add_outcome_decoder.py` | mortality AUROC |
| `data/benchmarkB_eval.json` | `eval_simulator_benchmarkB.py` | model-free direction eval |
| `data/lab_decodability.json` | `probe_lab_decodability.py` | per-lab R² (state-design probe) |
| `data/rollout_example.json` | `rollout_counterfactual.py` | one counterfactual demo with bands |
| `data/world_model_cardiac_delta.pt` / `cardiac_delta_metrics.json` | `train_delta_decoder_cardiac.py` | delta-aware ablation |

---

## 5. What's strong, what's lacking, and why

**Strong (defensible today):**
- Predictor **beats persistence** in latent space (0.851 vs 1.229), no overfit.
- **Mortality AUROC 0.864** — the outcome head reads risk cleanly from the latent.
- On the **clinically dynamic subset** (abnormal baseline), the simulator predicts
  lab direction where persistence is at chance (0.512 vs 0.333).
- Clean **anti-circularity** design (one patient-level split reused everywhere).

**Lacking, and the localized reason:**
- **Lab-direction on the full distribution only ties persistence.** Root cause is
  an **information ceiling in the frozen latent**, not the training objective. The
  evidence chain: (1) predictor beats persistence in *latent* space but ties in
  *decoded* space; (2) the probe caps lab-value decodability at **R²≈0.49**; (3) the
  delta-aware objective changed nothing (T6). All three point to "the movement
  signal isn't in `z`."
- **Deconfounding barely bites** (0.703 → 0.685), so counterfactual contrasts
  (the headline use case) aren't yet trustworthy.
- **Action vector misses drivers** (fluids, diet, renal status) → much lab movement
  is unexplained → model defaults to "Stable."

**Highest-leverage fix (structural, not more training):** put the missing
information *into the state* — a **hybrid state** `z ⊕ recent measured labs (LOCF)
⊕ vitals` and predict the **persistence-residual** on raw labs. Then (2) strengthen
the adversary/IPW and validate CF against known causal arrows (insulin→glucose↓),
(3) add vitals/continuous dosing, (4) finish the ICU widening to rule in/out data
scale, (5) add multi-step + calibration eval.
