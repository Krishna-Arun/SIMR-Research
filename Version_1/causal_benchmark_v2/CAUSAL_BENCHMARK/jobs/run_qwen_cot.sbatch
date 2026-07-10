#!/bin/bash
#SBATCH -p gpu
#SBATCH -C "GPU_MEM:24GB|GPU_MEM:32GB|GPU_MEM:48GB|GPU_MEM:80GB"   # any >=24GB (fits Qwen3-8B); widest pool = fast schedule
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=32GB
#SBATCH -t 04:00:00
#SBATCH -J qwen_cot
#SBATCH -o logs/qwen_cot_%j.log
#SBATCH -e logs/qwen_cot_%j.err

set -uo pipefail
mkdir -p logs
echo "Job $SLURM_JOB_ID on $(hostname) — $(date)"
ml purge
ml load math
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314
export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

cd /scratch/users/karun09/CAUSAL_BENCHMARK
# ONLY Qwen3-8B chain-of-thought (zero_shot already done; its checkpoint/results are untouched).
export CAUSAL_MODELS="Qwen/Qwen3-8B"
export CAUSAL_PROMPTS="cot"
export CAUSAL_MAX_NEW_TOKENS=1024
export CAUSAL_TIME_BUDGET_S=13800     # 3h50m, leaves buffer before the 4h kill
python3 -u scripts/run_benchmark.py || true

# This is a single-config run, not the whole benchmark — don't let it falsely mark ALL done.
rm -f outputs/ALL_COMPLETE
echo "=== done $(date) ==="
