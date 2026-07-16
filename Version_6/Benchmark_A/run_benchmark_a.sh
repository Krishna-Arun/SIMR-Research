#!/bin/zsh
# Full Benchmark A pipeline over the COMPLETE-SET backbone (82 A->B->C pairs = 164
# patients), chained end to end. One local gpt-oss-20b model on MPS, so stages run
# sequentially. Run under caffeinate so it survives a closed lid.
#
#   caffeinate -i ./run_benchmark_a.sh
#
# Stages:
#   0. build the complete-set backbone case-id list (recomputed from B/C eligibility)
#   1. generate  -> questions.jsonl        (Evaluator-Optimizer + single-round discard gate)
#   2. answer     -> transcripts.jsonl     (multi-turn active-sensing agent)
#   3. score      -> scores.json           (scheme B: MC accuracy + reasoning composite)
set -u
A="/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/Version_6/Benchmark_A"
PY="$A/../Benchmark_B/.venv_gptoss/bin/python"
GATE_K=1                       # single-round discard gate (compute-saving)
LOG="$A/bench_a_run.log"
: > "$LOG"

echo "==== [$(date)] STEP 0: build complete-set backbone ====" | tee -a "$LOG"
"$PY" "$A/build_complete_set.py" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] STEP 1: generate questions (gate-k=$GATE_K) ====" | tee -a "$LOG"
"$PY" "$A/generate_questions.py" \
  --case-ids-file "$A/complete_set_case_ids.txt" \
  --gate-k "$GATE_K" \
  --out "$A/questions.jsonl" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] STEP 2: answering agent ====" | tee -a "$LOG"
"$PY" "$A/answer_agent.py" \
  --questions "$A/questions.jsonl" \
  --out "$A/transcripts.jsonl" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] STEP 3: scorer ====" | tee -a "$LOG"
"$PY" "$A/scorer.py" \
  --transcripts "$A/transcripts.jsonl" \
  --out "$A/scores.json" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] BENCHMARK A DONE ====" | tee -a "$LOG"
