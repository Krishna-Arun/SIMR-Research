#!/bin/bash
# Timed smoke: 7B+7B (qgen_pilot.yaml) on the in-hand L40S, target N/benchmark, with per-line wall-clock
# timestamps so we can compute seconds-per-question. Sequential A -> B -> C.
set -eo pipefail
V2=/scratch/users/karun09/Version_2
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers TOKENIZERS_PARALLELISM=false
TARGET="${1:-10}"
for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation; cd "$D"; export PYTHONPATH=$D
  rm -f outputs/questions.jsonl outputs/QGEN_COMPLETE
  echo "@@@ BENCH ${X} START $(date +%s) @@@"
  stdbuf -oL -eL $PY -u -m qgen.run_generate config/qgen_pilot.yaml --target "$TARGET" 2>&1 \
    | while IFS= read -r line; do printf '%s\t%s\n' "$(date +%s)" "$line"; done
  echo "@@@ BENCH ${X} END $(date +%s) accepted=$(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0) @@@"
done
echo "@@@ ALL DONE $(date +%s) @@@"
