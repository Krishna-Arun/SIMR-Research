#!/bin/bash
#SBATCH -J icu_encode
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=160GB
#SBATCH --time=06:00:00
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_encode_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_encode_%j.err
set -euo pipefail
export HF_TOKEN="$(tr -d ' \n\r' < /scratch/users/karun09/Version_2/counterfactual_simulation/.hf_token)"
export HF_HOME=/scratch/users/karun09/.huggingface
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
cd /scratch/users/karun09/Version_1/Counterfactual_Algorithm
echo "start $(date) on $(hostname)"; nvidia-smi --query-gpu=name --format=csv,noheader || true
/scratch/users/karun09/Version_1/Counterfactual_Algorithm/envs/clmbr311/bin/python models/encode_clmbr.py /scratch/users/karun09/Version_2/counterfactual_simulation/configs_icu.yaml
echo "done $(date)"
