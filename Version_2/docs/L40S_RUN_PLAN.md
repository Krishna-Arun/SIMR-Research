# L40S Run Plan — Benchmark A / B / C question generation (cardiovascular)

Supersedes `H100_RUN_PLAN.md` (H100 kept only as the big-model option). Operating manual:
`l40s_session/MANUAL.md`. All work stays on `$SCRATCH` (MIMIC DUA — Sherlock only).

## Hardware & partition
- **Partition: `gpu`** (public). Card: **`-C GPU_SKU:L40S`** (48 GB Ada). Count: **`-G 4`** recommended
  (`-G 3` works but tight). Why L40S over H100: ~8 L40S nodes have free GPUs now vs ~19 jobs queued for
  the 3 H100 nodes.

## Models (downgraded to the ~32B tier so they fit L40S)
| Role | Model | params | ~fp16 |
|---|---|---|---|
| Optimizer | `Qwen/Qwen2.5-32B-Instruct` | 32B | ~64 GB |
| Evaluator | `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` | 32B | ~64 GB |

Both open (no gating), run via the **HF-transformers backend** (vLLM/bitsandbytes are broken in this
el7 env). They load **concurrently, sharded across the L40S cards** via `device_map="auto"` with a
`max_memory_per_gpu: 22GiB` cap (set in each `config/qgen.yaml`) so the two models coexist.

### Fit math
- 2× 32B ≈ 128 GB. On **4× L40S = 192 GB** → ~64 GB headroom for KV cache (comfortable).
  On **3× L40S = 144 GB** → ~16 GB headroom (tight; OOM-risk under long context).
- Fallback if tight: set evaluator → `DeepSeek-R1-Distill-Qwen-14B` (one line) → ~94 GB total, fits 3× easily.

### Performance caveat
HF multi-GPU is **naive model parallelism** (layers split; one card active at a time) → enables the big
models but is **not faster** per token. Efficient multi-GPU (tensor parallel, all cards at once) needs
**vLLM**, which isn't installed. So expect ~1–4 min/question; 500×3 ≈ 1 day on one allocation.

## What runs (Phase 1 — generation)
Per benchmark, full budgets (`config/qgen.yaml`): `target_n=500`, `max_iterations=3`,
`max_tool_calls_per_agent=6`; cohort = `cardiovascular_primary`. Cohorts already built (CV):
- A: ICU+micro+CV pool (5,000). B: therapeutic-procedure+CV pool (5,000). C: 8,056 overlap-matched pairs.
Outputs → `Benchmark_{A,B,C}/Question_Generation/outputs/questions.jsonl` (+ manifest). Resumable.

Order of operations (see MANUAL.md): `salloc` → `smoke_l40s.sh 10` (validate) → `run_l40s.sh 500` (full).

## Phase 2 — Agent benchmarking, with vs without PubMed (next build)
Not built yet. For each generated question, run the agent **with** and **without** the PubMed MCP server,
score against the answer keys (A: lab-request 0/0.5/1 + answer 0/0.5/1; B: direction 1/0.5/0 + ECE;
C: 0/1 + ECE), and report the **with-vs-without-PubMed delta**. A ~32B judge (e.g. Qwen2.5-32B-Instruct)
replaces the originally-specced Llama-3.3-70B scorer to stay within L40S.

## Scaling to the original big models (Mixtral-8x22B / Llama-70B)
Not possible on L40S in fp16. Requires the **H100** (or multi-H100) **plus** a working **vLLM + AWQ**
build (H100=sm_90 supports AWQ/FP8 natively). The code already supports `backend: vllm`
(`qgen/vllm_backend.py`, `qgen/serve_cmd.py`, `jobs/serve_models.sbatch`) — only the vLLM install +
config switch remain. Keep this as the "max-quality final dataset" path.

## Pre-flight checklist
- [ ] `salloc -p gpu -C GPU_SKU:L40S -G 4 -c 16 --mem=128GB -t 1-00:00:00`
- [ ] `nvidia-smi` shows 4× L40S
- [ ] (opt) `export NCBI_API_KEY=...`; confirm node internet for PubMed
- [ ] `smoke_l40s.sh 10` → inspect sample records → `run_l40s.sh 500`
