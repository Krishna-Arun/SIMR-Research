# H100 Run Plan — Benchmark A / B / C (cardiovascular)

What to run on the rented H100, which models, and how. Two phases: **(1) question generation**
(this is what the queued job does) and **(2) agent benchmarking with/without PubMed** (next build).

> All work stays on `$SCRATCH` (MIMIC DUA — no cloud GPUs, no data leaving Sherlock). The H100 must
> be a Sherlock `gpu`-partition allocation (`-C GPU_SKU:H100_SXM5`), not a cloud rental.

## Current allocation
- Job **31709531** queued: `-p gpu -C GPU_SKU:H100_SXM5 -G 1 -c 16 --mem=128GB -t 1-00:00:00`.
- On start it runs `h100_session/run_h100.sh`: per benchmark → ensure cohort → **self-check (3 Q)** → **full run (500 Q)**. Writes `h100_session/H100_READY` with node + jobid.

## Models

### Default (fits 1× H100 80 GB, fp16, no quantization) — what the job uses now
| Role | Model | ~VRAM (fp16) |
|---|---|---|
| Optimizer (drafts/refines) | `Qwen/Qwen2.5-14B-Instruct` | ~30 GB |
| Evaluator (4-dim critique) | `deepseek-ai/DeepSeek-R1-Distill-Qwen-14B` | ~30 GB |

Both load concurrently (~60 GB + KV) via the HF-transformers backend. Robust on el7 — **no vLLM, no
bitsandbytes** (both are broken in this env: vLLM-latest pins a nonexistent torch; bitsandbytes wheels
cap at 0.42 and fail CUDA setup).

### To use the originally-specced large models — needs MORE than 1 H100
| Role | Spec model | Fit |
|---|---|---|
| Optimizer | Mixtral-8x22B-Instruct (141B) | fp16 ~280 GB → **4× H100**; or AWQ ~80 GB → 1–2× H100 |
| Evaluator | DeepSeek-R1-Distill-Qwen-32B | fp16 ~64 GB → 1× H100 |
| Scorer (Benchmark run) | Llama-3.3-70B-Instruct | fp16 ~140 GB → **2× H100**; or AWQ ~40 GB → 1× H100 |

To run these you must **(a) request 2–4× H100** (`-G 4`) and **(b) install a torch-2.6-compatible vLLM
on the H100 node** (H100 = sm_90 supports vLLM AWQ/FP8 natively — no bitsandbytes needed), then set each
role's `config/qgen.yaml` to `backend: vllm` with `tensor_parallel_size`/`quantization: awq`. The code
already supports `backend: vllm` (`qgen/vllm_backend.py`) and serving (`jobs/serve_models.sbatch`,
`qgen/serve_cmd.py`).

**Recommendation:** start the generation now with the 14B fp16 pair (good quality, guaranteed to run);
upgrade to 32B evaluator + Mixtral/AWQ optimizer on a 2–4× H100 allocation if you want max quality for
the final dataset.

## Phase 1 — Question generation (the queued job)
Per benchmark, full budgets (`config/qgen.yaml`): `max_iterations: 3`, `max_tool_calls_per_agent: 6`,
`target_n: 500`. Each question is anchored to a real **cardiovascular** patient.
- **A** (`Benchmark_A/Question_Generation`): lab/micro-requesting + causal diagnosis/intervention.
- **B** (`Benchmark_B/...`): post-procedure trajectory (Rising/Falling/Stable) + causal justification.
- **C** (`Benchmark_C/...`): counterfactual intervention identification on overlap-matched patient pairs.

Outputs → each benchmark's `outputs/questions.jsonl` (+ `run_manifest.json`). Resumable (append-only).

Manual run (if not using the auto job), inside the allocation:
```bash
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export HF_HOME=$SCRATCH/.huggingface
cd /scratch/users/karun09/Version_2/Benchmark_A/Question_Generation
PYTHONPATH=$PWD $PY -m qgen.run_generate config/qgen.yaml --target 500
# repeat for Benchmark_B, Benchmark_C
```

### Requirements on the H100 node
- SIMR conda env: `/scratch/users/karun09/miniforge3/envs/simr` (torch 2.6 cu124, transformers, pandas, sklearn).
- **Outbound internet** for PubMed (NCBI E-utilities). Verify with `curl -sI https://eutils.ncbi.nlm.nih.gov`.
- Optional `export NCBI_API_KEY=...` before sbatch → raises PubMed rate limit 3→10 req/s (recommended for 1500 questions × agentic tool calls).
- PubMed MCP server auto-started by `run_generate` (Node 25.3.0, already built).

### Rough time estimate (1× H100, 14B pair)
~10–40 s per agentic generation; ~6–12 generations per question. ≈ **1–4 min/question** → 500 ≈ **10–30 h**
for all three. If tight on the 24 h wall, lower `target_n`, or use 2× H100 to parallelize benchmarks.

## Phase 2 — Agent benchmarking, with vs without PubMed (next to build)
Not built yet. The harness will, for each generated question:
1. Run the **agent under test** twice — **with** PubMed MCP and **without** — using the benchmark tools
   (A: `request_all_labs_no_values`→`request_a_lab`; B: predict trajectories; C: pick the patient).
2. Score against the answer keys:
   - **A**: lab-request 0/0.5/1 + answer 0/0.5/1 (judge = **Llama-3.3-70B**).
   - **B**: per-lab 1 / 0.5 (non-stable→stable) / 0; + **ECE** (stated confidence vs activation-prob over {Rising,Falling,Stable}).
   - **C**: 0/1 correct patient; + **ECE** (confidence vs activation-prob over {A,B}).
3. Report the **with-vs-without-PubMed delta** (the headline result).

## Checklist before launching the full run
- [ ] Decide model tier (14B fp16 default vs big models on 2–4× H100).
- [ ] `NCBI_API_KEY` exported (optional but recommended).
- [ ] Confirm node internet for PubMed.
- [ ] Confirm cohorts present (`outputs/pool.parquet` in A/B/C) — already built (CV).
