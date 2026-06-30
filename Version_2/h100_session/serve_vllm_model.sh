#!/bin/bash
# Serve any HF model via the v0.23 vLLM container (forward-compat libcuda). Fast (continuous batching).
# Usage: serve_vllm_model.sh <MODEL_ID> [extra vllm serve args...]
set -uo pipefail
H=/scratch/users/karun09/Version_2/h100_session
SB=/lscratch/karun09/vllm_v23
COMPAT=/$(cd "$SB" && ls -d usr/local/cuda*/compat 2>/dev/null | head -1)
MODEL="$1"; shift
setsid apptainer exec --nv --bind /scratch \
  --env LD_LIBRARY_PATH="$COMPAT:/usr/local/cuda/lib64" \
  --env HF_HOME=/scratch/users/karun09/.huggingface \
  --env HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub \
  --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  "$SB" vllm serve "$MODEL" --host 0.0.0.0 --port 8000 --served-model-name "$MODEL" \
    --gpu-memory-utilization 0.90 --max-model-len 16384 --tensor-parallel-size 1 "$@" \
  > "$H/vllm_model.log" 2>&1 &
echo "vllm serve $MODEL pid=$!"
