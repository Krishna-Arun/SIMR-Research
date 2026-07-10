#!/bin/bash
#SBATCH -J icu_enc_arr
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80GB
#SBATCH --time=05:00:00
#SBATCH --array=0-3
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_enc_arr_%A_%a.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/logs/icu_enc_arr_%A_%a.err
set -euo pipefail
export HF_TOKEN="$(tr -d ' \n\r' < /scratch/users/karun09/Version_2/counterfactual_simulation/.hf_token)"
export HF_HOME=/scratch/users/karun09/.huggingface HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false
cd /scratch/users/karun09/Version_1/Counterfactual_Algorithm
echo "shard $SLURM_ARRAY_TASK_ID start $(date) on $(hostname)"
/scratch/users/karun09/Version_1/Counterfactual_Algorithm/envs/clmbr311/bin/python models/encode_clmbr.py /scratch/users/karun09/Version_2/counterfactual_simulation/configs_icu_shard${SLURM_ARRAY_TASK_ID}.yaml
echo "shard $SLURM_ARRAY_TASK_ID done $(date)"
