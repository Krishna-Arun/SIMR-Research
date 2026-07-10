#!/bin/bash
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --mem=120G
#SBATCH --cpus-per-task=16
#SBATCH --time=08:00:00
#SBATCH -J gemma_eval
#SBATCH -o /scratch/users/karun09/Version_2/Eval/gemma_%j.out
# Bring Google gemma-3-27b-it into the eval as the American comparator.
# License is already accepted (model is in cache). Open question = agentic tool-calling.
# Step 1: serve + probe both auto (pythonic parser) and forced (guided) tool-calling.
# Step 2: if auto works -> full A/B/C x{w,wo}PubMed collect + gpt-oss judge + aggregate.
#         else -> log a definitive verdict so we wire the right fallback (forced/guided or text-ReAct).
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
SB=/lscratch/karun09/vllm_v23
GM=google/gemma-3-27b-it
export APPTAINER_CACHEDIR=/scratch/users/karun09/.apptainer
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub
LOG=$E/gemma.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 150); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }

: > "$LOG"; log "gemma eval on $(hostname)"

# rebuild sandbox if needed
mkdir -p /lscratch/karun09
if [ ! -d "$SB/usr/local/cuda" ]; then
  log "building v23 sandbox from cache…"
  apptainer build --force --sandbox "$SB" docker://vllm/vllm-openai:v0.23 >>"$E/recover_build.log" 2>&1 \
    && log "sandbox built" || { log "FATAL sandbox build failed"; exit 1; }
fi

# serve gemma (text use of a multimodal model; pythonic = generic tool parser)
log "serving gemma-3-27b-it"; kill_vllm
bash "$H/serve_vllm_model.sh" "$GM" --enable-auto-tool-choice --tool-call-parser pythonic >/dev/null 2>&1
if ! wait_health; then log "FATAL gemma serve failed (see vllm_model.log)"; tail -30 "$H/vllm_model.log" | tee -a "$LOG"; exit 1; fi

# dual probe: auto (parser) vs forced (guided, no parser needed)
log "probing tool-calling…"
VERDICT=$(cd "$E" && $PY -c "
from openai import OpenAI
c=OpenAI(base_url='$EP',api_key='EMPTY',timeout=120)
T=[{'type':'function','function':{'name':'answer','description':'submit final',
   'parameters':{'type':'object','properties':{'x':{'type':'string'}},'required':['x']}}}]
msg=[{'role':'user','content':'Use the answer tool to submit x=hi.'}]
def has(tc): return bool(getattr(tc,'tool_calls',None))
auto=forced='NO'
try:
  m=c.chat.completions.create(model='$GM',messages=msg,tools=T,tool_choice='auto',max_tokens=256).choices[0].message
  auto='YES' if has(m) else 'NO'
except Exception as e: auto='ERR:'+str(e)[:80]
try:
  m=c.chat.completions.create(model='$GM',messages=msg,tools=T,
     tool_choice={'type':'function','function':{'name':'answer'}},max_tokens=256).choices[0].message
  forced='YES' if has(m) else 'NO'
except Exception as e: forced='ERR:'+str(e)[:80]
print(f'AUTO={auto} FORCED={forced}')" 2>>"$LOG")
log "PROBE: $VERDICT"

case "$VERDICT" in
  AUTO=YES*)
    log "auto tool-calling works — running FULL gemma eval like the others"
    bash "$E/run_collect.sh" "$GM" $EP 100 8 >>"$E/collect_gemma.out" 2>&1
    log "collect done; swap to gpt-oss to judge"; kill_vllm
    bash "$H/serve_v23.sh" >/dev/null 2>&1
    if wait_health; then bash "$E/run_judge.sh" $EP openai/gpt-oss-20b >>"$LOG" 2>&1; fi
    $PY "$E/aggregate.py" >>"$LOG" 2>&1; log "GEMMA_DONE"
    ;;
  *)
    log "auto parser did NOT yield tool calls. Forced/guided result above decides the fallback."
    log "STOP: leaving gemma served verdict in $LOG; next step = wire forced-tool-choice mode into llm.py (clean if FORCED=YES) or text-ReAct (if both NO)."
    log "GEMMA_NEEDS_FALLBACK"
    ;;
esac
