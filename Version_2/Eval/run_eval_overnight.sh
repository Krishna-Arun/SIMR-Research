#!/bin/bash
# Autonomous overnight Phase-2 eval. Runs unattended:
#   1. wait for the in-flight Qwen3-32B collect to finish
#   2. swap vLLM -> gpt-oss, judge Benchmark A (ruthless mentor), aggregate  -> Qwen Δ table
#   3. Llama-3.1-8B-Instruct (American, Meta): serve w/ llama3_json tool parser, collect A/B/C x{w,wo} PubMed, judge, aggregate
#   4. gemma-3-27b-it: best-effort bonus (probe-gated; skipped if no tool calls)
#   5. final aggregate
# Safe to leave running while you sleep. Progress -> overnight.log ; markers QWEN_DONE / LLAMA_DONE / GEMMA_DONE / ALL_DONE.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
LOG=$E/overnight.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 120); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }
# tool-calling probe: returns YES if the served model emits a tool call
probe(){ cd "$E" && $PY -c "
from eval.llm import LLM
t=[{'type':'function','function':{'name':'answer','description':'submit','parameters':{'type':'object','properties':{'x':{'type':'string'}},'required':['x']}}}]
r=LLM('$1','$EP').chat([{'role':'user','content':'Call answer with x=hi.'}],tools=t)
print('YES' if r.tool_calls else 'NO')" 2>>"$LOG"; }

: > "$LOG"; log "overnight eval started"

# 1) wait for Qwen collect
log "waiting for Qwen collect (COLLECT_DONE in collect_qwen.out)…"
until grep -q "COLLECT_DONE" "$E/collect_qwen.out" 2>/dev/null; do sleep 30; done
log "Qwen collect done"

# 2) judge Qwen-A with gpt-oss + aggregate
log "swapping vLLM -> gpt-oss for judging"
kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
if wait_health; then
  log "gpt-oss healthy; judging A"; bash "$E/run_judge.sh" $EP openai/gpt-oss-20b >>"$LOG" 2>&1
  $PY "$E/aggregate.py" >>"$LOG" 2>&1; log "QWEN_DONE"
else
  log "ERROR: gpt-oss judge server didn't come up"; fi

export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub

# 3) Llama-3.1-8B-Instruct (American / Meta)  — already downloaded, ungated mirror
LM=NousResearch/Meta-Llama-3.1-8B-Instruct
log "serving Llama-3.1-8B"
kill_vllm
bash "$H/serve_vllm_model.sh" "$LM" --enable-auto-tool-choice --tool-call-parser llama3_json >/dev/null 2>&1
if wait_health && [ "$(probe "$LM")" = "YES" ]; then
  log "Llama tool-calling OK; collecting"
  : > "$E/collect_llama.out"
  bash "$E/run_collect.sh" "$LM" $EP 100 8 >>"$E/collect_llama.out" 2>&1
  log "Llama collect done; swapping to gpt-oss to judge"
  kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
  if wait_health; then bash "$E/run_judge.sh" $EP openai/gpt-oss-20b >>"$LOG" 2>&1; fi
  $PY "$E/aggregate.py" >>"$LOG" 2>&1; log "LLAMA_DONE"
else
  log "Llama SKIPPED — serve/tool-call failed (check vllm_model.log)"; fi

# 4) gemma-3-27b-it bonus (present locally; probe-gated)
GM=google/gemma-3-27b-it
GMDIR=$HF_HUB_CACHE/models--google--gemma-3-27b-it
if [ -d "$GMDIR/snapshots" ] && ls "$GMDIR/snapshots"/*/config.json >/dev/null 2>&1; then
  log "gemma present; serving (bonus)"
  kill_vllm
  bash "$H/serve_vllm_model.sh" "$GM" --enable-auto-tool-choice --tool-call-parser pythonic >/dev/null 2>&1
  if wait_health && [ "$(probe "$GM")" = "YES" ]; then
    log "gemma tool-calling OK; collecting"
    bash "$E/run_collect.sh" "$GM" $EP 100 8 >>"$LOG" 2>&1
    kill_vllm; bash "$H/serve_v23.sh" >/dev/null 2>&1
    if wait_health; then bash "$E/run_judge.sh" $EP openai/gpt-oss-20b >>"$LOG" 2>&1; fi
    $PY "$E/aggregate.py" >>"$LOG" 2>&1; log "GEMMA_DONE"
  else
    log "gemma SKIPPED — no tool calls under pythonic parser (needs hands-on tuning)"; fi
else
  log "gemma SKIPPED — not downloaded"; fi

$PY "$E/aggregate.py" >>"$LOG" 2>&1
log "ALL_DONE"
