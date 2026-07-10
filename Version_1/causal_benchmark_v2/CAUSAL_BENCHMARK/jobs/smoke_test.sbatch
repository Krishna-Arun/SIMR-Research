#!/bin/bash
#SBATCH -p normal
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB

module load math py-transformers/4.57.3_py314 py-scipy/1.16.3_py314 py-pytorch/2.9.1_py314

cd /scratch/users/karun09/CAUSAL_BENCHMARK
timeout 600 python3 scripts/run_question_benchmark.py

if [ -f outputs/RESULTS.md ]; then
  cat outputs/RESULTS.md
else
  echo "Benchmark failed - no results"
fi
