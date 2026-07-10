# Longitudinal — Single-Patient Clinical-Reasoning Benchmark (MTBBench-style)

A longitudinal benchmark that chains **four questions on the SAME patient**, in time order,
anchored on a lab-driven ICU intervention *P* (at time *tP*):

```
A1  next intervention      →  C  attribution        →  B  72h trajectory   →  A2  outcome
(at ICU intime, predict    (two REAL patients, same  (given P, predict     (at discharge,
 P's family from labs)      baseline, diff families;  each core lab's       mortality_1y /
                            which one got which)      Rising/Falling/Stable) readmission_30d)
```

The per-step rubric score is aggregated into a single longitudinal score, which doubles as
the **RL reward** for the CounterfactualSim GRPO environment (`../CounterfactualSim/`).

## Cohort — CARDIAC-restricted ICU

The cohort is now **restricted to cardiac patients**. Patient/admission IDs come from the
`mimic-iv-ext-cardiac-disease-1.0.0` dataset (`heart_*` files — union of `hadm_id` across
`heart_diagnoses_all.csv`, `heart_procedures.csv`, `heart_diagnoses.csv`), and full clinical
data is pulled from real **MIMIC-IV v3.1** under `../../2physionet.org/files/mimiciv/3.1`.

**Reference inclusion filters** (applied per admission):
- **alive at time-zero** — no `deathtime`/`dod` at or before the anchor time
- **ICU-only** — the anchor intervention occurred within an ICU stay
- **dense labs** — **≥ 20 distinct lab itemids** AND **≥ 50 total lab measurements** per admission
- plus **≥ 2 labs pre-anchor and ≥ 2 within 72h post-anchor** (needed for the B trajectory step)

**Anchor families** (the "arms"), lab-driven:
- `dialysis` / `ventilation` — from `icu/procedureevents` by label keyword
- `transfusion` — from `icu/inputevents` RBC itemids `{225168, 220996}` (not in procedureevents)

One anchor per ICU stay (earliest; priority dialysis > transfusion > ventilation).

### Current cohort stats

- **494 cardiac ICU stays** — **49 dialysis / 88 transfusion / 357 ventilation**
- **dense labs** — min **25** distinct itemids, median **78** per admission
- **patient-level split** (stratified by anchor family, no subject across splits):
  **train 328 / val 46 / test 97** subjects

> The heavy **ventilation skew reflects the real cardiac-ICU population** (most cardiac ICU
> patients are ventilated; dialysis/transfusion are comparatively rare). It is not a sampling
> artifact. The C step is the scarcest to build because it needs **similar-baseline,
> different-family** pairs (see below).

## Modules

### `cohort.py` — build the eligible cohort + split
Cohort-first design (labevents is 2.4 GB / ~150M rows and is **never loaded whole**):
1. `icustays` + `procedureevents`/`inputevents` → candidate stays with a lab-driven anchor,
   **restricted to the cardiac-ext `hadm_id` universe** (which also shrinks the labevents scan).
2. Bound to a family-balanced candidate pool.
3. **One chunked pass** over `hosp/labevents` keeping only candidate `hadm_id`s.
4. Apply the reference inclusion filters (density + alive@t0 + pre/post anchor labs).
5. Materialize per-cohort parquet slices (labs, procedures, dx, admissions, patients,
   micro, dictionaries) + `cohort_index.json`.
6. Emit **`cohort_split.json`** — patient-level train/val/test, stratified by anchor family,
   asserting no `subject_id` leaks across splits.

Outputs → `cohort_data/`. Prints family mix, lab-density distribution, split sizes.

### `context_builder.py` — the A1/C/B/A2 data spine
Reads `cohort_data/` and computes the **ground-truth structure** (no models) for each stay:
- **A1** — time-zero = ICU intime; answer = anchor family; golden = the abnormal decisive
  family lab (Creatinine/K/Urea for dialysis, Hgb/Hct for transfusion, pCO2/pH/pO2 for vent).
- **C** — attached by cross-patient pairing: each patient is greedily matched to a **real**
  cohort partner of a **different family** with the **closest baseline** (z-scored core labs,
  ≥ 3 shared labs, distance ≤ `MAX_PRESTATE_DIST`). Ground-truth answer balanced A/B.
- **B** — per-core-lab direction over 72h via a reference-range band rule (Rising/Falling/Stable).
- **A2** — time-zero = discharge; labels `mortality_1y` and `readmission_30d`.

Output → `longitudinal_contexts.json`.

> **C pairs are limited** by the need for similar-baseline, different-family patients — with
> the ventilation-heavy cardiac cohort, dialysis/transfusion partners are the binding constraint.

### `orchestrator.py` — build longitudinal case records
Turns each context's data spine into one case record (four chained questions) plus a
**leak-safe answering view** per step (every answer key stripped). Two modes:
- `--dry-run` — **no models**; synthesizes each step's framing from the data spine. Fast; use
  to verify wiring and zero answer leakage.
- **real** — 2-agent authoring (Mistral optimizer + GPT-OSS evaluator via the Ollama backend
  reused from `../Benchmark_A/Question_Gen`); the optimizer rewrites each stem into a richer
  vignette. Slow (4 steps × n patients). Prefers train-split subjects if `cohort_split.json` exists.

Outputs → `outputs/longitudinal.jsonl` + `outputs/answering/*.json`.

### `score_longitudinal.py` — the RL reward
Grades an agent's answers against the keys, per step, and aggregates:
- **A1 / A2** — multiple-choice: 1 exact / 0.5 partial overlap / 0.
- **C** — 1 if the chosen patient matches, else 0.
- **B** — per-target direction: 1 correct / 0.5 (true direction predicted Stable) / 0 opposite;
  averaged over targets.
- **total** = mean over answered steps, in `[0, 1]`. This scalar is the GRPO reward.

## Run

```bash
# 1. build the cardiac cohort + slices + split (chunked MIMIC-IV scan; slow, one-time)
python cohort.py

# 2. compute the A1/C/B/A2 data spine + C pairings
python context_builder.py

# 3a. fast wiring / leak-safety check (no models)
python orchestrator.py --dry-run --n 3

# 3b. real 2-agent authoring (slow; needs Ollama)
SIMR_BACKEND=ollama python orchestrator.py --n 3

# 4. self-test the scorer / RL reward
python score_longitudinal.py
```

Data roots (relative to this directory):
- MIMIC-IV v3.1 — `../../2physionet.org/files/mimiciv/3.1`
- cardiac-ext IDs — `../../mimic-iv-ext-cardiac-disease-1.0.0`
