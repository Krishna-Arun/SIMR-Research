#!/bin/bash
# Generate TARGET questions per benchmark (A/B/C) against the running gpt-oss server (:8000).
# RESUMABLE: run_generate appends to questions.jsonl, so re-running continues toward TARGET.
# Single-shot optimizer (no evaluator) + deterministic leak guard.
set -uo pipefail
V2=/scratch/users/karun09/Version_2
H=$V2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
TARGET="${1:-100}"
SUM=$H/RUN_SUMMARY.txt; : > "$SUM"
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub TOKENIZERS_PARALLELISM=false
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$SUM"; }

curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 || { log "FATAL: gpt-oss server down"; echo "RUN_RESULT=FAIL_NOSERVER" >>"$SUM"; exit 1; }
log "gpt-oss server up; generating ${TARGET}/benchmark (A,B,C)"
for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
  have=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0)
  log "===== Benchmark ${X}: have ${have}, target ${TARGET} ====="
  t0=$SECONDS
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" > "$H/run_${X}.log" 2>&1
  rc=$?; n=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0)
  sec=$((SECONDS-t0)); per="n/a"; [ "$n" -gt 0 ] && per="$(awk "BEGIN{printf \"%.1f\",$sec/$n}")s/Q"
  log "Benchmark ${X}: ${n}/${TARGET} in ${sec}s (${per}) rc=${rc}"
done
log "RUN_RESULT=DONE"
