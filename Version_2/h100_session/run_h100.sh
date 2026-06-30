#!/bin/bash
# Real workload for the H100 allocation: question generation for Benchmark A, B, C.
# (Runs real compute the whole time — satisfies Sherlock's no-sleeper rule.)
set -eo pipefail
V2=/scratch/users/karun09/Version_2
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
export TRANSFORMERS_CACHE=$SCRATCH/.huggingface/transformers TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"

echo "===== H100 RUN on $(hostname) at $(date) ====="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true
echo "node=$(hostname) jobid=${SLURM_JOB_ID:-NA} started=$(date)" > "$V2/h100_session/H100_READY"

# Optional: NCBI_API_KEY raises PubMed rate limit (export before sbatch to use).
TARGET="${QGEN_TARGET:-500}"     # override with --export=QGEN_TARGET=20 for a short run

for X in A B C; do
  D=$V2/Benchmark_${X}/Question_Generation
  cd "$D"; export PYTHONPATH=$D
  echo "===== Benchmark ${X}: ensure cohort ====="
  [ -f outputs/pool.parquet ] || $PY -u qgen/cohort.py config/qgen.yaml
  echo "===== Benchmark ${X}: SELF-CHECK (3 questions) ====="
  $PY -u -m qgen.run_generate config/qgen.yaml --target 3 2>&1 | tee "outputs/h100_selfcheck.log"
  echo "===== Benchmark ${X}: FULL generation (${TARGET}) ====="
  $PY -u -m qgen.run_generate config/qgen.yaml --target "$TARGET" 2>&1 | tee "outputs/h100_full.log"
  echo "===== Benchmark ${X} DONE: $(wc -l < outputs/questions.jsonl 2>/dev/null || echo 0) questions ====="
done
echo "===== ALL BENCHMARKS DONE at $(date) ====="
