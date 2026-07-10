#!/bin/bash
#SBATCH -p normal
#SBATCH -c 4
#SBATCH --mem=48GB
#SBATCH -t 01:00:00
#SBATCH -J cardiac_cf_pipeline
#SBATCH -o logs/pipeline_%j.log
#SBATCH -e logs/pipeline_%j.err

# Data pipeline: time-zero -> pre-index context (+AKI) -> 3-arm cohort -> overlap.
set -euo pipefail
cd /scratch/users/karun09/CARDIAC_COUNTERFACTUAL
mkdir -p logs

ml purge
ml load math py-scikit-learn/1.3.2_py39 py-pandas/2.0.1_py39

echo "=== cardiac-CF pipeline · job $SLURM_JOB_ID on $(hostname) · $(date) ==="
python3 -c "import numpy,pandas,sklearn;print('numpy',numpy.__version__,'pandas',pandas.__version__,'sklearn',sklearn.__version__)"

echo "--- 1/4 assign_index.py (arm + time-zero) ---";        python3 -u scripts/assign_index.py
echo "--- 2/4 build_context.py (pre-index chart + AKI) ---"; python3 -u scripts/build_context.py
echo "--- 3/4 build_multiarm_cohort.py (outcomes) ---";      python3 -u scripts/build_multiarm_cohort.py
echo "--- 4/4 overlap_diagnostic.py ---";                    python3 -u scripts/overlap_diagnostic.py
echo "=== Done $(date) ==="
