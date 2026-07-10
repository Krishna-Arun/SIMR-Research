#!/bin/bash
# Run phi-4 (14B, cached) on the L40S node (sh04-01n09, ~46GB).
# Checkpoints every 25 episodes — safe to kill and resume.
set -uo pipefail
source /etc/profile.d/modules.sh 2>/dev/null || true
ml purge 2>/dev/null || true
ml load math 2>/dev/null
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314 2>/dev/null

export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"

echo "node=$(hostname)  $(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

cd /scratch/users/karun09/CAUSAL_BENCHMARK

export CAUSAL_MODELS="microsoft/phi-4"
export CAUSAL_PROMPTS="zero_shot,cot"
export CAUSAL_MAX_NEW_TOKENS=1024
export CAUSAL_TIME_BUDGET_S=13000    # ~3h36m — safe margin before job walltime ends

python3 -u scripts/run_benchmark.py || true

rm -f outputs/ALL_COMPLETE
echo "=== done $(date) ==="
