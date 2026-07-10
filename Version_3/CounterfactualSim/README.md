# CounterfactualSim — Counterfactual-Simulation Engine

A latent **world model** that lets an LLM ask "what happens to this patient if I intervene?"
It encodes a patient's state timeline, rolls that latent forward under a chosen
intervention, and decodes the result into interpretable predictions. The engine is exposed
to the answering LLM as a `simulate()` MCP tool, and the SIMR longitudinal benchmark
(`../Longitudinal/`) is used as a **GRPO reinforcement-learning environment** to fine-tune
open LLMs to reason with those simulated interventions.

## Purpose / pipeline

```
patient event timeline
        │
        ▼
┌───────────────────┐   CLMBR-t-base (141M autoregressive EHR foundation model)
│  clmbr_encoder.py │   encodes the OMOP/MEDS timeline → per-timestep state embeddings
└───────────────────┘   z_1 … z_T   [T, 768]
        │
        ▼
┌───────────────────┐   V-JEPA2-style ACTION-CONDITIONED predictor (adapted to 1-D time).
│   world_model.py  │   Prepends an intervention (action) token to each step, causal-attends,
└───────────────────┘   and autoregressively rolls the latent forward under the chosen arm.
        │  z_hat (predicted future latent)
        ▼
┌───────────────────┐   decode latent → per-core-lab direction (Rising/Falling/Stable) +
│    readout.py     │   value estimate, and outcome-risk (mortality_1y / readmission_30d).
└───────────────────┘
        │  interpretable prediction
        ▼
┌───────────────────┐   MCP stdio server exposing simulate(patient_id, intervention).
│ simulate_server.py│   The answering LLM calls this as a TOOL during the benchmark.
└───────────────────┘
        │
        ▼
┌───────────────────┐   TRL GRPOTrainer: rollout = LLM answers a longitudinal case with
│      rl_env/      │   simulate() available; REWARD = benchmark rubric score
└───────────────────┘   (../Longitudinal/score_longitudinal.py).
```

**Ablation (the experiment):** three arms scored on the A/B/C longitudinal rubrics —
`vanilla` (LLM alone) / `+sim(base)` (LLM + untrained-or-base simulate tool) /
`+sim(GRPO)` (LLM fine-tuned with GRPO against the reward).

## Module map

| File | Role | Runs locally? |
|------|------|---------------|
| `clmbr_encoder.py` | Wraps `StanfordShahLab/clmbr-t-base` to turn a patient timeline into `[T, 768]` state embeddings. `backend='clmbr'` = real (cluster); `backend='fallback'` = deterministic hash embedding so downstream code runs without CLMBR. | fallback: yes / clmbr: cluster |
| `world_model.py` | `ActionConditionedWorldModel` (V-JEPA2 AC-predictor adapted to a 1-D temporal, time-causal sequence), `EMATeacher`, `jepa_loss`, `build_action_vector`. Autoregressive `rollout()`. | yes (needs torch) |
| `readout.py` | `ReadoutHeads` — decodes a predicted latent into per-core-lab direction logits + value, and mortality/readmission risk. `decode()` returns the human-readable dict for `simulate()`. | yes (needs torch) |
| `train_worldmodel.py` | Cluster training entry (SLURM-ready). `--smoke` trains a few steps on synthetic tensors to verify wiring. Real run = CLMBR-encoded cohort trajectories, JEPA loss + supervised readout heads. | smoke: yes / real: cluster |
| `simulate_server.py` | MCP stdio JSON-RPC server (same protocol as `../Benchmark_A/MCP_Server/server.py`). `trained` backend if `$CFSIM_CKPT` + torch present; else a clearly-labeled `heuristic` (physiology-prior) backend so the RL env can run untrained. | yes (heuristic) |
| `rl_env/` | TRL `GRPOTrainer` scaffold. **Currently a stub (`__init__.py` only).** Planned: `train_grpo.py` (cluster GRPO entry) and `ablation.py` (runs the 3 arms and scores them via `score_longitudinal.py`). | cluster |

## Data flow

1. **Encode** — `CLMBREncoder.encode(timeline)` → `[T, 768]` state embeddings.
2. **Act** — `build_action_vector(family, extra)` builds the per-step intervention vector
   (one-hot over `none/dialysis/transfusion/ventilation` + dose/flow features).
3. **Roll** — `world_model.rollout(z0, action_seq)` → predicted future latents `[B, K, 768]`.
4. **Decode** — `ReadoutHeads.decode(z_hat)` → `{predicted_lab_directions, mortality_1y_risk, readmission_30d_risk}`.
5. **Serve** — `simulate_server.py` wraps steps 1–4 behind the `simulate()` MCP tool.
6. **Reward** — in `rl_env/`, the LLM's answers are scored by
   `../Longitudinal/score_longitudinal.py`; that scalar is the GRPO reward.

## Assets already present locally

- **CLMBR weights** — `../loaded_models/clmbr-t-base/` (`model.safetensors`, `config.json`,
  `dictionary.msgpack`, `clmbr_v8_original_dictionary.json`). Hidden size 768.
- **OMOP vocabulary** — `../../vocabulary_download_v5_{...}/CONCEPT.csv` (Athena download;
  `clmbr_encoder.py` auto-discovers the newest `vocabulary_download_v5_*`).

## SCAFFOLD vs TODO(cluster)

Everything here is a runnable **scaffold**. What is genuinely local vs deferred to the
H100/L40S cluster:

**Runs locally (SCAFFOLD, verified via `__main__`/`--smoke`):**
- `world_model.py`, `readout.py` forward/rollout/decode on synthetic tensors.
- `train_worldmodel.py --smoke` (tiny synthetic train loop, saves a smoke checkpoint).
- `clmbr_encoder.py` with the **fallback** hash encoder (no CLMBR, no OMOP needed).
- `simulate_server.py` with the **heuristic** backend (physiology priors, no torch).

**TODO(cluster) — the real path:**
- **MIMIC-IV → OMOP-CDM → MEDS** conversion for the cohort (the heaviest dependency;
  needs the concept crosswalks in `CONCEPT.csv` + `femr`/`meds_reader`). Until this exists
  the fallback encoder stands in. Marked `TODO(cluster)` in `clmbr_encoder._encode_clmbr`.
- **Real CLMBR forward pass** (`CLMBREncoder(backend='clmbr')`) — needs `femr` (cluster-only).
- **World-model training** (`train_worldmodel.train_real`) — CLMBR-encoded cohort
  trajectories, JEPA + readout objectives, DDP/AMP over the train split.
- **Trained `simulate()` backend** — `simulate_server._load_engine` reconstructs
  encoder+world_model+readout from `$CFSIM_CKPT` (`TODO(cluster)`).
- **GRPO fine-tuning + ablations** (`rl_env/train_grpo.py`, `rl_env/ablation.py`) — TRL
  `GRPOTrainer` with `simulate()` available; reward = benchmark rubric.

## Local smoke checks

```bash
# 1. fallback encoder: timeline -> state embeddings, confirms weights/vocab discovered
python clmbr_encoder.py

# 2. world model: forward + autoregressive rollout on synthetic tensors
python world_model.py

# 3. readout heads: decode a latent -> interpretable prediction
python readout.py

# 4. tiny synthetic training loop (saves checkpoints/worldmodel_smoke.pt)
python train_worldmodel.py --smoke

# 5. compile everything
python -m py_compile *.py rl_env/*.py

# 6. simulate() over MCP (heuristic backend) — drive with the Benchmark_A mcp_client,
#    or pipe JSON-RPC lines directly:
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"simulate","arguments":{"patient_id":"demo","intervention":"dialysis"}}}' \
  | python simulate_server.py
```

**Planned (once `rl_env/` is built):** `python rl_env/ablation.py --dry-run` runs the
`vanilla` arm on a few local questions and emits scores (no training, no GPU). GRPO training
(`rl_env/train_grpo.py`) is a cluster job.

## Honest status

- The **architecture and interfaces are complete and local-runnable**; the **weights are
  untrained**. `simulate()` returns physiology-prior heuristics until a checkpoint exists.
- The single biggest blocker to the real engine is the **MIMIC→OMOP→MEDS + CLMBR** pipeline,
  which is deliberately isolated behind `CLMBREncoder` so nothing downstream is blocked on it.
- `rl_env/` is currently a stub (`__init__.py`); `train_grpo.py` / `ablation.py` are the next
  files to add before the GRPO/ablation phase.
