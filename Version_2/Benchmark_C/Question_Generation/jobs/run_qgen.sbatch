#!/bin/bash
# Run the Evaluator-Optimizer question generator against the live vLLM endpoints + PubMed MCP server.
# Resumable: questions.jsonl is append-only; a requeue continues toward target_n. Self-resubmits (<=15)
# until QGEN_COMPLETE exists, mirroring CARDIAC_COUNTERFACTUAL/jobs/run_gpu.sbatch.
#SBATCH -p gpu
#SBATCH -C "GPU_MEM:80GB|GPU_MEM:141GB"
#SBATCH -G 5
#SBATCH -c 16
#SBATCH --mem=128GB
#SBATCH -t 2-00:00:00
#SBATCH -J qgen_run
#SBATCH -o /scratch/users/karun09/Version_2/Benchmark_C/Question_Generation/outputs/run.%j.out
#SBATCH -e /scratch/users/karun09/Version_2/Benchmark_C/Question_Generation/outputs/run.%j.out

set -eo pipefail
QG=/scratch/users/karun09/Version_2/Benchmark_C/Question_Generation
export PYTHONPATH=$QG
PY=/scratch/users/karun09/miniforge3/envs/simr/bin/python
export HF_HOME=$SCRATCH/.huggingface HF_HUB_CACHE=$SCRATCH/.huggingface/hub
cd "$QG"

# NOTE: this assumes serve_models.sbatch is already running and endpoints are reachable.
# For a single-node setup, launch serving here instead and background it before run_generate.
$PY -m qgen.run_generate "$@" || true

if [ ! -f outputs/QGEN_COMPLETE ]; then
  n=$(cat outputs/.resume 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > outputs/.resume
  [ "$n" -le 15 ] && sbatch jobs/run_qgen.sbatch "$@"
fi
