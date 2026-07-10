#!/bin/bash
#SBATCH -p normal
#SBATCH -c 4
#SBATCH --mem=24GB
#SBATCH -t 00:45:00
#SBATCH -J taskC_data
#SBATCH -o logs/taskC_data_%j.log
#SBATCH -e logs/taskC_data_%j.err

# CPU pipeline + GPU-free end-to-end verification for Task C:
#   build_dataset (adds outcomes) -> select_outcome -> build_propensity_matches
#   -> run_taskC (MOCK predictor) -> score_taskC
# Run real LLMs separately with jobs/run_taskC_gpu.sbatch.

set -euo pipefail
cd /scratch/users/karun09/CAUSAL_BENCHMARK
mkdir -p logs

ml purge
ml load math
ml load py-scikit-learn/1.3.2_py39
ml load py-pandas/2.0.1_py39

echo "=== Task C data pipeline · job $SLURM_JOB_ID on $(hostname) · $(date) ==="
python3 -c "import numpy,pandas,sklearn;print('numpy',numpy.__version__,'pandas',pandas.__version__,'sklearn',sklearn.__version__)"

echo "--- 1/5 build_dataset.py (rebuild episodes.json WITH outcomes) ---"
python3 -u scripts/build_dataset.py

echo "--- 2/5 select_outcome.py ---"
python3 -u scripts/select_outcome.py

echo "--- 3/5 build_propensity_matches.py ---"
python3 -u scripts/build_propensity_matches.py

echo "--- 4/5 run_taskC.py (MOCK predictor, CPU end-to-end) ---"
CAUSAL_BACKEND=mock CAUSAL_PROMPTS=zero_shot python3 -u scripts/run_taskC.py

echo "--- 5/5 score_taskC.py ---"
python3 -u scripts/score_taskC.py

echo "=== RESULTS (head) ==="
sed -n '1,60p' outputs/TASKC_RESULTS.md || true
echo "=== Done $(date) ==="
