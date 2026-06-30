#!/bin/bash
# FINISH Qwen3-32B on THIS L40S node via FP8 (H100 queue is stuck). Qwen-32B fp8 ~32GB fits 46GB L40S.
# Only the missing pieces: collect C-with-PubMed, then judge the 2 Benchmark-A files. Then aggregate.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
SB=/lscratch/karun09/vllm_v23
QM=Qwen/Qwen3-32B
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub
LOG=$E/qwen_l40s.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 150); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }
serve_qwen_fp8(){
  local COMPAT=/$(cd "$SB" && ls -d usr/local/cuda*/compat 2>/dev/null | head -1)
  setsid apptainer exec --nv --bind /scratch \
    --env LD_LIBRARY_PATH="$COMPAT:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs" \
    --env HF_HOME=$HF_HOME --env HF_HUB_CACHE=$HF_HUB_CACHE \
    --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
    "$SB" vllm serve "$QM" --host 0.0.0.0 --port 8000 --served-model-name "$QM" \
      --quantization fp8 --gpu-memory-utilization 0.92 --max-model-len 12288 --tensor-parallel-size 1 \
      --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1 \
    > "$H/vllm_qwen_l40s.log" 2>&1 &
}

: > "$LOG"; log "Qwen3-32B FP8 finish on $(hostname) ($(nvidia-smi --query-gpu=name --format=csv,noheader|head -1))"

log "clearing any stale vllm"; kill_vllm
log "serving Qwen3-32B fp8 (max_len 12288, util 0.92)"; serve_qwen_fp8
if ! wait_health; then log "FATAL qwen serve failed:"; tail -40 "$H/vllm_qwen_l40s.log" | tee -a "$LOG"; exit 1; fi
log "qwen healthy"

# only the interrupted step: Benchmark C with PubMed
log "collecting C/pubmed (the step the timeout killed)"
$PY -m eval.run_eval_c --model "$QM" --endpoint $EP --pubmed --n 100 --workers 6 2>&1 | tail -1 | tee -a "$LOG"

# judge the two Benchmark-A files (collected earlier, never judged)
log "swap to gpt-oss to judge Qwen Benchmark-A files"
kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
if wait_health; then
  for f in "$E"/results_A_Qwen3-32B_nopubmed.json "$E"/results_A_Qwen3-32B_pubmed.json; do
    [ -e "$f" ] || continue
    $PY -m eval.run_eval_a --judge-file "$f" --judge-model openai/gpt-oss-20b --judge-endpoint $EP --workers 6 2>&1 | tail -1 | tee -a "$LOG"
  done
else
  log "ERROR: gpt-oss judge server didn't come up"; fi

$PY "$E/aggregate.py" >>"$LOG" 2>&1
log "QWEN_DONE"