#!/bin/bash
#SBATCH -J enrich_actions
#SBATCH -p normal
#SBATCH --cpus-per-task=4
#SBATCH --mem=24GB
#SBATCH --time=00:45:00
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/logs/enrich_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/logs/enrich_%j.err

set -euo pipefail
CS=/scratch/users/karun09/Version_2/counterfactual_simulation
cd "$CS"
echo "host: $(hostname)  start: $(date)"
/scratch/users/karun09/miniforge3/envs/simr/bin/python build_enriched_actions.py
echo "done: $(date)"
