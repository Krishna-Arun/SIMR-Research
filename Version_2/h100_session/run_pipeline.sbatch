#!/bin/bash
#SBATCH -J qgen_pipe
#SBATCH -p gpu
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH -G 1
#SBATCH -c 16
#SBATCH --mem=128G
#SBATCH -t 08:00:00
#SBATCH -o /scratch/users/karun09/Version_2/h100_session/pipeline.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/h100_session/pipeline.%j.out
# Self-contained generation pipeline on ONE properly-resourced H100:
#   build vllm SANDBOX on node-local NVMe (no squashfs -> no OOM) -> serve both 14B models
#   -> 10-Q smoke A/B/C -> write SMOKE_SUMMARY -> keep servers warm, wait for a control file:
#        touch h100_session/GO_FULL  -> run the full target (default 500) for A/B/C
#        touch h100_session/STOP     -> shut down
set -uo pipefail
V2=/scratch/users/karun09/Version_2
H=$V2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
SB=$L_SCRATCH/vllm_sb
SMOKE_N="${SMOKE_N:-10}"
FULL_N="${FULL_N:-500}"
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export APPTAINER_CACHEDIR=$SCRATCH/.apptainer/cache APPTAINER_TMPDIR=$L_SCRATCH/aptmp
mkdir -p "$APPTAINER_TMPDIR"
SUM=$H/SMOKE_SUMMARY.txt; : > "$SUM"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$SUM"; }

log "node=$(hostname) job=$SLURM_JOB_ID gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader)"

# 1) build sandbox from cached blobs (fast on NVMe, no squashfs)
if [ ! -x "$SB/usr/bin/python3" ]; then
  log "building vllm sandbox -> $SB (cached blobs, no re-download)"
  apptainer build --force --sandbox "$SB" docker://vllm/vllm-openai:v0.8.5.post1 >> "$H/sandbox_build.log" 2>&1 \
    || { log "FATAL: sandbox build failed"; tail -20 "$H/sandbox_build.log" | tee -a "$SUM"; exit 1; }
fi
log "sandbox ready"

# 2) serve both models on the one H100 (gpu_util 0.45 each)
serve_one(){ # model port log
  setsid apptainer exec --nv --bind /scratch \
    --env HF_HOME=$HF_HOME --env HF_HUB_CACHE=$HF_HUB_CACHE \
    --env TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers --env HF_HUB_OFFLINE=1 \
    "$SB" \
    vllm serve "$1" --host 0.0.0.0 --port "$2" --served-model-name "$1" \
      --gpu-memory-utilization 0.45 --max-model-len 16384 --tensor-parallel-size 1 \
      --dtype float16 --disable-log-requests > "$3" 2>&1 &
}
log "starting optimizer (Qwen2.5-14B) :8000 + evaluator (DeepSeek-R1-14B) :8001"
serve_one Qwen/Qwen2.5-14B-Instruct 8000 "$H/vllm_opt.log"
serve_one deepseek-ai/DeepSeek-R1-Distill-Qwen-14B 8001 "$H/vllm_eval.log"
for port in 8000 8001; do
  ok=0; for i in $(seq 1 180); do curl -sf "http://localhost:$port/v1/models" >/dev/null 2>&1 && { ok=1; break; }; sleep 10; done
  if [ $ok -ne 1 ]; then
    log "FATAL: server :$port not healthy"
    echo "---- :$port log ----" | tee -a "$SUM"; tail -30 "$H/vllm_$([ $port = 8001 ] && echo eval || echo opt).log" | tee -a "$SUM"
    exit 1
  fi
  log "server :$port healthy"
done
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader | tee -a "$SUM"

# 3) smoke each benchmark fresh, timed
run_set(){ # target tag
  local T=$1 TAG=$2
  for X in A B C; do
    local D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
    rm -f outputs/questions.jsonl outputs/QGEN_COMPLETE outputs/run_manifest.json
    log "[$TAG] Benchmark $X -> target $T"
    local t0=$SECONDS
    $PY -u -m qgen.run_generate config/qgen.yaml --target "$T" > "$H/${TAG}_${X}.log" 2>&1
    local rc=$? n; n=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0)
    local sec=$((SECONDS-t0)) per="n/a"; [ "$n" -gt 0 ] && per="$(awk "BEGIN{printf \"%.1f\",$sec/$n}")s/Q"
    log "[$TAG] Benchmark $X: ${n}/${T} in ${sec}s (${per}) rc=$rc"
  done
}
log "================ SMOKE (target ${SMOKE_N}) ================"
run_set "$SMOKE_N" smoke
log "SMOKE_RESULT=DONE"

# 4) review gate: keep servers warm; wait for GO_FULL or STOP
rm -f "$H/GO_FULL" "$H/STOP"
log "servers warm. waiting for control file: touch $H/GO_FULL (run full ${FULL_N}) or $H/STOP"
while true; do
  [ -f "$H/STOP" ]    && { log "STOP received"; break; }
  [ -f "$H/GO_FULL" ] && { log "================ FULL (target ${FULL_N}) ================"; rm -f "$H/GO_FULL"; run_set "$FULL_N" full; log "FULL_RESULT=DONE"; break; }
  sleep 30
done
log "pipeline exiting"
