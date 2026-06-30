#!/bin/bash
#SBATCH -J qgen_drv
#SBATCH -p normal
#SBATCH -c 16
#SBATCH --mem=32G
#SBATCH -t 08:00:00
#SBATCH -o /scratch/users/karun09/Version_2/h100_session/orchestrate.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/h100_session/orchestrate.%j.out
# Lightweight generation driver (CPU-only). The gpt-oss-20b model server runs on the H100 node
# (sh04-01n07.int:8000); this job just drives run_generate for A/B/C and talks to it over HTTP.
# Run target: pass via env  TARGET=10 (smoke) or TARGET=500 (full). Default 10.
set -uo pipefail
V2=/scratch/users/karun09/Version_2
H=$V2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
TARGET="${TARGET:-10}"
TAG="${TAG:-smoke}"
SERVER="http://sh04-01n07.int:8000/v1/models"
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub TOKENIZERS_PARALLELISM=false
SUM=$H/${TAG}_SUMMARY.txt; : > "$SUM"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$SUM"; }

log "driver on $(hostname) (cpu job $SLURM_JOB_ID), target=$TARGET, tag=$TAG"
if ! curl -sf "$SERVER" >/dev/null 2>&1; then
  log "FATAL: gpt-oss server not reachable at $SERVER"; echo "${TAG}_RESULT=FAIL_NOSERVER" >>"$SUM"; exit 1
fi
log "gpt-oss server reachable"

for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
  rm -f outputs/questions.jsonl outputs/QGEN_COMPLETE outputs/run_manifest.json
  log "===== Benchmark ${X} (target ${TARGET}) ====="
  t0=$SECONDS
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" > "$H/${TAG}_${X}.log" 2>&1
  rc=$?; n=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0)
  sec=$((SECONDS-t0)); per="n/a"; [ "$n" -gt 0 ] && per="$(awk "BEGIN{printf \"%.1f\",$sec/$n}")s/Q"
  log "Benchmark ${X}: ${n}/${TARGET} in ${sec}s (${per}) rc=${rc}"
done
log "${TAG}_RESULT=DONE"
