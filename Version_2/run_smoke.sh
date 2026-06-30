#!/bin/bash
# Smoke-test a benchmark's question generator end-to-end with the small pilot models on the local V100.
# Usage: ./run_smoke.sh <A|B|C> [target]   (default target=1)
set -eo pipefail
X="$1"; TARGET="${2:-1}"
V2=/scratch/users/karun09/Version_2
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
D=$V2/Benchmark_${X}/Question_Generation
cd "$D"; export PYTHONPATH=$D HF_HOME=$SCRATCH/.huggingface

echo "===== SMOKE Benchmark ${X} (target ${TARGET}, pilot models) ====="
[ -f outputs/pool.parquet ] || { echo "cohort missing — run qgen/cohort.py first"; exit 1; }
$PY -u -m qgen.run_generate config/qgen_pilot.yaml --target "$TARGET"
echo "----- generated record(s) -----"
$PY $V2/show_question.py outputs/questions.jsonl "$TARGET"
