#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_MEM:32GB           # Qwen3-8B fp16 ~16GB; any 32GB GPU works (schedules fast)
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=48GB
#SBATCH -t 00:40:00
#SBATCH -J smoke_qwen3
#SBATCH -o logs/smoke_qwen3_%j.log
#SBATCH -e logs/smoke_qwen3_%j.err

set -euo pipefail
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
python3 -c "import torch;print('cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
cd /scratch/users/karun09/CAUSAL_BENCHMARK
export CAUSAL_MODELS="Qwen/Qwen3-8B"
export CAUSAL_PROMPTS="zero_shot"
export CAUSAL_MAX_EPISODES=8
export CAUSAL_MAX_NEW_TOKENS=1024
python3 -u scripts/run_benchmark.py
echo "=== done $(date) ==="
