# MANUAL — Running Benchmark A/B/C question generation on L40S

Everything is on `$SCRATCH` (MIMIC DUA — must stay on Sherlock). Models: **Qwen2.5-32B-Instruct**
(optimizer) + **DeepSeek-R1-Distill-Qwen-32B** (evaluator), fp16, HF backend, split across the L40S
cards. **Partition = `gpu`**, card = `-C GPU_SKU:L40S`.

## 0. GPU count
- **Recommended: `-G 4`** (4× L40S = 192 GB) — comfortable for the two 32B models + KV cache.
- `-G 3` (144 GB) works but is **tight**; if you hit CUDA OOM, use 4, or set the evaluator to the 14B
  distill (one line in each `config/qgen.yaml`).

## 1. Get the allocation (interactive)
```bash
salloc -p gpu -C GPU_SKU:L40S -G 4 -c 16 --mem=128GB -t 1-00:00:00
# when it lands you're on the node; confirm the GPUs:
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader   # expect 4x L40S, 46068 MiB each
```
(Optional, higher PubMed rate limit:) `export NCBI_API_KEY=<your_key>`
Check the node has internet for PubMed: `curl -sI https://eutils.ncbi.nlm.nih.gov | head -1`

## 2. SMOKE — 10 questions per benchmark (do this first)
```bash
bash /scratch/users/karun09/Version_2/l40s_session/smoke_l40s.sh 10
```
- Loads the 32B models once, then generates 10 each for A, B, C, and **prints sample records**.
- Inspect the printed questions + answer keys. If they look good, proceed.
- Re-run a single benchmark’s smoke if needed, e.g.:
  `cd /scratch/users/karun09/Version_2/Benchmark_A/Question_Generation && \
   PYTHONPATH=$PWD /scratch/users/karun09/miniforge3/envs/simr/bin/python -m qgen.run_generate config/qgen.yaml --target 10`

## 3. FULL run — 500 per benchmark
```bash
bash /scratch/users/karun09/Version_2/l40s_session/run_l40s.sh 500
```
- Resumable: `questions.jsonl` is append-only; re-running continues toward 500.
- Outputs per benchmark: `Benchmark_{A,B,C}/Question_Generation/outputs/questions.jsonl` + `run_manifest.json`.

## Alternative: submit as a batch job (survives disconnect)
```bash
sbatch /scratch/users/karun09/Version_2/l40s_session/l40s.sbatch     # runs smoke(10) then full(500)
squeue --me                                                          # watch status
tail -f /scratch/users/karun09/Version_2/l40s_session/l40s.*.out      # watch progress
```

## Inspect results anytime
```bash
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
$PY /scratch/users/karun09/Version_2/show_question.py \
   /scratch/users/karun09/Version_2/Benchmark_A/Question_Generation/outputs/questions.jsonl 5
```

## Troubleshooting
- **CUDA OOM at model load / mid-run:** request `-G 4` (not 3); or lower `max_memory_per_gpu` is already
  22GiB — if still tight, set the **evaluator** `model_id` to `deepseek-ai/DeepSeek-R1-Distill-Qwen-14B`
  in each `config/qgen.yaml`.
- **Slow generation:** expected — HF multi-GPU is naive model-parallel (bigger, not faster). For speed,
  the path is vLLM tensor-parallel (not installed; see L40S_RUN_PLAN.md).
- **PubMed errors / no internet on node:** the agentic loop trips its circuit breaker and reasons from the
  chart only; set `NCBI_API_KEY` and confirm outbound HTTPS.
- **Low acceptance rate:** the evaluator is strict (4 dims, anti-buzzword, real PMIDs). 32B clears the bar
  far better than the 3B/1.5B smoke models did; if still low, relax `max_iterations`/thresholds in config.

## Config knobs (`Benchmark_*/Question_Generation/config/qgen.yaml`)
- `models.{optimizer,evaluator}.model_id`, `max_memory_per_gpu`
- `generation.target_n` (500), `max_iterations` (3), `max_tool_calls_per_agent` (6)
- `cohort.diagnosis_filter: cardiovascular_primary` (the CV restriction)
