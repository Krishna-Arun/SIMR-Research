#!/bin/bash
#SBATCH -p gpu
#SBATCH -C GPU_SKU:L40S          # 48GB Ada — fits DeepSeek-R1-Distill-Qwen-7B comfortably
#SBATCH -G 1
#SBATCH -c 4
#SBATCH --mem=40GB
#SBATCH -t 06:00:00
#SBATCH -J deepseek_cot
#SBATCH -o logs/deepseek_cot_%j.log
#SBATCH -e logs/deepseek_cot_%j.err

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
# Resume DeepSeek-R1-Distill-Qwen-7B CoT — checkpoint has 502/502 main + 25/502 flips done.
export CAUSAL_MODELS="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
export CAUSAL_PROMPTS="cot"
export CAUSAL_MAX_NEW_TOKENS=1024
export CAUSAL_TIME_BUDGET_S=21000     # 5h50m, leaves buffer before the 6h kill
python3 -u scripts/run_benchmark.py || true

rm -f outputs/ALL_COMPLETE
echo "=== done $(date) ==="
