#!/bin/bash
# Wait for the running DeepSeek job to finish, then run Phi-4 (14B) on the L40S as the
# third distinct family (replaces Mistral, which can't build sentencepiece on Py3.14).
DEEPSEEK_PID=25632
echo "phi4-chain: waiting for DeepSeek (PID $DEEPSEEK_PID) to finish... $(date)"
while kill -0 "$DEEPSEEK_PID" 2>/dev/null; do sleep 120; done
echo "phi4-chain: DeepSeek done, starting Phi-4  $(date)"

source /etc/profile.d/modules.sh 2>/dev/null || source /etc/profile.d/*.sh 2>/dev/null || true
ml purge 2>/dev/null || true
ml load math 2>/dev/null
ml load py-pytorch/2.9.1_py314 py-transformers/4.57.3_py314 2>/dev/null
export HF_HOME=$SCRATCH/.huggingface
export HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"
echo "node=$(hostname)  $(date)"; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
cd /scratch/users/karun09/CAUSAL_BENCHMARK
export CAUSAL_MODELS="microsoft/phi-4"
export CAUSAL_PROMPTS="zero_shot,cot"
export CAUSAL_MAX_NEW_TOKENS=1024
export CAUSAL_TIME_BUDGET_S=86400
python3 -u scripts/run_benchmark.py
rm -f outputs/ALL_COMPLETE
echo "=== PHI-4 DONE $(date) ==="
