#!/bin/bash
#SBATCH -p normal
#SBATCH -c 4
#SBATCH --mem=48GB
#SBATCH -t 01:00:00
#SBATCH -J taskC_context
#SBATCH -o logs/taskC_context_%j.log
#SBATCH -e logs/taskC_context_%j.err

# Broad 3-arm cohort context (reads the full labs CSV) + the multi-arm cohort + overlap.
set -euo pipefail
cd /scratch/users/karun09/CAUSAL_BENCHMARK
mkdir -p logs

ml purge
ml load math py-scikit-learn/1.3.2_py39 py-pandas/2.0.1_py39

echo "=== build_context · job $SLURM_JOB_ID on $(hostname) · $(date) ==="
python3 -c "import numpy,pandas;print('numpy',numpy.__version__,'pandas',pandas.__version__)"

echo "--- 1/3 build_context.py (pre-index chart for all arms) ---"
python3 -u scripts/build_context.py

echo "--- 2/3 build_multiarm_cohort.py (arms + durable outcomes + landmark) ---"
python3 -u scripts/build_multiarm_cohort.py

echo "--- 3/3 overlap_diagnostic.py (pairwise common support) ---"
python3 -u scripts/overlap_diagnostic.py

echo "=== Done $(date) ==="
