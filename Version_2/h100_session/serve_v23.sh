#!/bin/bash
# Serve gpt-oss-20b via the NEWER stable vllm/vllm-openai:v0.23 sandbox (fixes the launch-day 500 bug).
# Runtime CUDA 12.9 on driver 550 -> use the container's bundled cuda-compat libs (forward compat).
set -uo pipefail
H=/scratch/users/karun09/Version_2/h100_session
SB=/lscratch/karun09/vllm_v23
# in-container compat dir (e.g. /usr/local/cuda-12.9/compat)
COMPAT=/$(cd "$SB" && ls -d usr/local/cuda*/compat 2>/dev/null | head -1)
LDP="$COMPAT:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs"
echo "[serve_v23] compat=$COMPAT"
setsid apptainer exec --nv --bind /scratch \
  --env LD_LIBRARY_PATH="$LDP" \
  --env HF_HOME=/scratch/users/karun09/.huggingface \
  --env HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub \
  --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  "$SB" \
  vllm serve openai/gpt-oss-20b --host 0.0.0.0 --port 8000 \
    --served-model-name openai/gpt-oss-20b \
    --gpu-memory-utilization 0.85 --max-model-len 16384 \
    --tensor-parallel-size 1 \
    --enable-auto-tool-choice --tool-call-parser openai --reasoning-parser openai_gptoss \
  > "$H/vllm_gptoss.log" 2>&1 &
echo "[serve_v23] pid=$!"
