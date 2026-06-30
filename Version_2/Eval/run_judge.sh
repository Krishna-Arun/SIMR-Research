#!/bin/bash
# Judge all collected Benchmark-A result files with the CURRENTLY-SERVED judge (gpt-oss). Usage: run_judge.sh ENDPOINT [JUDGE_MODEL]
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP="$1"; JM="${2:-openai/gpt-oss-20b}"
cd "$E"
for f in "$E"/results_A_*.json; do
  echo "[$(date +%H:%M:%S)] judge $(basename "$f")"
  $PY -m eval.run_eval_a --judge-file "$f" --judge-model "$JM" --judge-endpoint "$EP" --workers 8 2>&1 | tail -1
done
echo "JUDGE_DONE"
