#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_MEM:80GB           # Mistral-Small-24B fp16 ~48GB -> needs H100/80GB
#SBATCH -G 1
#SBATCH -c 8
#SBATCH --mem=96GB
#SBATCH -t 01:00:00
#SBATCH -J smoke_mistral
#SBATCH -o logs/smoke_mistral_%j.log
#SBATCH -e logs/smoke_mistral_%j.err

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
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
cd /scratch/users/karun09/CAUSAL_BENCHMARK
export CAUSAL_MODELS="mistralai/Mistral-Small-24B-Instruct-2501"
export CAUSAL_PROMPTS="zero_shot"
export CAUSAL_MAX_EPISODES=8
export CAUSAL_MAX_NEW_TOKENS=1024
python3 -u scripts/run_benchmark.py
echo "=== done $(date) ==="
