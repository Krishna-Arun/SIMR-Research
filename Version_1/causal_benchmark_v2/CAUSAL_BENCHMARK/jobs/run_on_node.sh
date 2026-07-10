#!/bin/bash
# Run the benchmark directly on the current OnDemand GPU node (RTX 2080 Ti, 11GB).
# Small variants of distinct families that fit 11GB fp16. NOT submitted via Slurm —
# runs in the user's interactive session.
set -e
source /etc/profile.d/modules.sh 2>/dev/null || source /etc/profile.d/*.sh 2>/dev/null || true
ml purge 2>/dev/null || true
ml load math 2>/dev/null
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314 2>/dev/null

export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"

echo "node=$(hostname)  $(date)"
python3 -c "import torch;print('cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

cd /scratch/users/karun09/CAUSAL_BENCHMARK
# Largest cutting-edge small models from DISTINCT families that fit an 11GB GPU in fp16:
export CAUSAL_MODELS="Qwen/Qwen3-4B-Instruct-2507,microsoft/Phi-3.5-mini-instruct,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
export CAUSAL_PROMPTS="zero_shot"
export CAUSAL_MAX_NEW_TOKENS=768
python3 -u scripts/run_benchmark.py
echo "=== DONE $(date) ==="
[ -f outputs/RESULTS.md ] && cat outputs/RESULTS.md
