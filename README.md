# SIMR-Research

Research code for LLM causal-reasoning benchmarks and counterfactual clinical
world-modeling on MIMIC-IV, developed on the Stanford Sherlock HPC cluster.

> **Repo root = `$SCRATCH` (`/scratch/users/karun09`).** Only source code, docs,
> configs, and small research artifacts are tracked. All datasets, model
> weights, virtual environments, caches, and credentialed data are **git-ignored**
> (see [`.gitignore`](.gitignore)) and must be regenerated or re-downloaded — they
> are **not** in version control.

## Layout

| Path | Contents |
|------|----------|
| `Version_1/` | Early causal-intervention benchmarks and world-model prototypes: `causal_benchmark_v2/`, `causal_benchmark_v3/`, `CARDIAC_COUNTERFACTUAL/`, `Counterfactual_Algorithm/`, `MIMIC_WORLD_MODEL/`. |
| `Version_2/` | Current SIMR framework: `Benchmark_A/`, `Benchmark_B/`, `Benchmark_C/` (question generation), `counterfactual_simulation/` (CLMBR world model + LLM coupling), `Eval/` (multi-model evaluation), `scripts/`, `docs/`. |
| `Version_3/` | Next-iteration smoke tests and readiness checks. |

## Excluded from git (must be provided locally)

These live under `$SCRATCH` but are intentionally **not** committed:

- **Credentialed data** — `physionet.org/`, `**/mimiciv*/` (MIMIC-IV; requires a
  PhysioNet data use agreement — never redistribute).
- **Vocabularies** — `**/vocab_data/`, `**/vocabulary_download*/`, Athena/OMOP
  `CONCEPT*.csv`.
- **Model weights** — `loaded_models/` (symlinks) and the `.huggingface/` hub;
  re-download with `hf download <repo-id>`.
- **Environments & caches** — `miniforge3/`, `.conda/`, `.cache/`, `.pip*/`,
  `**/envs/`, etc.
- **Serialized data** — `*.pkl`, `*.parquet`, `*.npy`, `*.csv`, container `*.sif`.
- **Secrets** — `.hf_token`, `.env` (never commit).

## Environment notes

- Runs on Sherlock; submit all compute through Slurm (`*.sbatch` files), never on
  the login node.
- GPU work uses the public `gpu`/`dev` partitions.
- See per-version `docs/` and `README`s for pipeline-specific instructions.
