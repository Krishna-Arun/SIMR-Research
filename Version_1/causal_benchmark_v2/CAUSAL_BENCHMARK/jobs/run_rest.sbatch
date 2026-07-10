#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_SKU:L40S          # 48GB Ada, abundant + fast (R1 reasoning is the bottleneck)
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=40GB
#SBATCH -t 16:00:00
#SBATCH -J causal_rest
#SBATCH -o logs/rest_%j.log
#SBATCH -e logs/rest_%j.err

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
# The 4 remaining configs, sequentially, IN PARALLEL with the qwen_cot job (different model
# files -> separate checkpoints/results, no collision). Each config checkpoints every 25 episodes.
export CAUSAL_MODELS="mistralai/Mistral-7B-Instruct-v0.3,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
export CAUSAL_PROMPTS="zero_shot,cot"
export CAUSAL_MAX_NEW_TOKENS=1024
export CAUSAL_TIME_BUDGET_S=56400    # ~15h40m; use the full walltime, checkpoint before the 16h kill
python3 -u scripts/run_benchmark.py || true

# Single-job (subset) run — don't let it falsely mark the whole benchmark complete.
rm -f outputs/ALL_COMPLETE
echo "=== done $(date) ==="
