#!/bin/zsh
# ============================================================================
#  MASTER CHAIN — all SIMR benchmarks, end to end, on local gpt-oss-20b.
#
#  One model on MPS, so every stage runs SEQUENTIALLY. Launch once, unattended:
#      caffeinate -i ./run_all_benchmarks.sh
#
#  Stages (in order):
#    A1  Benchmark A — answering agent   questions.jsonl -> transcripts.jsonl
#    A2  Benchmark A — scorer            transcripts.jsonl -> scores.json
#    B1  Benchmark B (dialysis)          cases -> results_gptoss.jsonl
#    B2  Benchmark B (diuretic, 400)     cases -> results_gptoss.jsonl
#    C   Benchmark C (matched pairs)     cases_c -> results_c_gptoss.jsonl
#
#  Crash-safe: B/C resume from a .partial sidecar; A re-runs cleanly if killed.
#  Stage guard: a stage is SKIPPED if its output already exists (delete the
#  output file to force a re-run).
# ============================================================================
set -u
V6="/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/Version_6"
A="$V6/Benchmark_A"
PY="$V6/Benchmark_B/.venv_gptoss/bin/python"
EFFORT="low"
LOG="$V6/all_benchmarks.log"
: > "$LOG"

run () {  # run <name> <output-file> <cmd...>   — skip if output exists
  local name="$1"; local out="$2"; shift 2
  echo "==== [$(date)] $name ====" | tee -a "$LOG"
  if [ -s "$out" ]; then
    echo "  SKIP — output already exists: $out" | tee -a "$LOG"
    return 0
  fi
  "$@" 2>&1 | tee -a "$LOG"
  echo "  -> wrote $out" | tee -a "$LOG"
}

echo "######## [$(date)] MASTER BENCHMARK CHAIN START ########" | tee -a "$LOG"

# ---- Benchmark A (questions already generated: 69) ----
run "A1 Benchmark A — answering agent" "$A/transcripts.jsonl" \
  "$PY" "$A/answer_agent.py" --questions "$A/questions.jsonl" --out "$A/transcripts.jsonl"

run "A2 Benchmark A — scorer" "$A/scores.json" \
  "$PY" "$A/scorer.py" --transcripts "$A/transcripts.jsonl" --out "$A/scores.json"

# ---- Benchmark B ----
run "B1 Benchmark B (dialysis)" "$V6/Benchmark_B/results_gptoss.jsonl" \
  "$PY" "$V6/Benchmark_B/evaluate.py" --backend local --effort "$EFFORT" \
    --cases "$V6/Benchmark_B/cases_eligible_all4.jsonl" \
    --out   "$V6/Benchmark_B/results_gptoss.jsonl"

run "B2 Benchmark B (diuretic, 400)" "$V6/Benchmark_B_diuretic/results_gptoss.jsonl" \
  "$PY" "$V6/Benchmark_B/evaluate.py" --backend local --effort "$EFFORT" --limit 400 \
    --cases "$V6/Benchmark_B_diuretic/cases_eligible_all4.jsonl" \
    --out   "$V6/Benchmark_B_diuretic/results_gptoss.jsonl"

# ---- Benchmark C ----
run "C Benchmark C (matched pairs)" "$V6/Benchmark_C/results_c_gptoss.jsonl" \
  "$PY" "$V6/Benchmark_C/evaluate_c.py" --backend local --effort "$EFFORT" \
    --cases "$V6/Benchmark_C/cases_c.jsonl" \
    --out   "$V6/Benchmark_C/results_c_gptoss.jsonl"

echo "######## [$(date)] MASTER BENCHMARK CHAIN DONE ########" | tee -a "$LOG"
echo "results:" | tee -a "$LOG"
echo "  A: $A/scores.json" | tee -a "$LOG"
echo "  B: $V6/Benchmark_B/results_gptoss.jsonl  +  $V6/Benchmark_B_diuretic/results_gptoss.jsonl" | tee -a "$LOG"
echo "  C: $V6/Benchmark_C/results_c_gptoss.jsonl" | tee -a "$LOG"
