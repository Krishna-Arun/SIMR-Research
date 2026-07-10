#!/bin/bash
#SBATCH -p gpu
#SBATCH -C "GPU_MEM:24GB|GPU_MEM:32GB|GPU_MEM:48GB|GPU_MEM:80GB"   # any GPU >=24GB (RTX3090/V100-32/L40S/H100); widest pool, all fit Qwen3-8B fp16
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=32GB               # small footprint -> fits into partly-used (mix) nodes' free CPU/RAM
#SBATCH -t 03:00:00              # short -> backfills fast; checkpoints + auto-resubmits to resume
#SBATCH -J causal_frontier
#SBATCH -o logs/frontier_%j.log
#SBATCH -e logs/frontier_%j.err

set -euo pipefail
mkdir -p logs

echo "=== Causal Benchmark · Frontier Models ==="
echo "Job $SLURM_JOB_ID on $(hostname) — $(date)"

ml purge
ml load math
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314
# NOTE: py-accelerate/1.12.0_py314 is broken on this cluster (empty site-packages),
# so we run single-GPU fp16 (no device_map). All chosen models (~7-8B) fit a 32GB V100S.
# Mistral-Small-24B (48GB fp16) would NOT fit 32GB -> use Ministral-8B for the Mistral family.

# HF / torch caches on SCRATCH (never $HOME)
export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TORCH_HOME=$SCRATCH/.torch
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE" "$TORCH_HOME"
# For gated models (e.g. Llama): export HF_TOKEN=hf_xxx before sbatch, then uncomment:
# export HUGGING_FACE_HUB_TOKEN=${HF_TOKEN:-}

echo "GPU:"; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
python3 -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

cd /scratch/users/karun09/CAUSAL_BENCHMARK

# Three cutting-edge small models from DISTINCT families (all ungated, fp16 on one 32GB V100S):
#   Qwen3-8B (Qwen3, hybrid-thinking) · Mistral-7B-Instruct-v0.3 (Mistral family) · DeepSeek-R1-Distill-Qwen-7B (reasoning)
export CAUSAL_MODELS="Qwen/Qwen3-8B,mistralai/Mistral-7B-Instruct-v0.3,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
export CAUSAL_PROMPTS="zero_shot,cot"
export CAUSAL_MAX_NEW_TOKENS=1024     # room for reasoning models to think then emit JSON
export CAUSAL_TIME_BUDGET_S=9600      # stop+checkpoint at 2h40m, leaving buffer before the 3h kill
python3 -u scripts/run_benchmark.py || true

echo "=== Done $(date) ==="
# Auto-resume: if not fully complete, resubmit (resumes from checkpoint). Capped to avoid loops.
if [ ! -f outputs/ALL_COMPLETE ]; then
  n=$(cat .resume_count 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > .resume_count
  if [ "$n" -le 15 ]; then
    echo "Not complete — resubmitting to resume (attempt $n/15)"
    sbatch run_frontier_gpu.sbatch
  else
    echo "Max resume attempts (15) reached — stopping. Resubmit manually if needed."
  fi
else
  echo "ALL_COMPLETE present — benchmark finished."
  rm -f .resume_count
  cat outputs/RESULTS.md 2>/dev/null || true
fi
