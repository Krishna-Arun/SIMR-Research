#!/bin/bash
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH -C GPU_MEM:80GB
#SBATCH -c 8
#SBATCH --mem=96G
#SBATCH -t 08:00:00
#SBATCH -J cf_train
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling/logs/%x_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling/logs/%x_%j.out
# Usage: sbatch train.sbatch <script.py> [args...]   (large GPU for backprop through a frozen 8B)
set -euo pipefail
export HF_HOME=/scratch/users/karun09/.huggingface
export PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling
echo "host=$(hostname) gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader) cmd=$*"
/scratch/users/karun09/miniforge3/envs/simr/bin/python "$@"
echo "DONE $*"
