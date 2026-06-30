#!/bin/bash
# Re-run Llama-3.1-8B correctly: its native llama3_json path crashed the vLLM engine (EngineDeadError)
# -> B/C scored 0, A scored ~0. Fix: manual guided-JSON tool-calling (EVAL_FORCE_MANUAL) + --enforce-eager
# (no CUDA graphs) for stability. Validate with a dry-run before the full collect. Then judge + rebuild deck.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
SB=/lscratch/karun09/vllm_v23
LM=NousResearch/Meta-Llama-3.1-8B-Instruct
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub
LOG=$E/fix.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 150); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }
serve_llama(){  # plain serve (manual mode sends no tools to the server); enforce-eager for stability
  local COMPAT=/$(cd "$SB" && ls -d usr/local/cuda*/compat 2>/dev/null | head -1)
  setsid apptainer exec --nv --bind /scratch \
    --env LD_LIBRARY_PATH="$COMPAT:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs" \
    --env HF_HOME=$HF_HOME --env HF_HUB_CACHE=$HF_HUB_CACHE --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
    "$SB" vllm serve "$LM" --host 0.0.0.0 --port 8000 --served-model-name "$LM" \
      --gpu-memory-utilization 0.90 --max-model-len 16384 --tensor-parallel-size 1 --enforce-eager \
    > "$H/vllm_llama_fix.log" 2>&1 &
}

: > "$LOG"; log "Llama re-run (manual guided mode) on $(hostname)"
kill_vllm; log "serving Llama-3.1-8B (enforce-eager)"; serve_llama
if ! wait_health; then log "FATAL llama serve failed"; tail -30 "$H/vllm_llama_fix.log" | tee -a "$LOG"; exit 1; fi
log "llama healthy"

export EVAL_FORCE_MANUAL=1   # guided-JSON tool-calling for the COLLECT (judge runs in a separate, native process)
log "dry-run (2 q on C) to validate manual tool-calling…"
$PY -m eval.run_eval_c --model "$LM" --endpoint $EP --n 2 --workers 2 --out "$E/_llama_dry.json" 2>&1 | tail -1 | tee -a "$LOG"
DRY=$($PY -c "import json;d=json.load(open('$E/_llama_dry.json'));print(sum(1 for r in d['results'] if r.get('choice') in ('A','B')))" 2>/dev/null)
log "dry-run produced ${DRY:-0}/2 valid choices"
if [ "${DRY:-0}" = "0" ]; then log "FATAL manual tool-calling still empty; aborting"; exit 1; fi

log "FULL collect A/B/C x{w,wo}PubMed (manual mode, workers 4)"
bash "$E/run_collect.sh" "$LM" $EP 100 4 >>"$E/collect_llama.out" 2>&1
unset EVAL_FORCE_MANUAL

log "swap to gpt-oss; judge Llama A files"
kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
if wait_health; then
  for f in "$E"/results_A_Meta-Llama-3.1-8B-Instruct_*.json; do [ -e "$f" ] || continue
    $PY -m eval.run_eval_a --judge-file "$f" --judge-model openai/gpt-oss-20b --judge-endpoint $EP --workers 6 2>&1 | tail -1 | tee -a "$LOG"; done
else log "ERROR gpt-oss judge didn't come up"; fi

$PY "$E/make_report.py" >>"$LOG" 2>&1
log "FIX_DONE"