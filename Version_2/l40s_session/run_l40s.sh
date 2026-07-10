#!/bin/bash
# FULL run: generate target_n (config, =500) questions per benchmark. Resumable (append-only).
set -eo pipefail
V2=/scratch/users/karun09/Version_2
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers TOKENIZERS_PARALLELISM=false
TARGET="${1:-500}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
  echo "===================== FULL Benchmark ${X} (target ${TARGET}) ====================="
  [ -f outputs/pool.parquet ] || $PY -u qgen/cohort.py config/qgen.yaml
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" 2>&1 | tee "outputs/l40s_full.log"
  echo "===== ${X} DONE: $(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0) questions ====="
done
echo "=== ALL DONE: $(date) ==="
