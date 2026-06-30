#!/bin/bash
# Serve gpt-oss-20b via the vllm/vllm-openai:gptoss Apptainer sandbox on this H100.
# Runtime is CUDA 12.8 on a 550 driver -> use the container's bundled cuda-compat libs (forward compat).
# NOTE: do NOT set TRANSFORMERS_CACHE (it overrides HF_HUB_CACHE with an empty dir -> offline lookups fail).
set -uo pipefail
H=/scratch/users/karun09/Version_2/h100_session
SB=${VLLM_GPTOSS_SB:-/lscratch/karun09/vllm_gptoss}
PORT=${PORT:-8000}
UTIL=${UTIL:-0.85}
MAXLEN=${MAXLEN:-16384}
setsid apptainer exec --nv --bind /scratch \
  --env LD_LIBRARY_PATH=/usr/local/cuda-12.8/compat:/usr/local/cuda-12.8/lib64 \
  --env HF_HOME=/scratch/users/karun09/.huggingface \
  --env HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub \
  --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  "$SB" \
  vllm serve openai/gpt-oss-20b --host 0.0.0.0 --port "$PORT" \
    --served-model-name openai/gpt-oss-20b \
    --gpu-memory-utilization "$UTIL" --max-model-len "$MAXLEN" \
    --tensor-parallel-size 1 --disable-log-requests \
  > "$H/vllm_gptoss.log" 2>&1 &
echo "gpt-oss server pid=$!"
