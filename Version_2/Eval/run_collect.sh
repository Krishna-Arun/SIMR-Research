#!/bin/bash
# Collect agent answers for the CURRENTLY-SERVED model, A/B/C x {without, with PubMed}.
# A is collected (--no-judge); B/C scored deterministically inline. Usage: run_collect.sh MODEL ENDPOINT [N] [WORKERS]
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
M="$1"; EP="$2"; N="${3:-100}"; W="${4:-8}"
cd "$E"
log(){ echo "[$(date +%H:%M:%S)] $*"; }
for cond in "" "--pubmed"; do
  tag=$([ -n "$cond" ] && echo pubmed || echo nopubmed)
  log "A collect | $M | $tag"; $PY -m eval.run_eval_a --model "$M" --endpoint "$EP" --no-judge $cond --n "$N" --workers "$W" 2>&1 | tail -1
  log "B         | $M | $tag"; $PY -m eval.run_eval_b --model "$M" --endpoint "$EP" $cond --n "$N" --workers "$W" 2>&1 | tail -1
  log "C         | $M | $tag"; $PY -m eval.run_eval_c --model "$M" --endpoint "$EP" $cond --n "$N" --workers "$W" 2>&1 | tail -1
done
log "COLLECT_DONE $M"
