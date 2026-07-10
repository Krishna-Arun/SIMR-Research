#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_MEM:80GB           # H100 80GB (Mistral-24B fp16 needs ~48GB)
#SBATCH -G 1
#SBATCH -c 8
#SBATCH --mem=96GB
#SBATCH -t 02:00:00
#SBATCH -J causal_smoke_all
#SBATCH -o logs/smoke_all_%j.log
#SBATCH -e logs/smoke_all_%j.err

set -euo pipefail
mkdir -p logs

echo "=== Causal Benchmark · smoke ALL THREE models ==="
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
python3 -c "import torch;print('cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

cd /scratch/users/karun09/CAUSAL_BENCHMARK

# All three families, few episodes, one prompt style -> validates load+generate+parse
# for each, and pre-caches all weights to $SCRATCH for the full run.
export CAUSAL_MODELS="Qwen/Qwen3-8B,mistralai/Mistral-Small-24B-Instruct-2501,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
export CAUSAL_PROMPTS="zero_shot"
export CAUSAL_MAX_EPISODES=8
export CAUSAL_MAX_NEW_TOKENS=1024

python3 -u scripts/run_benchmark.py

echo "=== Smoke-all done $(date) ==="
