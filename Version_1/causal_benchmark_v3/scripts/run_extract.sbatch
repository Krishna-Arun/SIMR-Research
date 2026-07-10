#!/bin/bash
#SBATCH -p normal
#SBATCH -c 4
#SBATCH --mem=16GB
#SBATCH -t 00:30:00
#SBATCH -J ctb_benefit_extract
#SBATCH -o /scratch/users/karun09/causal_benchmark_v3/outputs/extract_%j.log
#SBATCH -e /scratch/users/karun09/causal_benchmark_v3/outputs/extract_%j.err

# Long-horizon benefit-outcome extraction (scans the 978k-row labs CSV). CPU-only.
set -uo pipefail
ml purge
ml load math py-pandas 2>/dev/null || ml load python/3.12 2>/dev/null || true
cd /scratch/users/karun09/causal_benchmark_v3/scripts
python3 extract_benefit_outcome.py
echo "=== done $(date) ==="
