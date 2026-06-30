#!/bin/bash
#SBATCH -J eval_vllm
#SBATCH -p gpu
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH -G 1
#SBATCH -c 8
#SBATCH --mem=96G
#SBATCH -t 08:00:00
#SBATCH -o /scratch/users/karun09/Version_2/h100_session/eval_server.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/h100_session/eval_server.%j.out
# Evaluator vLLM server on a dedicated H100 (full GPU). Writes EVAL_READY with its endpoint when healthy,
# then runs vLLM in the foreground so the job stays alive for the whole generation run.

set -uo pipefail
SIF=/scratch/users/karun09/Version_2/containers/vllm_085.sif
LOGDIR=/scratch/users/karun09/Version_2/h100_session
MODEL=deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
PORT=8001
MAX_LEN=16384
HFCACHE=$SCRATCH/.huggingface
export APPTAINER_CACHEDIR=$SCRATCH/.apptainer/cache APPTAINER_TMPDIR=$SCRATCH/.apptainer/tmp

HOST=$(hostname)
rm -f "$LOGDIR/EVAL_READY"
echo "[eval_server] node=$HOST port=$PORT model=$MODEL  $(date)"

# background watcher: when the local endpoint answers, publish the endpoint for the orchestrator node
(
  for i in $(seq 1 240); do
    if curl -sf "http://localhost:$PORT/v1/models" >/dev/null 2>&1; then
      echo "host=$HOST port=$PORT endpoint=http://$HOST:$PORT/v1 jobid=$SLURM_JOB_ID" > "$LOGDIR/EVAL_READY"
      echo "[eval_server] HEALTHY -> wrote EVAL_READY ($HOST:$PORT)"
      break
    fi
    sleep 10
  done
) &

# foreground vLLM server (keeps the Slurm job alive)
exec apptainer exec --nv \
  --bind /scratch \
  --env HF_HOME=$HFCACHE \
  --env HF_HUB_CACHE=$HFCACHE/hub \
  --env TRANSFORMERS_CACHE=$HFCACHE/transformers \
  --env HF_HUB_OFFLINE=1 \
  "$SIF" \
  vllm serve "$MODEL" \
    --host 0.0.0.0 --port "$PORT" \
    --served-model-name "$MODEL" \
    --gpu-memory-utilization 0.90 \
    --max-model-len "$MAX_LEN" \
    --tensor-parallel-size 1 \
    --dtype float16 \
    --disable-log-requests
