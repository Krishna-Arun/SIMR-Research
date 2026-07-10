#!/bin/bash
# Full Phase-2 eval via Ollama on an EXCLUSIVE-mode GPU (one model at a time):
#   Phase 1 — collect agent answers with each TEST model (A: --no-judge; B/C: deterministic, full).
#   Phase 2 — swap to gpt-oss judge, score the collected A answers (ruthless mentor).
# Then aggregate the with-vs-without-PubMed Δ.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
OLL=http://127.0.0.1:11434/v1
N="${1:-100}"
MODELS=("qwen3.6:27b" "gemma3:27b")
cd "$E"
log(){ echo "[$(date +%H:%M:%S)] $*"; }
curl -sf $OLL/models >/dev/null 2>&1 || { log "FATAL: ollama down"; exit 1; }

log "===== PHASE 1: collect agent answers (test models) ====="
for M in "${MODELS[@]}"; do
  for cond in "" "--pubmed"; do
    tag=$([ -n "$cond" ] && echo pubmed || echo nopubmed)
    log "A collect | $M | $tag"; $PY -m eval.run_eval_a --model "$M" --endpoint $OLL --no-judge $cond --n "$N" 2>&1 | tail -1
    log "B         | $M | $tag"; $PY -m eval.run_eval_b --model "$M" --endpoint $OLL $cond --n "$N" 2>&1 | tail -1
    log "C         | $M | $tag"; $PY -m eval.run_eval_c --model "$M" --endpoint $OLL $cond --n "$N" 2>&1 | tail -1
  done
done

log "===== PHASE 2: judge A with gpt-oss (ruthless mentor) ====="
for f in "$E"/results_A_*.json; do
  log "judge $(basename "$f")"; $PY -m eval.run_eval_a --judge-file "$f" --judge-model gpt-oss:20b --judge-endpoint $OLL 2>&1 | tail -1
done

log "aggregating…"; $PY "$E/aggregate.py"
log "ALL_EVAL_DONE"
