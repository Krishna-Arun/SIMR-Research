# Version 4 — Chained, Hardened, Agent-Scored Medical-Reasoning Benchmark

Version 4 is a **chained, single-patient** clinical-reasoning benchmark on
**real MIMIC-IV v3.1** data (cardiac-ICU cohort). It asks four questions about
the **same patient in time order** and scores whether the model constructs an
inspectable, patient-specific **causal chain** — not just whether it picks the
right label.

- **What & why:** [SUMMERS_GOAL.md](SUMMERS_GOAL.md)
- **Paper-readiness checklist:** [PAPER_CRITERIA.md](PAPER_CRITERIA.md)

---

## The chained a → b → c → d structure

All four tasks concern one patient, ordered by clinical time around an
**anchor** (the earliest lab-driven ICU intervention):

| Step | Task | Mode | Objective ground truth |
|---|---|---|---|
| **a** | Request + Answer | Agentic, open-ended diagnosis / next-intervention | — (agent-judged) |
| **b** | 72h Lab Trajectory | Predict Rising/Falling/Stable per lab + causal justification | Reference-band rule |
| **c** | Intervention Attribution | Which of two similar patients owns an observed 72h panel | Patient-ID |
| **d** | 1-Year Mortality | Calibrated mortality prediction + risk rationale | Mortality label |

Details, inputs/outputs, and hardening rationale are in
[SUMMERS_GOAL.md](SUMMERS_GOAL.md) §2.

---

## Folder layout

```
Version_4/
├── Longitudinal/         # cohort build + question generation + scoring
│   ├── cohort.py             # cohort construction & inclusion filters
│   ├── context_builder.py    # per-patient longitudinal context
│   ├── outcomes_fix.py       # repaired 30-day readmission / mortality labels
│   ├── orchestrator.py       # question-generation orchestration
│   ├── score_longitudinal.py # scoring entry point
│   ├── longitudinal_contexts.json
│   └── cohort_data/          # parquet tables, splits, balanced_cases.json
├── Benchmark_a/          # agentic Request+Answer infrastructure
│   ├── tools.py              # gate + request tools (no-values gate, Request_*)
│   ├── agentic_loop.py       # model tool-use loop
│   ├── mcp_client.py         # MCP client (PubMed, etc.)
│   ├── optimizer_agent.py    # Mistral Small 3.1 question optimizer
│   ├── evaluator_agent.py    # GPT-OSS-20B evaluator / judge
│   ├── orchestrator.py, backend.py, schema.py, prompts.py, context_builder.py
│   └── MCP_Server/
├── CounterfactualSim/    # JEPA world model + GRPO RL
│   ├── clmbr_encoder.py      # CLMBR latent encoder
│   ├── ac_jepa.py            # AC-JEPA residual predictor (IPW + CRN + μ/logvar)
│   ├── world_model.py, readout.py
│   ├── train_substrate_wm.py # world-model training
│   ├── simulate_server.py    # simulate() exposed as MCP tool
│   ├── rl_env/               # GRPO environment (chain rubric = reward)
│   ├── checkpoints/, embeddings/
└── docs/                 # this documentation
```

---

## How to run each stage

> Paths below are relative to `Version_4/`. Inspect each script's arguments
> before running; the world-model / GRPO stages require a GPU.

### 1. Build the cohort & labels
```
python Longitudinal/cohort.py          # apply inclusion filters, define anchors
python Longitudinal/outcomes_fix.py    # re-derive readmission/mortality labels
python Longitudinal/context_builder.py # build per-patient longitudinal contexts
```
Produces the cohort index, splits, and
[balanced_cases.json](../Longitudinal/cohort_data/balanced_cases.json).

### 2. Generate questions (Evaluator-Optimizer)
```
python Longitudinal/orchestrator.py    # Optimizer=Mistral Small 3.1,
                                       # Evaluator=GPT-OSS-20B, PubMed MCP
```

### 3. Run Benchmark a (agentic)
```
python Benchmark_a/orchestrator.py     # drives agentic_loop + MCP tools
```

### 4. Train / serve the world model, then GRPO
```
python CounterfactualSim/train_substrate_wm.py   # train AC-JEPA world model (GPU)
python CounterfactualSim/simulate_server.py      # serve simulate() as MCP tool
# GRPO fine-tuning runs from CounterfactualSim/rl_env/ (GPU cluster)
```

### 5. Score
```
python Longitudinal/score_longitudinal.py
```
Objective components (b directions, c patient-ID, d label) are graded against
deterministic ground truth; subjective components go to the evaluator agent on
the 0 / 0.5 / 1 rubric.

---

## Honest limitations

- **Small cohort.** 494 cardiac-ICU stays (471 CLMBR-encoded; test split of
  97; balanced eval set of 100 cases). Real but small — results should be read
  as a focused cardiac-ICU study, not a population-scale claim.
- **Agent-judged subjective scoring.** Causal-justification, request-quality,
  and open-answer dimensions are graded by an LLM (GPT-OSS-20B). This is
  mitigated by ≥3 judge runs, a second judge model, Cronbach's α / κ reporting,
  and a ~20-item human-rated subset — but those reliability numbers are **not
  yet collected**, and LLM judging remains a source of noise.
- **GRPO deferred to GPU cluster.** The reinforcement fine-tuning stage
  (`+sim(GRPO)` arm) has not been run here; the world model is trained and the
  ablation is designed, but the LLM-lift result is pending.
- **Rollout direction drift.** The world model's multi-step counterfactual
  rollouts can drift in direction over the horizon; predictions are most
  reliable near the anchor and degrade further out.
- **Difficulty target unconfirmed.** The v4 hardening is designed to push
  scores below 20% full-credit, but the v4 model scores confirming this have
  not yet been measured (v3 baselines: gemma 0.675, qwen 0.660, llama 0.607).
