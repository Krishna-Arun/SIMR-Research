#!/bin/bash
# Run google/gemma-3-27b-it (American comparator, Google) in FP8 on THIS L40S node (46GB).
# Gemma has no vLLM tool parser -> llm.py auto-uses guided-JSON manual tool-calling.
# Chain: serve gemma fp8 -> dry-run validate -> full collect A/B/C x{w,wo}PubMed -> swap gpt-oss -> judge gemma's A files.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
SB=/lscratch/karun09/vllm_v23
GM=google/gemma-3-27b-it
export APPTAINER_CACHEDIR=/scratch/users/karun09/.apptainer
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub
LOG=$E/gemma_l40s.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 150); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }
serve_gemma(){
  local COMPAT=/$(cd "$SB" && ls -d usr/local/cuda*/compat 2>/dev/null | head -1)
  setsid apptainer exec --nv --bind /scratch \
    --env LD_LIBRARY_PATH="$COMPAT:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs" \
    --env HF_HOME=$HF_HOME --env HF_HUB_CACHE=$HF_HUB_CACHE \
    --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
    "$SB" vllm serve "$GM" --host 0.0.0.0 --port 8000 --served-model-name "$GM" \
      --quantization fp8 --gpu-memory-utilization 0.92 --max-model-len 8192 --tensor-parallel-size 1 \
    > "$H/vllm_gemma.log" 2>&1 &
}

: > "$LOG"; log "gemma FP8 on $(hostname) ($(nvidia-smi --query-gpu=name --format=csv,noheader|head -1))"

mkdir -p /lscratch/karun09
if [ ! -d "$SB/usr/local/cuda" ]; then
  log "building v23 sandbox from cache…"
  apptainer build --force --sandbox "$SB" docker://vllm/vllm-openai:v0.23.0-cu129-ubuntu2404 >>"$E/recover_build.log" 2>&1 \
    && log "sandbox built" || { log "FATAL sandbox build failed"; exit 1; }
fi

log "serving gemma-3-27b-it fp8 (max_len 8192, util 0.92)"
kill_vllm; serve_gemma
if ! wait_health; then log "FATAL gemma serve failed:"; tail -40 "$H/vllm_gemma.log" | tee -a "$LOG"; exit 1; fi
log "gemma healthy"

# validate manual guided tool-calling end-to-end on 2 questions before the full run
log "dry-run (2 q on C) to validate manual tool-calling…"
$PY -m eval.run_eval_c --model "$GM" --endpoint $EP --n 2 --workers 2 --out "$E/_gemma_dry.json" 2>&1 | tail -2 | tee -a "$LOG"
DRY=$($PY -c "import json;d=json.load(open('$E/_gemma_dry.json'));print(sum(1 for r in d['results'] if r.get('choice') in ('A','B')))" 2>/dev/null)
log "dry-run produced $DRY/2 valid choices"
if [ "${DRY:-0}" = "0" ]; then log "FATAL manual tool-calling produced no valid answers; aborting before full run"; tail -20 "$H/vllm_gemma.log" | tee -a "$LOG"; exit 1; fi

log "FULL collect A/B/C x {without, with} PubMed (n=100)"
bash "$E/run_collect.sh" "$GM" $EP 100 6 >>"$E/collect_gemma.out" 2>&1
log "collect done"

log "swap to gpt-oss to judge gemma's Benchmark-A files"
kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
if wait_health; then
  for f in "$E"/results_A_gemma-3-27b-it_*.json; do
    [ -e "$f" ] || continue
    $PY -m eval.run_eval_a --judge-file "$f" --judge-model openai/gpt-oss-20b --judge-endpoint $EP --workers 6 2>&1 | tail -1 | tee -a "$LOG"
  done
else
  log "ERROR: gpt-oss judge server didn't come up"; fi

$PY "$E/aggregate.py" >>"$LOG" 2>&1
log "GEMMA_DONE"
