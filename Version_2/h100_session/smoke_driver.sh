#!/bin/bash
# Autonomous smoke driver: wait for SIF -> start both 14B vLLM servers on this H100 ->
# health-gate -> fresh 10-Q smoke for A/B/C (timed) -> show samples -> write SMOKE_SUMMARY.
# Leaves the vLLM servers UP afterward (reusable for the full run).
set -uo pipefail
V2=/scratch/users/karun09/Version_2
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
SIF=$V2/containers/vllm_085.sif
H=$V2/h100_session
SUM=$H/SMOKE_SUMMARY.txt
TARGET="${1:-10}"
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export APPTAINER_CACHEDIR=$SCRATCH/.apptainer/cache APPTAINER_TMPDIR=$SCRATCH/.apptainer/tmp
: > "$SUM"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$SUM"; }

# 1) wait for the container image
log "waiting for SIF ..."
for i in $(seq 1 240); do [ -s "$SIF" ] && break; sleep 15; done
[ -s "$SIF" ] || { log "FATAL: SIF never appeared"; echo "SMOKE_RESULT=FAIL_NO_SIF" >> "$SUM"; exit 1; }
log "SIF ready: $(ls -la "$SIF" | awk '{print $5}') bytes"

# 2) start both servers (gpu_util 0.45 each), health-gated
log "starting both vLLM servers on $(hostname) ..."
if ! bash "$H/serve_vllm.sh" start both >> "$SUM" 2>&1; then
  log "FATAL: servers did not become healthy"
  echo "---- vllm_opt.log tail ----" >> "$SUM"; tail -25 "$H/vllm_opt.log" >> "$SUM" 2>/dev/null
  echo "---- vllm_eval.log tail ----" >> "$SUM"; tail -25 "$H/vllm_eval.log" >> "$SUM" 2>/dev/null
  echo "SMOKE_RESULT=FAIL_SERVERS" >> "$SUM"; exit 1
fi
log "both servers healthy"
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader | tee -a "$SUM"

# 3) smoke each benchmark fresh, timed
declare -A CNT TIME
for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation
  cd "$D"; export PYTHONPATH=$D
  rm -f outputs/questions.jsonl outputs/QGEN_COMPLETE outputs/run_manifest.json
  log "===== SMOKE Benchmark ${X} (target ${TARGET}) ====="
  t0=$(date +%s)
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" >> "$H/smoke_${X}.log" 2>&1
  rc=$?
  t1=$(date +%s)
  n=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0)
  CNT[$X]=$n; TIME[$X]=$((t1-t0))
  log "Benchmark ${X}: ${n}/${TARGET} questions in $((t1-t0))s (rc=$rc)"
done

# 4) summary
{
  echo "================ SMOKE SUMMARY ================"
  for X in A B C; do
    sec=${TIME[$X]}; n=${CNT[$X]}
    per="n/a"; [ "$n" -gt 0 ] && per="$(awk "BEGIN{printf \"%.1f\", $sec/$n}")s/Q"
    echo "  Benchmark $X: ${n}/${TARGET} in ${sec}s  (${per})"
  done
  echo "==============================================="
  echo "SMOKE_RESULT=DONE"
} | tee -a "$SUM"
