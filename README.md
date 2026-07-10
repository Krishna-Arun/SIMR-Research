# SIMR-Research

Clinical-reasoning benchmark and simulation research, organized by iteration.

## Repository structure

| Folder | Description |
|--------|-------------|
| `Version_1/` | Initial work: kidney/AKI + cardiac benchmarks, PubMed & kidney MCP servers, species benchmark, EHR exploration. |
| `Version_2/` | Benchmarks A/B/C question generation, H100/L40S run sessions, Ollama setup, dashboard. |
| `Version_3/` | SIMR clinical-reasoning benchmarks A/B/C, counterfactual simulation, longitudinal modeling. |
| `Version_4/` | Current iteration: Benchmark_a, CounterfactualSim, Longitudinal, and paper docs. |
| `datasets/` | Local datasets (MIMIC-IV, PhysioNet, OMOP vocab). **Gitignored — never pushed.** |

## Branches

- `main` — clean/empty baseline.
- `local-dev` — active local development (this organized tree).
- `sherlock` — Sherlock server work.
- `v1` — snapshot of the original repository history.

## Datasets

Credentialed datasets (MIMIC-IV, PhysioNet, EHRSHOT, OMOP vocabulary) live under
`datasets/` and are **excluded from version control**. Obtain them from their
official sources and place them there locally.
