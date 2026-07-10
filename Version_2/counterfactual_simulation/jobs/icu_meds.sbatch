#!/bin/bash
#SBATCH -J icu_meds
#SBATCH -p normal
#SBATCH --cpus-per-task=8
#SBATCH --mem=128GB
#SBATCH --time=04:00:00
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_meds_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_meds_%j.err
set -euo pipefail
cd /scratch/users/karun09/Version_2/counterfactual_simulation
echo "start $(date) on $(hostname)"
/scratch/users/karun09/Version_1/Counterfactual_Algorithm/envs/clmbr311/bin/python build_icu_meds.py
echo "done $(date)"
