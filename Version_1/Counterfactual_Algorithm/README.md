# Counterfactual_Algorithm — MIMIC-IV Latent World Model · Simulator · Benchmark · Offline RL

A **research environment** for intervention-conditioned patient-trajectory modeling on MIMIC-IV.
One core artifact — a **latent world model of patient dynamics** — drives three outputs: a
**simulator** (rollouts under interventions), a **counterfactual/stability benchmark**, and a
**Gym-style offline-RL environment**.

> ⚠️ **NOT a clinical tool.** All rollouts are *learned simulations from observational data*. The
> system does **not** recover true causal effects and makes **no** counterfactual-validity claims.
> Offline RL trains **inside the learned simulator only** — never a deployment claim. Metrics target
> stability / consistency / calibration, not clinical benefit.

## Pipeline & status (validated end-to-end on the MIMIC-IV demo, 100 patients)

| Stage | Script | Status | Headline result |
|------|--------|--------|-----------------|
| 0 · CLMBR smoke | `notebooks/clmbr_smoke.ipynb` | ✅ | clmbr-t-base (FEMRModel) loads + runs → **(3, 768)** representations |
| 1 · Preprocess | `preprocessing/build_trajectories.py` | ✅ | 100 patients, 107,752 events; action vocab (PCI/CABG/vasopressor/…) |
| 2a · Encoder (GRU) | `training/train_encoder.py` | ✅ | next-event val NLL 7.88 → 5.36; 256-d states |
| 2b · Encoder (CLMBR) | `models/encode_clmbr.py` | 🟡 wired+validated to the ontology step; **needs Athena vocab** | MIMIC→MEDS ✅, nested-schema ✅, 768-d frozen clmbr-t-base |
| 3 · World model | `training/train_world_model.py` | ✅ | val MSE **0.00637 < persistence 0.01038** |
| 4 · Simulator | `simulation/rollout.py` | ✅ | branching + counterfactual-pair rollouts |
| 5 · Benchmark | `benchmark/intervention_tests.py` | ✅ | swap-div 8.16; stability smooth; 128-step stable |
| 6 · Offline RL | `training/train_agent.py` | ✅ | BC return **3.74** > random 3.02 (≈ no-op 3.71) |

Outputs land in `data/` (artifacts) and `outputs/` (`benchmark_results.json`, `agent_results.json`).

## Architecture

```
events (MIMIC-IV)
   │  preprocessing/  → per-patient chronological trajectories + grouped action vocab a_t
   ▼
ENCODER  models/encoder.py     s_t = encoder(x_≤t)         [EncoderBase]
   ├─ GRUEncoder       from-scratch CLMBR-style next-event SSL (default, 256-d) ── runs anywhere
   └─ CLMBRFemrEncoder frozen StanfordShahLab/clmbr-t-base via femr (768-d) ───── target encoder
   ▼
WORLD MODEL  models/world_model.py   s_{t+1} = f(s_t, a_t, Δt)   (deterministic | gaussian | mdn)
   ▼
SIMULATOR  simulation/rollout.py     rollout / branch / counterfactual_pair
   ├─► BENCHMARK  benchmark/{intervention_tests,metrics}.py   (Tasks 1–4)
   └─► RL ENV     rl_env/mimic_env.py + training/train_agent.py  (BC now, CQL scaffold)
DECODER  models/decoder.py   s_t → proxy outcomes (mortality / ICU / LOS) for reward + divergence
```

Swapping GRU↔CLMBR is a config switch (`encoder.kind: gru | clmbr`); everything downstream reads the
latent dim from config.

## Environment (Sherlock, el7 / glibc 2.17)

Two `$SCRATCH` venvs built with **`uv`** on a self-contained CPython 3.11 (femr 0.2.3 needs py>3.9;
torch 2.1.2 has no cp312 wheel; the cluster ships only py 3.6/3.9/3.12/3.14):

- `envs/cfa311` — lean torch-only env for the **GRU pipeline** (torch 2.1.2 + numpy/pandas/pyyaml).
- `envs/clmbr311` — heavy **CLMBR** env (`torch==2.1.2 femr==0.2.3 datasets==2.15.0
  xformers==0.0.23.post1 transformers==4.35.2`), with `pyarrow/pyzmq/scipy/scikit-learn` pinned to
  el7-compatible wheel versions to avoid Rust/OpenBLAS source builds.

## How to run

```bash
PY=$SCRATCH/Counterfactual_Algorithm/envs/cfa311/bin/python
export PYTHONPATH=$PWD
$PY preprocessing/build_trajectories.py configs/default.yaml   # Stage 1 (or jobs/preprocess.sbatch)
$PY training/train_encoder.py        configs/default.yaml      # Stage 2a
$PY training/train_world_model.py    configs/default.yaml      # Stage 3
$PY benchmark/intervention_tests.py  configs/default.yaml      # Stage 5
$PY training/train_agent.py          configs/default.yaml      # Stage 6
```
Slurm templates live in `jobs/` (public `gpu`/`dev` partitions). Config: `configs/default.yaml`.

### Real-CLMBR path (Stage 2b) — once the Athena vocab is in place

```bash
# in the clmbr311 venv:
python preprocessing/build_meds.py   configs/default.yaml   # MIMIC-IV -> MEDS (done; Athena-free)
python models/encode_clmbr.py        configs/default.yaml   # frozen CLMBR + Athena -> encoded_states_clmbr.pkl
# then flip encoder.kind: clmbr in the config and rerun the SAME downstream stages:
python training/train_world_model.py configs/default.yaml   # auto-loads CLMBR (768-d) states
python benchmark/intervention_tests.py configs/default.yaml
python training/train_agent.py       configs/default.yaml
```
`utils.common.states_path()` switches `encoded_states.pkl` (GRU) ↔ `encoded_states_clmbr.pkl` (CLMBR)
by `encoder.kind`, so nothing downstream changes. Or submit `jobs/encode_clmbr.sbatch`.

## Blockers (user action)

1. **Gated CLMBR model.** Request access at <https://huggingface.co/StanfordShahLab/clmbr-t-base>,
   then authenticate (`hf auth login`, or set `HF_TOKEN`). Re-run `jobs/clmbr_smoke.sbatch` (or the
   notebook) to validate; then set `encoder.kind: clmbr`.
2. **Athena OMOP vocabulary** (for CLMBR tokenization of MIMIC) — manual OHDSI download; see
   `preprocessing/to_meds.py`. The GRU path needs neither blocker.
3. **Full MIMIC-IV v3.1** is incompletely downloaded (only admissions + diagnoses_icd); demo is used
   for now. Set `data.source: full` once the download completes.
```
