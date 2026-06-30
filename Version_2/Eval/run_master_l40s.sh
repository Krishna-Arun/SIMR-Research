#!/bin/bash
# MASTER chain on this L40S node. Everything runs here (H100 queue is dead).
# Order: [Qwen already running] -> wait QWEN_DONE -> Llama-3.1-8B -> Gemma-3-27B(fp8) -> build HTML deck.
# Each model: serve -> collect A/B/C x{w,wo}PubMed -> swap gpt-oss -> judge its own A files.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
SB=/lscratch/karun09/vllm_v23
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub
LOG=$E/master.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 150); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }
judge_own(){ # $1 = model basename glob
  kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
  if wait_health; then
    for f in "$E"/results_A_$1_*.json; do [ -e "$f" ] || continue
      $PY -m eval.run_eval_a --judge-file "$f" --judge-model openai/gpt-oss-20b --judge-endpoint $EP --workers 6 2>&1 | tail -1 | tee -a "$LOG"; done
  else log "ERROR gpt-oss judge didn't come up"; fi
}

: > "$LOG"; log "master chain on $(hostname)"

# 1) wait for the Qwen finisher (separate driver) to complete
log "waiting for QWEN_DONE (qwen_l40s.log)…"
until grep -q "QWEN_DONE" "$E/qwen_l40s.log" 2>/dev/null; do
  grep -q "FATAL" "$E/qwen_l40s.log" 2>/dev/null && { log "Qwen finisher FATAL — continuing to other models anyway"; break; }
  sleep 20
done
log "Qwen stage complete"; $PY "$E/make_report.py" >>"$LOG" 2>&1

# 2) Llama-3.1-8B-Instruct (American/Meta) — bf16 fits L40S, native llama3_json tool-calling
LM=NousResearch/Meta-Llama-3.1-8B-Instruct
log "serving Llama-3.1-8B"; kill_vllm
bash "$H/serve_vllm_model.sh" "$LM" --enable-auto-tool-choice --tool-call-parser llama3_json >/dev/null 2>&1
if wait_health; then
  log "Llama healthy; collecting A/B/C x{w,wo}PubMed"
  bash "$E/run_collect.sh" "$LM" $EP 100 6 >>"$E/collect_llama.out" 2>&1
  log "Llama collect done; judging"; judge_own "Meta-Llama-3.1-8B-Instruct"
  $PY "$E/make_report.py" >>"$LOG" 2>&1; log "LLAMA_DONE"
else
  log "Llama SKIPPED — serve failed"; tail -20 "$H/vllm_model.log" | tee -a "$LOG"; fi

# 3) Gemma-3-27B (American/Google) — FP8, manual guided tool-calling (llm.py auto)
log "running gemma via run_gemma_l40s.sh"
bash "$E/run_gemma_l40s.sh" >>"$LOG" 2>&1 || log "gemma driver returned nonzero"
log "gemma stage complete"

# 4) final deck
$PY "$E/make_report.py" >>"$LOG" 2>&1
log "ALL_DONE — deck at $E/deck.html"
