#!/bin/bash
#SBATCH -J icu_downstream
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48GB
#SBATCH --time=02:00:00
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_downstream_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_downstream_%j.err
set -euo pipefail
cd /scratch/users/karun09/Version_2/counterfactual_simulation
echo "=== actions $(date) ==="; /scratch/users/karun09/miniforge3/envs/simr/bin/python build_enriched_actions_icu.py
echo "=== substrate $(date) ==="; /scratch/users/karun09/miniforge3/envs/simr/bin/python build_train_substrate_icu.py
echo "=== delta-aware train + eval $(date) ==="; /scratch/users/karun09/miniforge3/envs/simr/bin/python train_delta_decoder.py
echo "=== ALL DONE $(date) ==="
