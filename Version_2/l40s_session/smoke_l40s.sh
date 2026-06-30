#!/bin/bash
# SMOKE: generate N (default 10) questions per benchmark on the L40S allocation, then show samples.
# Run this AFTER you have the allocation (see MANUAL.md). Fresh start (clears prior questions.jsonl).
set -eo pipefail
V2=/scratch/users/karun09/Version_2
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers TOKENIZERS_PARALLELISM=false
TARGET="${1:-10}"
echo "=== GPUs visible ==="; nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
  echo "===================== SMOKE Benchmark ${X} (target ${TARGET}) ====================="
  [ -f outputs/pool.parquet ] || { echo "ERROR: cohort missing for ${X}"; exit 1; }
  rm -f outputs/questions.jsonl outputs/QGEN_COMPLETE          # fresh smoke
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" 2>&1 | tee outputs/l40s_smoke.log
  echo "----- sample generated records (${X}) -----"
  $PY "$V2/show_question.py" outputs/questions.jsonl 3 || true
done
echo "=== SMOKE COMPLETE: $(date) ==="
