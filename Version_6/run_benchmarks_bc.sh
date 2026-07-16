#!/bin/zsh
# Chained real gpt-oss-20b runs for Benchmarks B (dialysis), B (diuretic), and C.
# Sequential because it's one local model on MPS. Each run is crash-safe/resumable
# via a .partial sidecar next to its --out file (re-running skips finished cases).
set -u
V6="/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/Version_6"
PY="$V6/Benchmark_B/.venv_gptoss/bin/python"
EFFORT="low"
LOG="$V6/bc_run.log"
: > "$LOG"

echo "==== [$(date)] BENCHMARK B (dialysis) full ====" | tee -a "$LOG"
"$PY" "$V6/Benchmark_B/evaluate.py" --backend local --effort "$EFFORT" \
  --cases "$V6/Benchmark_B/cases_eligible_all4.jsonl" \
  --out   "$V6/Benchmark_B/results_gptoss.jsonl" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] BENCHMARK B (diuretic) sample 400 ====" | tee -a "$LOG"
"$PY" "$V6/Benchmark_B/evaluate.py" --backend local --effort "$EFFORT" --limit 400 \
  --cases "$V6/Benchmark_B_diuretic/cases_eligible_all4.jsonl" \
  --out   "$V6/Benchmark_B_diuretic/results_gptoss.jsonl" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] BENCHMARK C full ====" | tee -a "$LOG"
"$PY" "$V6/Benchmark_C/evaluate_c.py" --backend local --effort "$EFFORT" \
  --cases "$V6/Benchmark_C/cases_c.jsonl" \
  --out   "$V6/Benchmark_C/results_c_gptoss.jsonl" 2>&1 | tee -a "$LOG"

echo "==== [$(date)] ALL DONE ====" | tee -a "$LOG"
