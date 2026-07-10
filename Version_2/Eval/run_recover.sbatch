#!/bin/bash
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --mem=120G
#SBATCH --cpus-per-task=16
#SBATCH --time=08:00:00
#SBATCH -J qwen_recover
#SBATCH -o /scratch/users/karun09/Version_2/Eval/recover_%j.out
# Recovery after the previous eval job hit its 8h walltime mid C-pubmed collect.
# Self-contained: rebuild vLLM sandbox on this node's $L_SCRATCH (cache is on shared scratch),
# finish Qwen (C-pubmed collect + judge A + aggregate), then full Llama-3.1-8B pass, then gemma bonus.
set -uo pipefail
E=/scratch/users/karun09/Version_2/Eval
H=/scratch/users/karun09/Version_2/h100_session
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
EP=http://localhost:8000/v1
SB=/lscratch/karun09/vllm_v23
export APPTAINER_CACHEDIR=/scratch/users/karun09/.apptainer
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_CACHE=/scratch/users/karun09/.huggingface/hub
LOG=$E/recover.log
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
kill_vllm(){ for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill "$p" 2>/dev/null; done; sleep 8
             for p in $(pgrep -f "vllm serve" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; sleep 5; }
wait_health(){ for i in $(seq 1 150); do curl -sf $EP/models >/dev/null 2>&1 && return 0; sleep 10; done; return 1; }
probe(){ cd "$E" && $PY -c "
from eval.llm import LLM
t=[{'type':'function','function':{'name':'answer','description':'submit','parameters':{'type':'object','properties':{'x':{'type':'string'}},'required':['x']}}}]
r=LLM('$1','$EP').chat([{'role':'user','content':'Call answer with x=hi.'}],tools=t)
print('YES' if r.tool_calls else 'NO')" 2>>"$LOG"; }

: > "$LOG"; log "recovery started on $(hostname) ($(nvidia-smi --query-gpu=name --format=csv,noheader|head -1))"

# 0) rebuild sandbox from cached OCI blobs (re-extract only; --sandbox avoids the mksquashfs OOM)
mkdir -p /lscratch/karun09
if [ ! -x "$SB/usr/bin/python3" ] && [ ! -d "$SB/usr/local/cuda" ]; then
  log "building v23 sandbox (from cache)…"
  apptainer build --force --sandbox "$SB" docker://vllm/vllm-openai:v0.23.0-cu129-ubuntu2404 >>"$E/recover_build.log" 2>&1 \
    && log "sandbox built" || { log "FATAL sandbox build failed"; exit 1; }
else
  log "sandbox already present"; fi

# 1) Qwen3-32B — finish the one missing collect (C with PubMed)
log "serving Qwen3-32B"; kill_vllm
bash "$H/serve_vllm_model.sh" Qwen/Qwen3-32B --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1 >/dev/null 2>&1
if wait_health; then
  log "collecting C/pubmed (the interrupted step)"
  cd "$E"; $PY -m eval.run_eval_c --model Qwen/Qwen3-32B --endpoint $EP --pubmed --n 100 --workers 8 2>&1 | tail -1 | tee -a "$LOG"
else
  log "ERROR: Qwen serve didn't come up"; fi

# 2) judge all Qwen Benchmark-A files with gpt-oss + aggregate
log "swapping to gpt-oss for judging"; kill_vllm
bash "$H/serve_v23.sh" >/dev/null 2>&1
if wait_health; then
  for f in "$E"/results_A_Qwen3-32B_*.json; do [ -e "$f" ] || continue
    $PY -m eval.run_eval_a --judge-file "$f" --judge-model openai/gpt-oss-20b --judge-endpoint $EP --workers 8 2>&1 | tail -1 | tee -a "$LOG"; done
  $PY "$E/aggregate.py" >>"$LOG" 2>&1; log "QWEN_DONE"
else
  log "ERROR: gpt-oss judge server didn't come up"; fi

# 3) Llama-3.1-8B-Instruct (American / Meta) full pass
LM=NousResearch/Meta-Llama-3.1-8B-Instruct
log "serving Llama-3.1-8B"; kill_vllm
bash "$H/serve_vllm_model.sh" "$LM" --enable-auto-tool-choice --tool-call-parser llama3_json >/dev/null 2>&1
if wait_health && [ "$(probe "$LM")" = "YES" ]; then
  log "Llama tool-calling OK; collecting A/B/C x{w,wo} PubMed"
  bash "$E/run_collect.sh" "$LM" $EP 100 8 >>"$E/collect_llama.out" 2>&1
  log "Llama collect done; swapping to gpt-oss to judge"; kill_vllm
  bash "$H/serve_v23.sh" >/dev/null 2>&1
  if wait_health; then for f in "$E"/results_A_Meta-Llama-3.1-8B-Instruct_*.json; do [ -e "$f" ] || continue
    $PY -m eval.run_eval_a --judge-file "$f" --judge-model openai/gpt-oss-20b --judge-endpoint $EP --workers 8 2>&1 | tail -1 | tee -a "$LOG"; done; fi
  $PY "$E/aggregate.py" >>"$LOG" 2>&1; log "LLAMA_DONE"
else
  log "Llama SKIPPED — serve/tool-call failed"; fi
# gemma runs separately on the L40S node (run_gemma_l40s.sh) — not here.

$PY "$E/aggregate.py" >>"$LOG" 2>&1
log "ALL_DONE"
