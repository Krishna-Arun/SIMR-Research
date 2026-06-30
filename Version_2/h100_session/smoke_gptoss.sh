#!/bin/bash
# Run the 10-Q smoke for A/B/C against the already-running gpt-oss-20b vLLM server (:8000).
# Single-model generator (gpt-oss-20b drives both optimizer and evaluator roles).
set -uo pipefail
V2=/scratch/users/karun09/Version_2
H=$V2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
TARGET="${1:-10}"
SUM=$H/SMOKE_SUMMARY.txt; : > "$SUM"
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub TOKENIZERS_PARALLELISM=false
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$SUM"; }

curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 || { log "FATAL: gpt-oss server not up on :8000"; echo "SMOKE_RESULT=FAIL_NOSERVER" >>"$SUM"; exit 1; }
log "gpt-oss server up; starting smoke (target ${TARGET}) for A/B/C"
for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
  rm -f outputs/questions.jsonl outputs/QGEN_COMPLETE outputs/run_manifest.json
  log "===== Benchmark ${X} (target ${TARGET}) ====="
  t0=$SECONDS
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" > "$H/smoke_${X}.log" 2>&1
  rc=$?; n=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0)
  sec=$((SECONDS-t0)); per="n/a"; [ "$n" -gt 0 ] && per="$(awk "BEGIN{printf \"%.1f\",$sec/$n}")s/Q"
  log "Benchmark ${X}: ${n}/${TARGET} in ${sec}s (${per}) rc=${rc}"
done
log "SMOKE_RESULT=DONE"
