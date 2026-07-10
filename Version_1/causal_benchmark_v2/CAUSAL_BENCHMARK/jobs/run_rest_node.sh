#!/bin/bash
# Run the 4 remaining configs (Mistral-7B x2, DeepSeek-R1 x2) directly on the L40S node
# (sh04-01n09, 48GB) the user holds. Parallel to the qwen_cot V100 job. Checkpointed.
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
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
cd /scratch/users/karun09/CAUSAL_BENCHMARK
export CAUSAL_MODELS="mistralai/Mistral-7B-Instruct-v0.3,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
export CAUSAL_PROMPTS="zero_shot,cot"
export CAUSAL_MAX_NEW_TOKENS=1024
export CAUSAL_TIME_BUDGET_S=86400     # run to completion (no early stop)
python3 -u scripts/run_benchmark.py
rm -f outputs/ALL_COMPLETE             # subset run — don't falsely mark whole benchmark done
echo "=== DONE $(date) ==="
