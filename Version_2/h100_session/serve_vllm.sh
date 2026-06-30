#!/bin/bash
# Launch vLLM OpenAI server(s) INSIDE the vllm-openai Apptainer container.
# Modern vLLM cannot be pip-installed on this glibc-2.17 (CentOS 7) node — its wheels are manylinux_2_28.
# The container carries its own glibc 2.28 + CUDA 12.4; the host only provides the NVIDIA driver (--nv).
#
# Roles:
#   opt   -> optimizer  (Qwen2.5-14B-Instruct)            port 8000
#   eval  -> evaluator  (DeepSeek-R1-Distill-Qwen-14B)    port 8001
#
# Usage:
#   ./serve_vllm.sh start opt            # optimizer only, FULL gpu (one model per H100)
#   ./serve_vllm.sh start eval           # evaluator only, FULL gpu
#   ./serve_vllm.sh start both           # BOTH on one H100 (gpu_util 0.45 each)
#   ./serve_vllm.sh stop                 # kill any vllm serve here
#   ./serve_vllm.sh status               # health + GPU mem
#   ./serve_vllm.sh wait opt|eval        # block until that port is healthy
set -uo pipefail

SIF=${VLLM_CONTAINER:-/lscratch/karun09/vllm_sb}   # apptainer sandbox dir (preferred) or .sif
LOGDIR=/scratch/users/karun09/Version_2/h100_session
OPT_MODEL=Qwen/Qwen2.5-14B-Instruct
EVAL_MODEL=deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
OPT_PORT=8000
EVAL_PORT=8001
MAX_LEN=16384

export APPTAINER_CACHEDIR=$SCRATCH/.apptainer/cache APPTAINER_TMPDIR=$SCRATCH/.apptainer/tmp
HFCACHE=$SCRATCH/.huggingface

serve_one() {  # $1 model  $2 port  $3 logfile  $4 gpu_util
  setsid apptainer exec --nv \
    --bind /scratch \
    --env HF_HOME=$HFCACHE \
    --env HF_HUB_CACHE=$HFCACHE/hub \
    --env TRANSFORMERS_CACHE=$HFCACHE/transformers \
    --env HF_HUB_OFFLINE=1 \
    "$SIF" \
    vllm serve "$1" \
      --host 0.0.0.0 \
      --port "$2" \
      --served-model-name "$1" \
      --gpu-memory-utilization "$4" \
      --max-model-len "$MAX_LEN" \
      --tensor-parallel-size 1 \
      --dtype float16 \
      --disable-log-requests \
    > "$3" 2>&1 &
  echo $!
}

wait_healthy() {  # $1 port  $2 name
  for i in $(seq 1 180); do   # up to ~30 min (first model load is slow)
    if curl -sf "http://localhost:$1/v1/models" >/dev/null 2>&1; then
      echo "  $2 healthy on $(hostname):$1"; return 0
    fi
    sleep 10
  done
  echo "  ERROR: $2 not healthy on :$1 after timeout"; return 1
}

start_role() {  # $1 role  $2 util
  case "$1" in
    opt)  echo "[serve] optimizer ($OPT_MODEL) :$OPT_PORT util=$2 on $(hostname)"
          P=$(serve_one "$OPT_MODEL" "$OPT_PORT" "$LOGDIR/vllm_opt.log" "$2"); echo "$P" > "$LOGDIR/vllm_opt.pid"
          wait_healthy "$OPT_PORT" optimizer ;;
    eval) echo "[serve] evaluator ($EVAL_MODEL) :$EVAL_PORT util=$2 on $(hostname)"
          P=$(serve_one "$EVAL_MODEL" "$EVAL_PORT" "$LOGDIR/vllm_eval.log" "$2"); echo "$P" > "$LOGDIR/vllm_eval.pid"
          wait_healthy "$EVAL_PORT" evaluator ;;
  esac
}

case "${1:-status}" in
  start)
    [ -e "$SIF" ] || { echo "container missing: $SIF"; exit 1; }
    case "${2:-both}" in
      opt)  start_role opt 0.90 ;;
      eval) start_role eval 0.90 ;;
      both) start_role opt 0.45 && start_role eval 0.45 && echo "[serve] BOTH HEALTHY" ;;
      *) echo "role must be opt|eval|both"; exit 1;;
    esac
    ;;
  wait)  wait_healthy "$([ "${2:-}" = eval ] && echo $EVAL_PORT || echo $OPT_PORT)" "${2:-opt}" ;;
  stop)
    for f in vllm_opt.pid vllm_eval.pid; do
      [ -f "$LOGDIR/$f" ] && kill "$(cat "$LOGDIR/$f")" 2>/dev/null && echo "killed $(cat "$LOGDIR/$f")"
    done
    pkill -f "vllm serve" 2>/dev/null ;;
  status)
    curl -sf http://localhost:$OPT_PORT/v1/models >/dev/null 2>&1 && echo "optimizer :$OPT_PORT UP" || echo "optimizer :$OPT_PORT down"
    curl -sf http://localhost:$EVAL_PORT/v1/models >/dev/null 2>&1 && echo "evaluator :$EVAL_PORT UP" || echo "evaluator :$EVAL_PORT down"
    nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader ;;
  *) echo "usage: $0 start opt|eval|both | stop | status | wait opt|eval"; exit 1;;
esac
