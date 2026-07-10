#!/bin/bash
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH -C GPU_MEM:24GB
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH -t 02:00:00
#SBATCH -J cf_gpu
#SBATCH -o /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling/logs/%x_%j.out
#SBATCH -e /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling/logs/%x_%j.out
# Usage: sbatch gpu.sbatch <script.py> [args...]
set -euo pipefail
export HF_HOME=/scratch/users/karun09/.huggingface
export PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /scratch/users/karun09/Version_2/counterfactual_simulation/llm_coupling
echo "host=$(hostname) gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader) cmd=$*"
/scratch/users/karun09/miniforge3/envs/simr/bin/python "$@"
echo "DONE $*"
